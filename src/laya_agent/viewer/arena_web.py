"""Live decision viewer for arena runs (Snake and 2048). Standard library only.

Reads the files the arena runner writes under runs/<game>/:
  <session_id>.jsonl         submission log (laya_agent.arena.spec_log.SpecLog)
  <session_id>.events.jsonl  live events: session_start, decision, session_end (optional)
  <session_id>.final.json    the game's final API response (optional)

Usage: python -m laya_agent.viewer.arena_web [runs_folder] [--port 8770] [--host 127.0.0.1] [--sim-roots "runs_sim*"]

--sim-roots adds read-only simulator folders (a glob, relative to the working directory), scanned two
levels deep, for example runs_sim_r2/noul_nodir/2048. Their sessions get a unique key such as
"runs_sim_r2/noul_nodir/2048/<session_id>", because simulator seeds repeat session ids across folders.

Pages: / is the built dashboard in app_dist/ (frontend/ in the repo builds it), /classic is the
original single-file viewer. Without app_dist/ the classic viewer is served at / as well.
/api/leaderboard?game=snake proxies the public arena leaderboard (cached 60 s, last good copy when offline).
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict, deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..arena.spec_log import verify_log
from .doom_web import ACTIONS as DOOM_ACTIONS
from .doom_web import frame_bytes, has_frames, log_keys, recording_checks

STATIC = Path(__file__).with_name("arena_static")
APP_DIST = Path(__file__).with_name("app_dist")
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/classic": ("index.html", "text/html; charset=utf-8"),
    "/classic/": ("index.html", "text/html; charset=utf-8"),
    "/classic/index.html": ("index.html", "text/html; charset=utf-8"),
    "/classic/style.css": ("style.css", "text/css; charset=utf-8"),
    "/classic/app.js": ("app.js", "application/javascript; charset=utf-8"),
}
APP_PAGES = ("/", "/index.html")
ASSET_TYPES = {
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".json": "application/json",
    ".txt": "text/plain; charset=utf-8",
}
SAFE_ASSET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
GAMES = ("snake", "2048", "doom")
EVENTS_SUFFIX = ".events.jsonl"
FINAL_SUFFIX = ".final.json"
SPEC_SUFFIX = ".jsonl"
TIMING_KEYS = ("decide_ms", "api_ms", "turn_ms")
DIRECTIONS = ("up", "down", "left", "right")

# A session is LIVE only while its files keep growing and no session_end or final response exists
LIVE_WINDOW_S = 15.0
INTERRUPTED_AFTER_S = 120.0
SIM_ENVS = ("LOCAL_SIM", "LOCAL_FIXTURE")
SIM_AGENTS = ("SIM-EVAL",)
HISTORY_PAGE = 400
MAX_TAILS = 48
MAX_RECORD_SETS = 12

# Public arena leaderboard, fetched server side because the browser cannot call it directly

LEADERBOARD_URL = "https://topgameai.com/api/arena/leaderboard/{game}"
LEADERBOARD_TTL_S = 60.0
LEADERBOARD_TIMEOUT_S = 10.0
LEADERBOARD_UA = "CodeYatri-laya-agent/1.0"
LEADERBOARD_RETRY_S = 15.0  # after a failed fetch, wait this long before trying the network again
SAFE_GAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")

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


def session_status(done: bool, age_s: float) -> str:
    if done:
        return "finished"
    if age_s <= LIVE_WINDOW_S:
        return "live"
    return "idle" if age_s <= INTERRUPTED_AFTER_S else "interrupted"


def env_kind(start: dict | None) -> str:
    # The env label the runner wrote decides it; an agent name alone never makes a session hosted
    start = start or {}
    env = str(start.get("env") or "").upper()
    agent = str(start.get("agent_name") or "").upper()
    if env in SIM_ENVS or agent in SIM_AGENTS or agent.startswith("TEST"):
        return "simulator"
    if env == "HOSTED":
        return "hosted"
    return "unknown"


def session_source(kind: str, origin: str) -> str:
    # The env label wins; a session without one is tagged by the folder it was found in
    if kind == "hosted":
        return "arena"
    if kind == "simulator":
        return "simulator"
    return "arena" if origin == "runs" else "simulator"


def pair_decisions(lines: list[dict], events: list[dict]) -> tuple[list[dict | None], dict | None]:
    """Matches each submission line to the decision event the runner wrote just before sending it.

    A rejected move and its retry share a step, so the k-th usable decision of a step belongs to the
    k-th line of that step. A decision followed by reconcile "not_applied" never became a line.
    Returns one event (or None) per line, and the newest decision that has no line yet.
    """
    decisions: list[list] = []
    for e in events:
        kind = e.get("type")
        if kind == "decision":
            decisions.append([e, True])
        elif (kind == "reconcile" and e.get("verdict") == "not_applied" and decisions
              and decisions[-1][0].get("step") == e.get("step")):
            decisions[-1][1] = False
    queues: dict[Any, deque] = {}
    for idx, (e, usable) in enumerate(decisions):
        if usable:
            queues.setdefault(e.get("step"), deque()).append(idx)
    used: set[int] = set()
    paired: list[dict | None] = []
    for line in lines:
        q = queues.get(line.get("step"))
        idx = q.popleft() if q else None
        ev = decisions[idx][0] if idx is not None else None
        if idx is not None:
            used.add(idx)
        paired.append(ev if ev is not None and ev.get("chosen") == line.get("action") else None)
    usable = [i for i, (_, ok) in enumerate(decisions) if ok]
    pending = decisions[usable[-1]][0] if usable and usable[-1] not in used else None
    return paired, pending


def compact_event(ev: dict | None) -> dict | None:
    if not isinstance(ev, dict):
        return None
    keys = ("step", "facts", "kinds", "p_true", "probabilities", "chosen", "source", "laya_choice", "reason",
            "decide_ms", "laya_ms", "ts", "offered", "tic")
    return {k: ev.get(k) for k in keys}


def questions_by_direction(line: dict, ev: dict | None) -> dict[str, str] | None:
    # The decider lists one question per asked direction in up, down, left, right order,
    # and p_true holds exactly the asked directions, so the two zip together
    questions = (line.get("decision") or {}).get("questions")
    p_true = (ev or {}).get("p_true")
    if not isinstance(questions, list) or not isinstance(p_true, dict):
        return None
    order = DOOM_ACTIONS if any(k not in DIRECTIONS for k in p_true) else DIRECTIONS
    asked = [d for d in order if d in p_true]
    if len(asked) != len(questions):
        return None
    return dict(zip(asked, questions))


def step_record(i: int, line: dict, ev: dict | None, error: Any = None) -> dict:
    dec = line.get("decision") if isinstance(line.get("decision"), dict) else {}
    questions = dec.get("questions")
    return {
        "i": i,
        "step": line.get("step"),
        "result": line.get("result"),
        "action": line.get("action"),
        "source": dec.get("source"),
        "confidence": dec.get("confidence"),
        "probabilities": dec.get("probabilities"),
        "n_questions": len(questions) if isinstance(questions, list) else 0,
        "timing": line.get("timing"),
        "ts": line.get("ts"),
        "hash": str(line.get("hash") or "")[:16],
        "state_before": line.get("state_before"),
        "state_after": line.get("state_after"),
        "event": compact_event(ev),
        "error": error,
    }


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


def fetch_leaderboard_json(game: str) -> Any:
    req = urllib.request.Request(LEADERBOARD_URL.format(game=game),
                                 headers={"User-Agent": LEADERBOARD_UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=LEADERBOARD_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


class Leaderboard:
    """Caches the public leaderboard per game for LEADERBOARD_TTL_S.

    On a failed fetch it serves the last good copy marked stale with its fetch time, and with no copy it
    returns an empty board and the error. Rows are passed through exactly as the arena sent them.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._game_locks: dict[str, threading.Lock] = {}
        self._good: dict[str, dict] = {}
        self._failed: dict[str, tuple[float, str]] = {}

    def get(self, game: str) -> dict:
        with self._lock:
            game_lock = self._game_locks.setdefault(game, threading.Lock())
        with game_lock:  # one fetch per game at a time
            good = self._good.get(game)
            if good and time.time() - good["fetched_at"] < LEADERBOARD_TTL_S:
                return {**good, "stale": False, "error": None}
            failed = self._failed.get(game)
            if failed and time.time() - failed[0] < LEADERBOARD_RETRY_S:
                return self._fallback(game, good, failed[1])
            try:
                data = fetch_leaderboard_json(game)
                rows = data.get("leaderboard") if isinstance(data, dict) else None
                if not isinstance(rows, list):
                    raise ValueError("the response has no leaderboard list")
                good = {"game": data.get("game", game), "leaderboard": [r for r in rows if isinstance(r, dict)],
                        "fetched_at": time.time(), "url": LEADERBOARD_URL.format(game=game)}
                self._good[game] = good
                self._failed.pop(game, None)
                return {**good, "stale": False, "error": None}
            except (OSError, ValueError, urllib.error.URLError) as e:
                # json.JSONDecodeError is a ValueError, HTTPError and timeouts are OSErrors
                error = f"{type(e).__name__}: {e}"
                self._failed[game] = (time.time(), error)
                return self._fallback(game, good, error)

    @staticmethod
    def _fallback(game: str, good: dict | None, error: str) -> dict:
        if good:
            return {**good, "stale": True, "error": error}
        return {"game": game, "leaderboard": [], "fetched_at": None, "url": LEADERBOARD_URL.format(game=game),
                "stale": True, "error": error}


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
    key: str = ""         # unique API id; the plain session id for sessions in the main runs folder
    origin: str = "runs"  # runs | sim

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

    def __init__(self, root: str | Path, sim_roots: list[str | Path] | None = None) -> None:
        self.root = Path(root)
        main = self.root.resolve()
        # A simulator root that is the main folder (or inside it) would list the same sessions twice
        self.sim_roots = [Path(r) for r in sim_roots or []
                          if Path(r).resolve() != main and main not in Path(r).resolve().parents]
        self._lock = threading.Lock()
        self._tails: OrderedDict[Path, JsonlTail] = OrderedDict()
        self._finals: dict[Path, tuple[tuple[float, int], Any]] = {}
        self._records: OrderedDict[Path, tuple[tuple, list[dict], dict | None]] = OrderedDict()
        self._lights: dict[str, tuple[tuple, dict]] = {}

    @staticmethod
    def _subdirs(folder: Path) -> list[Path]:
        try:
            return sorted(p for p in folder.iterdir() if p.is_dir() and not p.name.endswith(".frames"))
        except OSError:
            return []

    def _folders(self) -> list[tuple[Path, str, Path]]:
        out: list[tuple[Path, str, Path]] = []
        if self.root.is_dir():
            out.append((self.root, "runs", self.root))
            out += [(p, "runs", self.root) for p in self._subdirs(self.root)]
        for root in self.sim_roots:
            if not root.is_dir():
                continue
            out.append((root, "sim", root))
            for child in self._subdirs(root):
                out.append((child, "sim", root))
                out += [(g, "sim", root) for g in self._subdirs(child)]
        return out

    def scan(self) -> dict[str, Session]:
        found: dict[str, Session] = {}
        for folder, origin, base in self._folders():
            game = folder.name if folder.name in GAMES else None
            try:
                names = [p.name for p in folder.iterdir() if p.is_file()]
            except OSError:
                continue
            prefix = "" if origin == "runs" else folder.relative_to(base.parent).as_posix() + "/"
            for name in names:
                if name.endswith(EVENTS_SUFFIX):
                    sid = name[: -len(EVENTS_SUFFIX)]
                elif name.endswith(SPEC_SUFFIX):
                    sid = name[: -len(SPEC_SUFFIX)]
                else:
                    continue
                key = prefix + sid
                if sid and key not in found:
                    found[key] = Session(sid, folder, game, key, origin)
        return found

    def find(self, ident: str) -> Session | None:
        return self._get(ident)

    def _get(self, ident: str) -> Session | None:
        """Finds a session by its key, or by plain session id (the main runs folder wins)."""
        found = self.scan()
        if ident in found:
            return found[ident]
        return next((s for s in found.values() if s.session_id == ident), None)

    def _tail(self, path: Path) -> list[dict]:
        with self._lock:
            tail = self._tails.get(path)
            if tail is None:
                tail = self._tails[path] = JsonlTail(path)
            self._tails.move_to_end(path)
            while len(self._tails) > MAX_TAILS:
                self._tails.popitem(last=False)
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

    def _bad_lines(self, s: Session) -> int:
        with self._lock:
            return sum(t.bad_lines for p, t in self._tails.items() if p in (s.spec, s.events))

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
        out = self._outcome(s, len(lines), len(applied), fallbacks,
                            sum(1 for e in events if e.get("type") == "decision"),
                            lines[-1].get("state_after") if lines else None, start, end, final)
        out["timing"] = timing_stats(lines)
        return out

    def _outcome(self, s: Session, n_lines: int, n_applied: int, fallbacks: int, decisions: int,
                 last_state: Any, start: dict | None, end: dict | None, final: Any) -> dict:
        final = final if isinstance(final, dict) else None
        state = last_state if n_lines else (final or {}).get("state")
        state = state if isinstance(state, dict) else {}
        reported_won = (end or {}).get("won", (final or {}).get("won"))
        out: dict[str, Any] = {
            "game": s.game,
            "lines": n_lines,
            "steps": n_applied,
            "rejected": n_lines - n_applied,
            "fallbacks": fallbacks,
            "fallback_share": round(fallbacks / n_applied, 4) if n_applied else 0.0,
            "final_score": (final or {}).get("score", (end or {}).get("score")),
            "done": final is not None or end is not None,
            "won": reported_won,
            "decisions": decisions,
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
        elif s.game == "doom":
            # The last line's state_after is the engine's variables, or the episode result once it ended
            f = final or {}
            settings = f.get("settings") or (start or {}).get("settings") or {}
            out.update(kills=int(f.get("kills", state.get("kills") or 0)), health=f.get("health", state.get("health")),
                       dead=bool(f.get("dead", state.get("dead", False))),
                       exited=bool(f.get("exited", state.get("exited", False))),
                       items=f.get("items", state.get("items")), explored=f.get("explored_cells"),
                       scenario=settings.get("scenario"))
            out["won"] = out["exited"] if out["done"] else None
            computed = None
        else:
            computed = None
        reported = (end or {}).get("points")
        has_reported = isinstance(reported, (int, float)) and not isinstance(reported, bool)
        out["points_computed"] = computed
        out["points"] = reported if has_reported else computed
        out["points_source"] = "session_end" if has_reported else "computed"
        out["agent_name"] = (start or {}).get("agent_name")
        start = start or {}
        kind = env_kind(start)
        if s.game == "doom" and kind == "unknown":
            kind = "engine"  # stage 3 runs in our own copy of the engine, never on the hosted arena
        out.update(env=start.get("env"), env_kind=kind, source=session_source(kind, s.origin), model=start.get("model"),
                   model_source=start.get("model_source"), device=start.get("device"), design=start.get("design"),
                   started_ts=start.get("ts"), ended_ts=(end or {}).get("ts"), key=s.key or s.session_id)
        return out

    def _light(self, s: Session) -> dict:
        """List-row summary from raw bytes, so listing 150 simulator sessions never parses every line."""
        stats = []
        for path in (s.spec, s.events, s.final):
            try:
                st = path.stat()
                stats.append((st.st_mtime_ns, st.st_size))
            except OSError:
                stats.append(None)
        key = tuple(stats)
        with self._lock:
            cached = self._lights.get(s.key)
            if cached and cached[0] == key:
                return cached[1]

        def complete_lines(path: Path) -> list[bytes]:
            try:
                data = path.read_bytes()
            except OSError:
                return []
            data = data[: data.rfind(b"\n") + 1]
            return [raw for raw in data.split(b"\n") if raw.strip()]

        def parse(raw: bytes) -> dict | None:
            try:
                obj = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None
            return obj if isinstance(obj, dict) else None

        def applied_fallback(raw: bytes) -> bool:
            line = parse(raw) or {}
            return line.get("result") == "applied" and (line.get("decision") or {}).get("source") == "fallback"

        lines = complete_lines(s.spec)
        events = complete_lines(s.events)
        n_applied = sum(1 for raw in lines if b'"result":"applied"' in raw)
        # Fallback lines are rare, so only those are parsed to check they were applied
        fallbacks = sum(1 for raw in lines if b'"source":"fallback"' in raw and applied_fallback(raw))
        decisions = sum(1 for raw in events if b'"type": "decision"' in raw or b'"type":"decision"' in raw)
        last = parse(lines[-1]) if lines else None
        first_event = parse(events[0]) if events else None
        start = first_event if (first_event or {}).get("type") == "session_start" else None
        end = None
        for raw in reversed(events[-5:]):
            ev = parse(raw) if b"session_end" in raw else None
            if ev and ev.get("type") == "session_end":
                end = ev
                break
        if s.game is None:
            s.game = (last or {}).get("game") or (start or {}).get("game")
        out = self._outcome(s, len(lines), n_applied, fallbacks, decisions, (last or {}).get("state_after"),
                            start, end, self._final(s.final))
        with self._lock:
            self._lights[s.key] = (key, out)
        return out

    def sessions(self) -> list[dict]:
        found = sorted(self.scan().values(), key=lambda s: s.mtime(), reverse=True)[:MAX_SESSIONS]
        now = time.time()
        out = []
        for s in found:
            summ = self._light(s)
            score = summ["final_score"]
            if score is None:
                score = summ.get("score", summ.get("foods"))
            mtime = s.mtime()
            age = round(now - mtime, 1)
            out.append({"game": summ["game"], "session_id": s.session_id, "mtime": mtime, "age_s": age,
                        "steps": summ["steps"], "last_score": score, "points": summ["points"],
                        "done": summ["done"], "won": summ["won"], "agent_name": summ["agent_name"],
                        "status": session_status(summ["done"], age), "env": summ["env"],
                        "env_kind": summ["env_kind"], "model": summ["model"], "model_source": summ["model_source"],
                        "device": summ["device"], "design": summ["design"], "lines": summ["lines"],
                        "rejected": summ["rejected"], "fallbacks": summ["fallbacks"],
                        "fallback_share": summ["fallback_share"], "decisions": summ["decisions"],
                        "final_score": summ["final_score"], "points_source": summ["points_source"],
                        "started_ts": summ["started_ts"], "folder": s.folder.name, "key": s.key,
                        "source": summ["source"], "origin": s.origin, "kills": summ.get("kills")})
        return out

    def _paired(self, s: Session, lines: list[dict], events: list[dict]) -> tuple[list[dict], dict | None]:
        key = (len(lines), len(events), lines[-1].get("hash") if lines else None,
               lines[0].get("hash") if lines else None, events[-1].get("ts") if events else None)
        with self._lock:
            cached = self._records.get(s.spec)
            if cached and cached[0] == key:
                return cached[1], cached[2]
        paired, pending = pair_decisions(lines, events)
        errors: dict[Any, deque] = {}
        for e in events:
            if e.get("type") == "rejected":
                errors.setdefault((e.get("step"), e.get("action")), deque()).append(e.get("error"))
        records = []
        for i, (line, ev) in enumerate(zip(lines, paired)):
            err = None
            if line.get("result") == "rejected":
                q = errors.get((line.get("step"), line.get("action")))
                err = q.popleft() if q else None
            records.append(step_record(i, line, ev, err))
        with self._lock:
            self._records[s.spec] = (key, records, pending)
            self._records.move_to_end(s.spec)
            while len(self._records) > MAX_RECORD_SETS:
                self._records.popitem(last=False)
        return records, pending

    def history(self, sid: str, after: int = 0, limit: int = HISTORY_PAGE) -> dict | None:
        """Compact per-line records (line + its decision event), paged forward from `after`."""
        s = self._get(sid)
        if s is None:
            return None
        lines, events, final = self._read(s)
        records, pending = self._paired(s, lines, events)
        reset = after > len(records) or after < 0
        if reset:
            after = 0
        page = records[after: after + max(1, limit)]
        start = next((e for e in events if e.get("type") == "session_start"), None)
        end = next((e for e in reversed(events) if e.get("type") == "session_end"), None)
        summary = self.summarize(s, lines, events, final)
        mtime = s.mtime()
        age = round(time.time() - mtime, 1)
        return {
            "session_id": s.session_id,
            "key": s.key,
            "source": summary["source"],
            "game": s.game,
            "folder": str(s.folder),
            "reset": reset,
            "after": after,
            "next_after": after + len(page),
            "total": len(records),
            "records": page,
            "pending": pending,
            "events_count": len(events),
            "bad_lines": self._bad_lines(s),
            "session_start": start,
            "session_end": end,
            "final": final,
            "summary": summary,
            "status": session_status(summary["done"], age),
            "live_window_s": LIVE_WINDOW_S,
            "interrupted_after_s": INTERRUPTED_AFTER_S,
            "mtime": mtime,
            "age_s": age,
        }

    def step(self, sid: str, i: int) -> dict | None:
        """One full submission line with its decision event and the question asked per direction."""
        s = self._get(sid)
        if s is None:
            return None
        lines, events, _ = self._read(s)
        if not 0 <= i < len(lines):
            return None
        paired, _ = pair_decisions(lines, events)
        line, ev = lines[i], paired[i]
        return {"session_id": s.session_id, "i": i, "line": line, "event": ev,
                "questions_by_dir": questions_by_direction(line, ev)}

    def session(self, sid: str, after: int = 0, eafter: int = 0, limit: int = MAX_LINES_PER_POLL) -> dict | None:
        s = self._get(sid)
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
        summary = self.summarize(s, lines, events, final)
        age = round(time.time() - mtime, 1)
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
            "summary": summary,
            "status": session_status(summary["done"], age),
            "mtime": mtime,
            "age_s": age,
        }

    def verify(self, sid: str, replay: bool = False) -> dict | None:
        s = self._get(sid)
        if s is None:
            return None
        if s.game is None:
            self._read(s)
        doom = s.game == "doom"
        try:
            data = s.spec.read_bytes()
        except OSError:
            data = b""
        cut = data.rfind(b"\n") + 1
        if cut == 0:
            return {"ok": None, "pending": True, "problems": [], "lines": 0, "chain_ok": None}
        final = self._final(s.final)
        final = final if isinstance(final, dict) else None
        # A Doom final record is the episode result, not an arena response, so the chain is checked on its own
        # and the recording checks below compare the log with the final record
        kw = {"keys": log_keys(s.spec)} if doom else {}
        against = None if doom else final
        if cut == len(data):
            result = verify_log(s.spec, against, **kw)
        else:
            # A line is being appended right now; check the complete lines only
            fd, tmp = tempfile.mkstemp(suffix=".jsonl")
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data[:cut])
                result = verify_log(tmp, against, **kw)
            finally:
                os.unlink(tmp)
        result["chain_ok"] = not any("hash" in p for p in result.get("problems", []))
        result["pending"] = False
        if doom:
            rec = recording_checks(s.folder, s.session_id, final, result.get("applied"), replay)
            result["checks"] = {"hash chain, step order and decision blocks": not result["problems"], **rec["checks"]}
            result["replay"] = rec["replay"]
            result["problems"] = result["problems"] + [f"{k}: no" for k, ok in rec["checks"].items() if not ok]
            result["ok"] = not result["problems"]
            result["frames"] = has_frames(s.folder, s.session_id)
        return result


def make_handler(store: RunStore, board: Leaderboard | None = None):
    board = board or Leaderboard()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # keep the console for the bot
            pass

        def _send(self, code: int, body: bytes, ctype: str, cache: str = "no-store") -> None:
            try:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", cache)
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def _json(self, code: int, obj: Any) -> None:
            self._send(code, json.dumps(obj, default=str).encode("utf-8"), "application/json")

        def _app_file(self, path: str) -> bool:
            # Built dashboard files: /assets/<name> (content-hashed, cacheable) or a top-level file such as favicon.svg
            parts = [p for p in path.split("/") if p]
            if not parts or len(parts) > 2 or (len(parts) == 2 and parts[0] != "assets"):
                return False
            if not all(SAFE_ASSET.match(p) for p in parts):
                return False
            target = APP_DIST.joinpath(*parts)
            ctype = ASSET_TYPES.get(target.suffix.lower())
            if ctype is None or not target.is_file():
                return False
            cache = "public, max-age=31536000, immutable" if parts[0] == "assets" else "no-store"
            self._send(200, target.read_bytes(), ctype, cache)
            return True

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

            if url.path in ("/doom", "/doom/"):
                # The Doom view lives in the dashboard, next to Snake and 2048
                self.send_response(302)
                self.send_header("Location", "/#/arena?g=doom")
                self.send_header("Content-Length", "0")
                self.end_headers()
            elif url.path == "/api/frame":
                s = store.find(arg("id"))
                img = frame_bytes(s.folder, s.session_id, arg("step", "latest")) if s else None
                if img is None:
                    self._send(404, b"no frame", "text/plain")
                else:
                    self._send(200, img, "image/jpeg")
            elif url.path in APP_PAGES and (APP_DIST / "index.html").is_file():
                self._send(200, (APP_DIST / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif url.path in STATIC_FILES:
                name, ctype = STATIC_FILES[url.path]
                self._send(200, (STATIC / name).read_bytes(), ctype)
            elif not url.path.startswith("/api/") and self._app_file(url.path):
                pass
            elif url.path == "/api/leaderboard":
                game = arg("game")
                if not SAFE_GAME.match(game):
                    self._json(400, {"error": f"bad game name {game!r}"})
                    return
                body = board.get(game)
                # gameId is the arena session id: point matching rows at the local copy (main runs folder first)
                local: dict[str, str] = {}
                for s in store.scan().values():
                    local.setdefault(s.session_id, s.key)
                ids = {str(r.get("gameId")) for r in body["leaderboard"]}
                body["local"] = {gid: key for gid, key in local.items() if gid in ids}
                self._json(200, body)
            elif url.path == "/api/history":
                sid = arg("id")
                body = store.history(sid, int_arg("after", 0), int_arg("limit", HISTORY_PAGE)) if sid else None
                if body is None:
                    self._json(404, {"error": f"unknown session {sid!r}"})
                else:
                    self._json(200, body)
            elif url.path == "/api/step":
                sid = arg("id")
                body = store.step(sid, int_arg("i", -1)) if sid else None
                if body is None:
                    self._json(404, {"error": f"unknown session or line {sid!r} {arg('i')!r}"})
                else:
                    self._json(200, body)
            elif url.path == "/api/sessions":
                items = store.sessions()
                self._json(200, {"root": str(store.root.resolve()), "sessions": items,
                                 "newest": items[0]["session_id"] if items else None,
                                 "newest_key": items[0]["key"] if items else None,
                                 "sim_roots": [str(r.resolve()) for r in store.sim_roots]})
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
                body = store.verify(arg("id"), replay=arg("replay") == "1")
                if body is None:
                    self._json(404, {"error": f"unknown session {arg('id')!r}"})
                else:
                    self._json(200, body)
            else:
                self._send(404, b"not found", "text/plain")

    return Handler


def resolve_sim_roots(patterns: list[str]) -> list[Path]:
    roots: list[Path] = []
    for pattern in patterns:
        for match in sorted(glob.glob(pattern)):
            path = Path(match)
            if path.is_dir() and path not in roots:
                roots.append(path)
    return roots


def make_server(root: str | Path, host: str = "127.0.0.1", port: int = 8770,
                sim_roots: list[str | Path] | None = None) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), make_handler(RunStore(root, sim_roots)))
    server.daemon_threads = True
    return server


def main() -> None:
    ap = argparse.ArgumentParser(description="Live Laya decision viewer for arena runs")
    ap.add_argument("runs", nargs="?", default="runs", help="runs folder (default: runs)")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--sim-roots", action="append", default=[], metavar="GLOB",
                    help='read-only simulator folders, a glob relative to the working directory, e.g. "runs_sim*"')
    args = ap.parse_args()
    sims = resolve_sim_roots(args.sim_roots)
    server = make_server(args.runs, args.host, args.port, sims)
    host, port = server.server_address[:2]
    print(f"arena viewer on http://{host}:{port}  (runs: {Path(args.runs).resolve()}, "
          f"simulator folders: {len(sims)})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
