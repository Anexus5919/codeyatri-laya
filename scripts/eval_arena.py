"""Plays N LOCAL SIMULATOR games with real Laya and summarises them (never real arena results).

Usage: python scripts/eval_arena.py --game snake --games 10 --template noul_nodir
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
import time
from pathlib import Path

from laya_agent.arena.decider import LayaMoveDecider
from laya_agent.arena.runner import play_session
from laya_agent.arena.sims import FakeArena


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True, choices=["snake", "2048"])
    ap.add_argument("--games", type=int, default=10)
    ap.add_argument("--seed0", type=int, default=100)
    ap.add_argument("--template", default="noul_nodir")
    ap.add_argument("--offer", default="legal")
    ap.add_argument("--style", default="words")
    ap.add_argument("--runs", default="runs_sim_eval")
    ap.add_argument("--out", default=None)
    ap.add_argument("--model", default="english", help="english | multilingual | typed-decisions | checkpoint path")
    args = ap.parse_args()

    dec = LayaMoveDecider(args.game, model=args.model, template=args.template, offer=args.offer, style=args.style)
    info = dec.load()
    print("load:", info, flush=True)
    rows = []
    for i in range(args.games):
        seed = args.seed0 + i
        t0 = time.perf_counter()
        rep = play_session(FakeArena(seed=seed), dec, args.game, Path(args.runs) / args.template, "SIM-EVAL", info, quiet=True)
        last = rep.get("last_state_after") or {}
        row = {"seed": seed, "points": rep["points"], "won": rep["won"], "steps": rep["applied"],
               "fallbacks": rep["fallbacks"], "fallback_share": rep["fallback_share"], "verified_ok": rep["ok"],
               "seconds": round(time.perf_counter() - t0, 1)}
        if args.game == "snake":
            row["foods"] = last.get("foodEaten")
        else:
            row["best_tile"] = last.get("best")
            row["score"] = last.get("score")
        rows.append(row)
        print(json.dumps(row), flush=True)

    pts = [r["points"] for r in rows]
    summary = {"game": args.game, "template": args.template, "games": len(rows),
               "points_mean": round(statistics.mean(pts), 1), "points_median": statistics.median(pts),
               "points_min": min(pts), "points_max": max(pts),
               "fallback_share_max": max(r["fallback_share"] for r in rows),
               "all_logs_verify": all(r["verified_ok"] for r in rows)}
    if args.game == "snake":
        summary["unlock_rate_600"] = sum(p >= 600 for p in pts) / len(pts)
        summary["wins"] = sum(bool(r["won"]) for r in rows)
    else:
        tiles = collections.Counter(r["best_tile"] for r in rows)
        summary["best_tiles"] = dict(sorted(tiles.items()))
        summary["reach_512_rate"] = sum(r["best_tile"] >= 512 for r in rows) / len(rows)
    print("SUMMARY", json.dumps(summary), flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows, "load": info}, indent=1))


if __name__ == "__main__":
    main()
