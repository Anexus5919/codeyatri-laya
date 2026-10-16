"""Proof check for one session: our log versus the arena server's own record.

Usage:
  python -m laya_agent.arena.verify runs/snake/<session_id>.jsonl
  python -m laya_agent.arena.verify <session_id>            (looks in runs/*/)

Checks the log locally (hash chain, contiguous steps, every decision block, fallback share),
then asks the arena server for the same session and compares steps, score, outcome and the
final board with the last line of the log. Prints where the public record can be opened.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .client import BASE_URL, ArenaClient
from .spec_log import verify_log


def find_log(arg: str) -> Path:
    p = Path(arg)
    if p.suffix == ".jsonl" and p.exists():
        return p
    hits = [h for h in Path("runs").glob(f"*/{arg}*.jsonl") if not h.name.endswith(".events.jsonl")]
    if not hits:
        raise SystemExit(f"no log found for {arg!r} under runs/")
    return hits[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("session", help="path to <session_id>.jsonl, or a session id (prefix)")
    ap.add_argument("--offline", action="store_true", help="skip the server comparison")
    args = ap.parse_args(argv)

    log = find_log(args.session)
    sid = log.name[: -len(".jsonl")]
    local = verify_log(log)
    lines = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]
    sources = {}
    for ln in lines:
        s = ln["decision"]["source"]
        sources[s] = sources.get(s, 0) + 1

    print(f"Session {sid} ({local.get('game')})")
    print(f"  log file          {log}")
    print(f"  lines             {local.get('lines')} ({local.get('applied')} applied)")
    print(f"  decided by        {', '.join(f'{k}: {v}' for k, v in sorted(sources.items()))}")
    print(f"  hash chain/rules  {'OK' if local['ok'] else 'PROBLEMS'}")
    for p in local["problems"]:
        print(f"    - {p}")

    ok = local["ok"]
    if not args.offline:
        code, server = ArenaClient().get(sid)
        if code != 200 or "session_id" not in server:
            print(f"  arena server      could not read the session (HTTP {code})")
            return 1
        last = lines[-1] if lines else {}
        applied_last = next((ln for ln in reversed(lines) if ln["result"] == "applied"), {})
        checks = {
            "steps match": server.get("steps") == local.get("applied"),
            "final board matches last line": server.get("state") == applied_last.get("state_after"),
            "same game": server.get("game") == local.get("game"),
        }
        print(f"  arena server      steps {server.get('steps')}, score {server.get('score')}, "
              f"done {server.get('done')}, won {server.get('won')}")
        for name, good in checks.items():
            print(f"    {'OK ' if good else 'NO '} {name}")
        ok = ok and all(checks.values())
        print(f"  public record     {BASE_URL}/sessions/{sid}")
        print(f"  leaderboard       {BASE_URL}/leaderboard/{local.get('game')}")
        if last and last.get("result") != "applied":
            print("  note: the last line is a rejected move; the server board is compared with the last applied move")
    print("RESULT:", "VERIFIED" if ok else "NOT VERIFIED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
