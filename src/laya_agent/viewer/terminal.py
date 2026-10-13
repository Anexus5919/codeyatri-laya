"""Terminal viewer: renders log events as they are written, or follows a log file."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import TextIO

BAR = 20


def _bar(p: float) -> str:
    n = max(0, min(BAR, round(p * BAR)))
    return "#" * n + "." * (BAR - n)


def render(event: dict) -> str:
    t = event.get("type")
    head = f"[{event.get('seq', '?'):>4}] {event.get('env', '')[:5]:5} {t}"
    if t == "decision":
        lines = [
            f"{head} turn={event.get('turn_id')} design={event.get('design_id')} model={event.get('model')} "
            f"latency={event.get('latency_ms')}ms valid={event.get('valid')}"
        ]
        probs = event.get("probabilities") or {}
        chosen = event.get("chosen_action_id")
        for action, p in sorted(probs.items(), key=lambda kv: -kv[1]):
            mark = ">" if action == chosen else " "
            lines.append(f"       {mark} {action:<16} {_bar(p)} {p:.4f}")
        lines.append(f"         answer_confidence={event.get('answer_confidence')} confidence={event.get('confidence')}")
        if event.get("validation_problems"):
            lines.append(f"         problems: {event['validation_problems']}")
        return "\n".join(lines)
    if t == "submission":
        return f"{head} turn={event.get('turn_id')} action={event.get('action_id')} status={event.get('status')} {event.get('detail') or ''}"
    if t == "game_over":
        return f"{head} score={event.get('score')} session={event.get('session')}"
    if t == "run_end":
        return (
            f"{head} status={event.get('status')} score={event.get('final_score')} decisions={event.get('decisions')} "
            f"accepted={event.get('moves_accepted')} rejected={event.get('moves_rejected')} latency={event.get('latency_ms')}"
        )
    if t == "run_start":
        return f"{head} run_id={event.get('run_id')} game={event.get('game_id')} design={event.get('design_id')}"
    if t == "model_loaded":
        return f"{head} {event.get('info')}"
    rest = {k: v for k, v in event.items() if k not in ("schema", "seq", "ts", "run_id", "env", "type")}
    return f"{head} {rest}"


class ConsoleSink:
    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout

    def __call__(self, event: dict) -> None:
        print(render(event), file=self.stream, flush=True)


def latest_log(path: str | Path) -> Path:
    p = Path(path)
    if p.is_dir():
        logs = sorted(p.glob("*.jsonl"), key=lambda f: f.stat().st_mtime)
        if not logs:
            raise FileNotFoundError(f"no .jsonl logs in {p}")
        return logs[-1]
    return p


def follow(path: str | Path, poll_s: float = 0.25) -> None:
    """Tail a log like `tail -f`, printing each complete event line once."""
    import json

    target = latest_log(path)
    print(f"following {target}", flush=True)
    with open(target, encoding="utf-8") as fh:
        buf = ""
        while True:
            chunk = fh.readline()
            if not chunk:
                time.sleep(poll_s)
                continue
            buf += chunk
            if not buf.endswith("\n"):
                continue
            line, buf = buf.strip(), ""
            if line:
                try:
                    print(render(json.loads(line)), flush=True)
                except json.JSONDecodeError:
                    pass
