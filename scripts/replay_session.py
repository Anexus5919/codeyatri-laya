"""Replays a recorded session into another runs folder line by line, to test the live viewer without a GPU.

The lines are copied byte for byte, so the hash chain still verifies and the env label stays what the
original run wrote (a LOCAL_SIM session stays a simulator session, a HOSTED one stays hosted).
Order follows the runner: decision event first, then the submission line, then any rejected/reconcile event.

Usage:
  python scripts/replay_session.py runs/snake/<session_id>.jsonl C:/Temp/dash_dev/runs --pace 0.8
  python scripts/replay_session.py <spec.jsonl> <target_runs> --stop-after 40   # leaves an unfinished session
  python scripts/replay_session.py <spec.jsonl> <target_runs> --realtime         # use the logged turn_ms
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def read_lines(path: Path) -> list[bytes]:
    if not path.exists():
        return []
    return [raw for raw in path.read_bytes().split(b"\n") if raw.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Replay a recorded arena session into another runs folder")
    ap.add_argument("spec", help="the session's submission log, <runs>/<game>/<session_id>.jsonl")
    ap.add_argument("target", help="runs folder to write into (never the repo's runs/ folder)")
    ap.add_argument("--pace", type=float, default=0.8, help="seconds per move (default 0.8)")
    ap.add_argument("--realtime", action="store_true", help="wait the logged turn_ms between moves instead of --pace")
    ap.add_argument("--start-delay", type=float, default=0.0, help="seconds to wait after session_start")
    ap.add_argument("--stop-after", type=int, default=None, help="stop after this many submission lines, without session_end")
    ap.add_argument("--replace", action="store_true", help="delete an earlier replay of this session in the target first")
    args = ap.parse_args(argv)

    spec = Path(args.spec).resolve()
    if not spec.name.endswith(".jsonl") or spec.name.endswith(".events.jsonl"):
        ap.error("spec must be the <session_id>.jsonl submission log")
    sid = spec.name[: -len(".jsonl")]
    src_events = spec.with_name(f"{sid}.events.jsonl")
    src_final = spec.with_name(f"{sid}.final.json")
    lines = read_lines(spec)
    events = read_lines(src_events)
    if not lines or not events:
        ap.error("both the submission log and its events log are needed")
    game = json.loads(lines[0]).get("game") or "unknown"

    target_root = Path(args.target).resolve()
    if target_root == (REPO / "runs").resolve() or (REPO / "runs").resolve() in target_root.parents:
        ap.error("refusing to write into the repo's runs/ folder, it holds real results")
    folder = target_root / game
    if folder == spec.parent:
        ap.error("target is the source folder")
    folder.mkdir(parents=True, exist_ok=True)
    out_spec = folder / f"{sid}.jsonl"
    out_events = folder / f"{sid}.events.jsonl"
    out_final = folder / f"{sid}.final.json"
    existing = [p for p in (out_spec, out_events, out_final) if p.exists()]
    if existing and not args.replace:
        ap.error(f"{existing[0]} exists; pass --replace to start this replay again")
    for p in existing:
        p.unlink()

    spec_fh = open(out_spec, "ab")
    ev_fh = open(out_events, "ab")

    def put(fh, raw: bytes) -> None:
        fh.write(raw + b"\n")
        fh.flush()

    next_line = 0
    written = 0
    stopped = False
    try:
        for n, raw in enumerate(events):
            ev = json.loads(raw)
            kind = ev.get("type")
            if kind == "session_end":
                continue
            put(ev_fh, raw)
            if kind == "session_start":
                print(f"replaying {sid} ({game}, env {ev.get('env')}, agent {ev.get('agent_name')}) into {folder}", flush=True)
                time.sleep(args.start_delay)
                continue
            if kind != "decision" or next_line >= len(lines):
                continue
            after = json.loads(events[n + 1]) if n + 1 < len(events) else {}
            if after.get("type") == "reconcile" and after.get("verdict") == "not_applied":
                continue  # this decision never became a line
            line = json.loads(lines[next_line])
            if line.get("step") != ev.get("step") or line.get("action") != ev.get("chosen"):
                continue
            wait = (line.get("timing") or {}).get("turn_ms", 0) / 1000 if args.realtime else args.pace
            time.sleep(max(0.0, wait) * 0.5)  # deciding
            put(spec_fh, lines[next_line])
            next_line += 1
            written += 1
            print(f"  line {written:>4}  step {line.get('step'):>4}  {line.get('action'):>5}  {line.get('result')}", flush=True)
            if args.stop_after is not None and written >= args.stop_after:
                stopped = True
                break
            time.sleep(max(0.0, wait) * 0.5)  # waiting for the game
        if not stopped:
            for raw in events:
                if json.loads(raw).get("type") == "session_end":
                    if src_final.exists():
                        out_final.write_bytes(src_final.read_bytes())
                    put(ev_fh, raw)
            print(f"done: {written} lines, session_end written", flush=True)
        else:
            print(f"stopped after {written} lines without session_end (an unfinished session)", flush=True)
    except KeyboardInterrupt:
        print(f"interrupted after {written} lines", flush=True)
    finally:
        spec_fh.close()
        ev_fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
