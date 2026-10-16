"""Doom pieces of the dashboard that the arena games do not have: screen frames and the recording proof.

Doom sessions are listed, paged and verified by the same RunStore as Snake and 2048 (their logs use the same
fields and hash rule, with Doom's action names as the probability keys). This module adds the screen captures
(<id>.frames/<step>.jpg) and the checks on the engine's demo recording, including an optional replay.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ACTIONS = ("shoot", "turn_left", "turn_right", "turn_left_big", "turn_right_big", "turn_around",
           "forward", "backward", "strafe_left", "strafe_right", "use")


def log_keys(spec: Path) -> tuple[str, ...]:
    """The action names a Doom log was written with (logs before the turn-around action have ten)."""
    try:
        with open(spec, encoding="utf-8") as fh:
            first = json.loads(fh.readline())
        keys = tuple((first.get("decision") or {}).get("probabilities") or ())
    except (OSError, ValueError):
        return ACTIONS
    return keys if keys and set(keys) <= set(ACTIONS) else ACTIONS


def frame_bytes(folder: Path, sid: str, step: str) -> bytes | None:
    """The screen Laya saw at a step (saved before the action), or the newest one for step "latest"."""
    frames = folder / f"{sid}.frames"
    try:
        name = "latest.jpg" if step == "latest" else f"{int(step):05d}.jpg"
        return (frames / name).read_bytes()
    except (OSError, ValueError):
        return None


def has_frames(folder: Path, sid: str) -> bool:
    return (folder / f"{sid}.frames").is_dir()


def recording_checks(folder: Path, sid: str, final: dict | None, applied: int | None, replay: bool = False) -> dict[str, Any]:
    """Checks on the demo recording: its sha256 against the final record, the step count, and (on request) a
    replay in the engine that must reproduce the kills and how the episode ended."""
    out: dict[str, Any] = {"checks": {}, "replay": None}
    if not final:
        return out
    lmp = folder / f"{sid}.lmp"
    sha = hashlib.sha256(lmp.read_bytes()).hexdigest() if lmp.exists() else None
    out["checks"]["recording matches its sha256"] = bool(sha) and sha == final.get("recording_sha256")
    out["checks"]["steps match the recorded episode"] = final.get("steps") == applied
    if replay and lmp.exists():
        from ..doom.engine import replay as play_back

        st = final.get("settings") or {}
        r = play_back(st.get("scenario", "freedoom1:E1M1"), str(lmp), skill=st.get("skill", 3), seed=st.get("seed", 0))
        out["replay"] = {k: r[k] for k in ("kills", "items", "secrets", "health", "dead", "exited", "tic")}
        out["checks"]["engine replay reproduces the result"] = all(r[k] == final.get(k) for k in ("kills", "dead", "exited"))
    return out
