"""Doom sessions for the dashboard: list, live decisions, screen frames and the proof checks.

Served by arena_web under /doom (the page) and /api/doom/* (data). Doom logs live in runs/doom/ (real runs) and in
the simulator roots' doom/ folders (tests); the Snake and 2048 views never see them.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..arena.spec_log import verify_log

ACTIONS = ("shoot", "turn_left", "turn_right", "turn_left_big", "turn_right_big",
           "forward", "backward", "strafe_left", "strafe_right", "use")
STATIC = Path(__file__).with_name("doom_static")


def _read_jsonl(path: Path, after: int = 0) -> list[dict]:
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for i, raw in enumerate(fh):
                if i < after or not raw.endswith("\n"):
                    continue
                try:
                    out.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return out


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


class DoomStore:
    def __init__(self, root: str | Path, sim_roots: list[str | Path] | None = None):
        self.roots = [(Path(root) / "doom", "runs")]
        for r in sim_roots or []:
            r = Path(r)
            self.roots.append((r / "doom", "sim"))
            if r.is_dir():
                self.roots += [(c / "doom", "sim") for c in sorted(p for p in r.iterdir() if p.is_dir())]

    def _find(self) -> dict[str, tuple[Path, str]]:
        found = {}
        for folder, origin in self.roots:
            if not folder.is_dir():
                continue
            for p in folder.glob("doom-*.jsonl"):
                if p.name.endswith(".events.jsonl"):
                    continue
                sid = p.name[: -len(".jsonl")]
                found.setdefault(sid, (folder, origin))
        return found

    def sessions(self) -> list[dict]:
        out = []
        for sid, (folder, origin) in self._find().items():
            final = _json(folder / f"{sid}.final.json")
            spec = folder / f"{sid}.jsonl"
            start = next((e for e in _read_jsonl(folder / f"{sid}.events.jsonl")[:1] if e.get("type") == "session_start"), {})
            row = {"session_id": sid, "origin": origin, "mtime": spec.stat().st_mtime,
                   "settings": (final or {}).get("settings") or start.get("settings") or {},
                   "model_source": (final or start).get("model_source"), "done": final is not None}
            if final:
                row.update({k: final.get(k) for k in ("steps", "kills", "items", "secrets", "health", "dead", "exited",
                                                       "log_verified", "seconds", "explored_cells")})
            else:
                lines = _read_jsonl(spec)
                last = lines[-1]["state_before"] if lines else {}
                row.update({"steps": len(lines), "kills": last.get("kills"), "health": last.get("health")})
            out.append(row)
        return sorted(out, key=lambda r: -r["mtime"])

    def session(self, sid: str, after: int = 0) -> dict | None:
        hit = self._find().get(sid)
        if not hit:
            return None
        folder, origin = hit
        events = [e for e in _read_jsonl(folder / f"{sid}.events.jsonl") if e.get("type") == "decision"]
        lines = _read_jsonl(folder / f"{sid}.jsonl")
        by_step = {ln["step"]: ln for ln in lines}
        decisions = []
        for e in events[after:]:
            ln = by_step.get(e["step"])
            decisions.append({**e, "state_before": ln and ln["state_before"], "state_after": ln and ln["state_after"],
                              "hash": ln and ln["hash"], "timing": ln and ln["timing"]})
        return {"session_id": sid, "origin": origin, "after": after, "total": len(events), "lines": len(lines),
                "decisions": decisions, "final": _json(folder / f"{sid}.final.json"),
                "frames": (folder / f"{sid}.frames").is_dir()}

    def frame(self, sid: str, step: str) -> bytes | None:
        hit = self._find().get(sid)
        if not hit:
            return None
        frames = hit[0] / f"{sid}.frames"
        name = "latest.jpg" if step == "latest" else f"{int(step):05d}.jpg"
        try:
            return (frames / name).read_bytes()
        except (OSError, ValueError):
            return None

    def verify(self, sid: str, replay: bool = False) -> dict | None:
        hit = self._find().get(sid)
        if not hit:
            return None
        folder = hit[0]
        report = verify_log(folder / f"{sid}.jsonl", keys=ACTIONS)
        final = _json(folder / f"{sid}.final.json") or {}
        lmp = folder / f"{sid}.lmp"
        checks = {"hash chain and decision blocks": report["ok"]}
        if final:
            sha = hashlib.sha256(lmp.read_bytes()).hexdigest() if lmp.exists() else None
            checks["recording matches its sha256"] = bool(sha) and sha == final.get("recording_sha256")
            checks["steps match the recording run"] = final.get("steps") == report.get("applied")
        out = {"session_id": sid, "checks": checks, "problems": report["problems"][:20],
               "applied": report.get("applied"), "fallbacks": report.get("fallbacks")}
        if replay and final and lmp.exists():
            from ..doom.engine import replay as play_back

            st = final.get("settings") or {}
            r = play_back(st.get("scenario", "freedoom1:E1M1"), str(lmp), skill=st.get("skill", 3), seed=st.get("seed", 0))
            out["replay"] = {k: r[k] for k in ("kills", "items", "secrets", "health", "dead", "exited", "tic")}
            checks["engine replay reproduces the result"] = all(r[k] == final.get(k) for k in ("kills", "dead", "exited"))
        out["ok"] = all(checks.values())
        return out
