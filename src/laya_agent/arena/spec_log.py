"""Submission log in the exact format of the PS 02 participant guide (section 3).

One JSON object per line: one per applied move, plus one per rejected move marked "rejected".
Each line is hash-chained: hash = sha256(prev_hash + "|" + canonical JSON of the line without "hash").
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DIRECTIONS = ("up", "down", "left", "right")
REQUIRED = ("session_id", "game", "step", "state_before", "action", "state_after", "result",
            "decision", "timing", "ts", "prev_hash", "hash")


def canonical_json(obj: Any) -> str:
    # Keys sorted, no spaces, UTF-8, and NaN/Infinity refused (allow_nan=False raises on them)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def line_hash(prev_hash: str, line_without_hash: dict) -> str:
    text = prev_hash + "|" + canonical_json(line_without_hash)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def genesis_hash(session_id: str) -> str:
    return f"GENESIS-{session_id}"


def decision_problems(decision: dict, action: str, keys: tuple[str, ...] = DIRECTIONS) -> list[str]:
    """Checks section 3.2 for one decision block (keys: the game's action names, up/down/left/right by default)."""
    out = []
    probs = decision.get("probabilities")
    if not isinstance(probs, dict) or set(probs) != set(keys):
        out.append(f"probabilities must have exactly the keys {', '.join(keys)}")
        return out
    vals = list(probs.values())
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) or math.isnan(v) or v < 0 or v > 1 for v in vals):
        out.append("probabilities must be numbers from 0 to 1")
    elif not 0.98 <= sum(vals) <= 1.02:
        out.append(f"probabilities sum to {sum(vals):.4f}, not 0.98 to 1.02")
    if decision.get("chosen") != action:
        out.append("chosen must equal action")
    if decision.get("chosen") in probs and decision.get("confidence") != probs[decision["chosen"]]:
        out.append("confidence must equal probabilities[chosen]")
    if decision.get("source") not in ("laya", "fallback"):
        out.append("source must be laya or fallback")
    q = decision.get("questions")
    if not isinstance(q, list) or not q or not all(isinstance(x, str) and x for x in q):
        out.append("questions must be a non-empty list of question texts")
    return out


class SpecLog:
    """Append-only, fsynced, hash-chained submission log for one game session."""

    def __init__(self, path: str | Path, session_id: str, game: str, keys: tuple[str, ...] = DIRECTIONS) -> None:
        self.path = Path(path)
        self.keys = tuple(keys)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id
        self.game = game
        self.prev_hash = genesis_hash(session_id)
        self.lines = 0
        self.applied = 0
        self.fallbacks = 0
        if self.path.exists() and self.path.stat().st_size:
            raise FileExistsError(f"{self.path} already exists; a session log is never rewritten")
        self._fh = open(self.path, "a", encoding="utf-8", newline="\n")

    def write(self, *, step: int, state_before: Any, action: str, state_after: Any, result: str,
              decision: dict, timing: dict) -> dict:
        if result not in ("applied", "rejected"):
            raise ValueError("result must be applied or rejected")
        problems = decision_problems(decision, action, getattr(self, "keys", DIRECTIONS))
        if problems:
            raise ValueError(f"decision block breaks section 3.2: {problems}")
        line = {
            "session_id": self.session_id,
            "game": self.game,
            "step": int(step),
            "state_before": state_before,
            "action": action,
            "state_after": state_after,
            "result": result,
            "decision": decision,
            "timing": {k: int(timing[k]) for k in ("decide_ms", "api_ms", "turn_ms")},
            "ts": utc_ts(),
            "prev_hash": self.prev_hash,
        }
        line["hash"] = line_hash(self.prev_hash, line)
        self._fh.write(canonical_json(line) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())
        self.prev_hash = line["hash"]
        self.lines += 1
        if result == "applied":
            self.applied += 1
            if decision.get("source") == "fallback":
                self.fallbacks += 1
        return line

    @classmethod
    def resume(cls, path: str | Path, session_id: str, game: str) -> tuple["SpecLog", list[dict], str | None]:
        """Reopens an existing session log to continue it after a crash.

        Every complete line must verify (hash chain, steps, decision blocks). A torn last line (a
        crash in the middle of a write) is moved to `<log>.torn` and reported, never kept.
        Returns (log, lines, torn_text).
        """
        path = Path(path)
        raw = path.read_text(encoding="utf-8") if path.exists() else ""
        torn = None
        if raw and not raw.endswith("\n"):
            cut = raw.rfind("\n") + 1
            torn = raw[cut:]
            Path(str(path) + ".torn").write_text(torn, encoding="utf-8")
            with open(path, "r+", encoding="utf-8", newline="\n") as fh:
                fh.truncate(len(raw[:cut].encode("utf-8")))
            raw = raw[:cut]
        lines = [json.loads(x) for x in raw.splitlines() if x.strip()]
        if lines:
            report = verify_log(path)
            chain_problems = [p for p in report["problems"] if "fallback share" not in p]
            if chain_problems:
                raise ValueError(f"cannot resume, the existing log does not verify: {chain_problems}")
            if lines[0]["session_id"] != session_id or lines[0]["game"] != game:
                raise ValueError("cannot resume, the log belongs to another session or game")
        obj = cls.__new__(cls)
        obj.path, obj.session_id, obj.game = path, session_id, game
        obj.prev_hash = lines[-1]["hash"] if lines else genesis_hash(session_id)
        obj.lines = len(lines)
        applied = [ln for ln in lines if ln["result"] == "applied"]
        obj.applied = len(applied)
        obj.fallbacks = sum(1 for ln in applied if ln["decision"].get("source") == "fallback")
        obj._fh = open(path, "a", encoding="utf-8", newline="\n")
        return obj, lines, torn

    @property
    def fallback_share(self) -> float:
        return self.fallbacks / self.applied if self.applied else 0.0

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()


def save_final_response(folder: str | Path, session_id: str, response: Any) -> Path:
    """Section 3.5: keep the game's final response as soon as the game ends."""
    p = Path(folder) / f"{session_id}.final.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(response, fh, indent=2, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    return p


def verify_log(path: str | Path, final_response: dict | None = None, keys: tuple[str, ...] = DIRECTIONS) -> dict:
    """Checks a log the way section 5.1 describes a verified run (parts we can check locally)."""
    problems: list[str] = []
    lines: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for n, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                lines.append(json.loads(raw))
            except json.JSONDecodeError:
                problems.append(f"line {n}: not valid JSON")
    if not lines:
        return {"ok": False, "problems": ["log is empty"], "lines": 0}

    session_id = lines[0].get("session_id")
    prev = genesis_hash(str(session_id))
    expected_step = 1
    applied = fallbacks = 0
    for n, line in enumerate(lines, 1):
        missing = [k for k in REQUIRED if k not in line]
        if missing:
            problems.append(f"line {n}: missing {missing}")
            continue
        if line["session_id"] != session_id:
            problems.append(f"line {n}: session_id changes inside one log")
        if line["prev_hash"] != prev:
            problems.append(f"line {n}: prev_hash does not match the previous line")
        body = {k: v for k, v in line.items() if k != "hash"}
        if line_hash(line["prev_hash"], body) != line["hash"]:
            problems.append(f"line {n}: hash does not match its content")
        prev = line["hash"]
        problems += [f"line {n}: {p}" for p in decision_problems(line["decision"], line["action"], keys)]
        if line["result"] == "applied":
            if line["step"] != expected_step:
                problems.append(f"line {n}: step {line['step']}, expected {expected_step}")
            expected_step += 1
            applied += 1
            fallbacks += line["decision"].get("source") == "fallback"
        elif line["result"] == "rejected":
            if line["step"] != expected_step:
                problems.append(f"line {n}: rejected line step {line['step']}, expected {expected_step}")
        else:
            problems.append(f"line {n}: result must be applied or rejected")

    share = fallbacks / applied if applied else 0.0
    if share > 0.10:
        problems.append(f"fallback share {share:.1%} is above 10%")

    last = lines[-1]
    summary = {"session_id": session_id, "game": last.get("game"), "lines": len(lines), "applied": applied,
               "fallbacks": fallbacks, "fallback_share": round(share, 4),
               "last_state_after": last.get("state_after")}
    if final_response is not None:
        if final_response.get("session_id") != session_id:
            problems.append("final response is for another session")
        if final_response.get("steps") != applied:
            problems.append(f"final steps {final_response.get('steps')} != applied lines {applied}")
        if final_response.get("state") != last.get("state_after"):
            problems.append("final state does not match the last line's state_after")
        summary["final_score"] = final_response.get("score")
        summary["final_done"] = final_response.get("done")
    return {"ok": not problems, "problems": problems, **summary}
