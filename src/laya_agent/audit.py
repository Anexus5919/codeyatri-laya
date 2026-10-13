"""Audit a decision log: every submitted move must trace to an earlier, valid Laya decision.

Usage: python -m laya_agent.audit logs/<run>.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .telemetry.jsonl import read_events


def audit_events(events: list[dict]) -> dict:
    decisions: dict[str, dict] = {}
    problems: list[str] = []
    submissions = 0
    seqs = [e.get("seq") for e in events]
    if seqs != sorted(seqs) or len(set(seqs)) != len(seqs):
        problems.append("event sequence numbers are not strictly increasing")
    run_ids = {e.get("run_id") for e in events}
    if len(run_ids) > 1:
        problems.append(f"log mixes runs: {sorted(map(str, run_ids))}")
    envs = {e.get("env") for e in events}

    for e in events:
        if e.get("type") == "decision":
            decisions[e.get("decision_id")] = e
        elif e.get("type") == "submission":
            submissions += 1
            d = decisions.get(e.get("decision_id"))
            if d is None:
                problems.append(f"seq {e.get('seq')}: submission without an earlier decision event")
                continue
            if not d.get("valid"):
                problems.append(f"seq {e.get('seq')}: submission of a decision that failed validation")
            if d.get("chosen_action_id") != e.get("action_id"):
                problems.append(
                    f"seq {e.get('seq')}: submitted {e.get('action_id')!r} but Laya chose {d.get('chosen_action_id')!r}"
                )
            if not d.get("laya_response"):
                problems.append(f"seq {e.get('seq')}: decision has no recorded Laya response")

    final = next((e for e in reversed(events) if e.get("type") == "run_end"), None)
    return {
        "events": len(events),
        "decisions": len(decisions),
        "submissions": submissions,
        "env": sorted(map(str, envs)),
        "final": {k: final.get(k) for k in ("status", "final_score", "session")} if final else None,
        "ok": not problems,
        "problems": problems,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    args = ap.parse_args()
    report = audit_events(read_events(Path(args.log)))
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
