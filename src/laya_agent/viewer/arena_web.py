"""Live decision viewer for arena runs (Snake and 2048). Standard library only.

Reads the files the arena runner writes under runs/<game>/:
  <session_id>.jsonl         submission log (laya_agent.arena.spec_log.SpecLog)
  <session_id>.events.jsonl  live events: session_start, decision, session_end (optional)
  <session_id>.final.json    the game's final API response (optional)

Usage: python -m laya_agent.viewer.arena_web [runs_folder] [--port 8770] [--host 127.0.0.1]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..arena.spec_log import verify_log

STATIC = Path(__file__).with_name("arena_static")
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
}
GAMES = ("snake", "2048")
EVENTS_SUFFIX = ".events.jsonl"
FINAL_SUFFIX = ".final.json"
SPEC_SUFFIX = ".jsonl"
TIMING_KEYS = ("decide_ms", "api_ms", "turn_ms")

SNAKE_POINTS_PER_FOOD = 60
SNAKE_WIN_BONUS = 100
SNAKE_WIN_FOODS = 15
SNAKE_UNLOCK_POINTS = 600
TILE_UNLOCK = 512
POINTS_CAP = 1000
MAX_LINES_PER_POLL = 200
MAX_SESSIONS = 200


def snake_points(foods: int, won: bool) -> int:
    return min(POINTS_CAP, foods * SNAKE_POINTS_PER_FOOD + (SNAKE_WIN_BONUS if won else 0))


def points_2048(best_tile: int, score: int) -> int:
    tile_part = max(0, int(math.log2(best_tile)) - 6) * 143 if best_tile > 0 else 0
    return min(POINTS_CAP, tile_part + max(0, int(score)) // 1000)


def best_tile(state: Any) -> int:
    # The largest tile is always on the board, so the grid alone gives it
    grid = state.get("grid") if isinstance(state, dict) else None
    vals = [v for row in grid or [] if isinstance(row, list) for v in row if isinstance(v, (int, float))]
    return int(max(vals)) if vals else 0


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def timing_stats(lines: list[dict]) -> dict:
    out = {}
    for key in TIMING_KEYS:
        vals = [t[key] for line in lines if isinstance(t := line.get("timing"), dict)
                and isinstance(t.get(key), (int, float)) and not isinstance(t.get(key), bool)]
        out[key] = {
            "last": vals[-1] if vals else None,
            "mean": round(sum(vals) / len(vals), 1) if vals else None,
            "p95": percentile(vals, 0.95),
            "n": len(vals),
        }
    return out


class JsonlTail:
    """Parses a JSONL file incrementally; a half-written last line waits for the next read."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.offset = 0
        self.items: list[dict] = []
        self.bad_lines = 0

    def refresh(self) -> list[dict]:
        try:
            size = self.path.stat().st_size
        except OSError:
            self.offset, self.items, self.bad_lines = 0, [], 0
            return self.items
        if size < self.offset:  # file was replaced, start over
            self.offset, self.items, self.bad_lines = 0, [], 0
        if size == self.offset:
            return self.items
        with open(self.path, "rb") as fh:
            fh.seek(self.offset)
            chunk = fh.read(size - self.offset)
        end = chunk.rfind(b"\n")
        if end < 0:
            return self.items
        for raw in chunk[:end].split(b"\n"):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                self.bad_lines += 1
                continue
            if isinstance(obj, dict):
                self.items.append(obj)
        self.offset += end + 1
        return self.items


@dataclass
class Session:
    session_id: str
    folder: Path
    game: str | None

    @property
    def spec(self) -> Path:
        return self.folder / f"{self.session_id}{SPEC_SUFFIX}"

    @property
    def events(self) -> Path:
        return self.folder / f"{self.session_id}{EVENTS_SUFFIX}"

    @property
    def final(self) -> Path:
        return self.folder / f"{self.session_id}{FINAL_SUFFIX}"

    def mtime(self) -> float:
        times = []
        for p in (self.spec, self.events, self.final):
            try:
                times.append(p.stat().st_mtime)
            except OSError:
                pass
        return max(times) if times else 0.0


class RunStore:
    """Finds sessions under the runs folder and keeps parsed log tails between polls."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._lock = threading.Lock()
        self._tails: dict[Path, JsonlTail] = {}
        self._finals: dict[Path, tuple[tuple[float, int], Any]] = {}

    def _folders(self) -> list[Path]:
        if not self.root.is_dir():
            return []
        folders = [self.root]
        folders += sorted(p for p in self.root.iterdir() if p.is_dir())
        return folders

    def scan(self) -> dict[str, Session]:
        found: dict[str, Session] = {}
        for folder in self._folders():
            game = folder.name if folder.name in GAMES else None
            try:
                names = [p.name for p in folder.iterdir() if p.is_file()]
            except OSError:
                continue
            for name in names:
                if name.endswith(EVENTS_SUFFIX):
                    sid = name[: -len(EVENTS_SUFFIX)]
                elif name.endswith(SPEC_SUFFIX):
                    sid = name[: -len(SPEC_SUFFIX)]
                else:
                    continue
                if sid and sid not in found:
                    found[sid] = Session(sid, folder, game)
        return found

    def _tail(self, path: Path) -> list[dict]:
        with self._lock:
            tail = self._tails.get(path)
            if tail is None:
                tail = self._tails[path] = JsonlTail(path)
            return list(tail.refresh())

    def _final(self, path: Path) -> Any:
        try:
            st = path.stat()
        except OSError:
            return None
        key = (st.st_mtime, st.st_size)
        with self._lock:
            cached = self._finals.get(path)
            if cached and cached[0] == key:
                return cached[1]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None  # still being written
        with self._lock:
            self._finals[path] = (key, data)
        return data

    def _read(self, s: Session) -> tuple[list[dict], list[dict], Any]:
        lines = self._tail(s.spec)
        events = self._tail(s.events)
        final = self._final(s.final)
        if s.game is None:
            s.game = next((x.get("game") for x in lines + events if x.get("game")), None)
        return lines, events, final

    def summarize(self, s: Session, lines: list[dict], events: list[dict], final: Any) -> dict:
        applied = [x for x in lines if x.get("result") == "applied"]
        fallbacks = sum(1 for x in applied if (x.get("decision") or {}).get("source") == "fallback")
        start = next((e for e in events if e.get("type") == "session_start"), None)
        end = next((e for e in reversed(events) if e.get("type") == "session_end"), None)
        final = final if isinstance(final, dict) else None
        state = lines[-1].get("state_after") if lines else (final or {}).get("state")
        state = state if isinstance(state, dict) else {}
        reported_won = (end or {}).get("won", (final or {}).get("won"))
        out: dict[str, Any] = {
            "game": s.game,
            "lines": len(lines),
            "steps": len(applied),
            "rejected": len(lines) - len(applied),
            "fallbacks": fallbacks,
            "fallback_share": round(fallbacks / len(applied), 4) if applied else 0.0,
            "timing": timing_stats(lines),
            "final_score": (final or {}).get("score", (end or {}).get("score")),
            "done": final is not None or end is not None,
            "won": reported_won,
            "decisions": sum(1 for e in events if e.get("type") == "decision"),
        }
        if s.game == "snake":
            foods = int(state.get("foodEaten") or 0)
            won = bool(reported_won) or foods >= SNAKE_WIN_FOODS
            computed = snake_points(foods, won)
            target_foods = SNAKE_UNLOCK_POINTS // SNAKE_POINTS_PER_FOOD
            out.update(foods=foods, length=len(state.get("snake") or []), won=won,
                       target_points=SNAKE_UNLOCK_POINTS, target_foods=target_foods,
                       progress=min(1.0, foods / target_foods), unlocked=computed >= SNAKE_UNLOCK_POINTS)
        elif s.game == "2048":
            tile = best_tile(state)
            score = int(state.get("score") or 0)
            computed = points_2048(tile, score)
            steps_to_target = int(math.log2(TILE_UNLOCK)) - 6
            tile_steps = max(0, int(math.log2(tile)) - 6) if tile else 0
            out.update(best_tile=tile, score=score, target_tile=TILE_UNLOCK,
                       progress=min(1.0, tile_steps / steps_to_target), unlocked=tile >= TILE_UNLOCK)
        else:
            computed = None
        reported = (end or {}).get("points")
        has_reported = isinstance(reported, (int, float)) and not isinstance(reported, bool)
        out["points_computed"] = computed
        out["points"] = reported if has_reported else computed
        out["points_source"] = "session_end" if has_reported else "computed"
        out["agent_name"] = (start or {}).get("agent_name")
        return out

    def sessions(self) -> list[dict]:
        found = sorted(self.scan().values(), key=lambda s: s.mtime(), reverse=True)[:MAX_SESSIONS]
        now = time.time()
        out = []
        for s in found:
            lines, events, final = self._read(s)
            summ = self.summarize(s, lines, events, final)
            score = summ["final_score"]
            if score is None:
                score = summ.get("score", summ.get("foods"))
            mtime = s.mtime()
            out.append({"game": s.game, "session_id": s.session_id, "mtime": mtime, "age_s": round(now - mtime, 1),
                        "steps": summ["steps"], "last_score": score, "points": summ["points"],
                        "done": summ["done"], "won": summ["won"], "agent_name": summ["agent_name"]})
        return out

    def session(self, sid: str, after: int = 0, eafter: int = 0, limit: int = MAX_LINES_PER_POLL) -> dict | None:
        s = self.scan().get(sid)
        if s is None:
            return None
        lines, events, final = self._read(s)
        reset = after > len(lines) or eafter > len(events)
        if reset:
            after = eafter = 0
        after, eafter = max(0, after), max(0, eafter)
        limit = max(1, limit)
        new_lines = lines[after:][-limit:]
        new_events = events[eafter:][-limit:]
        start = next((e for e in events if e.get("type") == "session_start"), None)
        end = next((e for e in reversed(events) if e.get("type") == "session_end"), None)
        mtime = s.mtime()
        return {
            "session_id": s.session_id,
            "game": s.game,
            "folder": str(s.folder),
            "reset": reset,
            "after": after,
            "first_index": len(lines) - len(new_lines) + 1 if new_lines else None,
            "lines": new_lines,
            "next_after": len(lines),
            "events": new_events,
            "next_events_after": len(events),
            "session_start": start,
            "session_end": end,
            "final": final,
            "summary": self.summarize(s, lines, events, final),
            "mtime": mtime,
            "age_s": round(time.time() - mtime, 1),
        }

    def verify(self, sid: str) -> dict | None:
        s = self.scan().get(sid)
        if s is None:
            return None
        try:
            data = s.spec.read_bytes()
        except OSError:
            data = b""
        cut = data.rfind(b"\n") + 1
        if cut == 0:
            return {"ok": None, "pending": True, "problems": [], "lines": 0, "chain_ok": None}
        final = self._final(s.final)
        final = final if isinstance(final, dict) else None
        if cut == len(data):
            result = verify_log(s.spec, final)
        else:
            # A line is being appended right now; check the complete lines only
            fd, tmp = tempfile.mkstemp(suffix=".jsonl")
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data[:cut])
                result = verify_log(tmp, final)
            finally:
                os.unlink(tmp)
        result["chain_ok"] = not any("hash" in p for p in result.get("problems", []))
        result["pending"] = False
        return result


def make_handler(store: RunStore):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # keep the console for the bot
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            try:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def _json(self, code: int, obj: Any) -> None:
            self._send(code, json.dumps(obj, default=str).encode("utf-8"), "application/json")

        def do_GET(self) -> None:
            url = urlparse(self.path)
            query = parse_qs(url.query)

            def arg(name: str, default: str = "") -> str:
                return query.get(name, [default])[0]

            def int_arg(name: str, default: int) -> int:
                try:
                    return int(arg(name, str(default)))
                except ValueError:
                    return default

            if url.path in STATIC_FILES:
                name, ctype = STATIC_FILES[url.path]
                self._send(200, (STATIC / name).read_bytes(), ctype)
            elif url.path == "/api/sessions":
                items = store.sessions()
                self._json(200, {"root": str(store.root.resolve()), "sessions": items,
                                 "newest": items[0]["session_id"] if items else None})
            elif url.path == "/api/session":
                sid = arg("id")
                if not sid:
                    items = store.sessions()
                    sid = items[0]["session_id"] if items else ""
                body = store.session(sid, int_arg("after", 0), int_arg("eafter", 0),
                                     int_arg("limit", MAX_LINES_PER_POLL)) if sid else None
                if body is None:
                    self._json(404, {"error": f"unknown session {sid!r}"})
                else:
                    self._json(200, body)
            elif url.path == "/api/verify":
                body = store.verify(arg("id"))
                if body is None:
                    self._json(404, {"error": f"unknown session {arg('id')!r}"})
                else:
                    self._json(200, body)
            else:
                self._send(404, b"not found", "text/plain")

    return Handler


def make_server(root: str | Path, host: str = "127.0.0.1", port: int = 8770) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), make_handler(RunStore(root)))
    server.daemon_threads = True
    return server


def main() -> None:
    ap = argparse.ArgumentParser(description="Live Laya decision viewer for arena runs")
    ap.add_argument("runs", nargs="?", default="runs", help="runs folder (default: runs)")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    server = make_server(args.runs, args.host, args.port)
    host, port = server.server_address[:2]
    print(f"arena viewer on http://{host}:{port}  (runs: {Path(args.runs).resolve()})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
