"""Compare Doom policies on the same fixed games (simulator runs only; logs go to runs_sim_doom_eval/).

Policies: laya (base `english` or a checkpoint via --model), reader (the rule reader that labels training data,
shown as a reference), random. Laya episodes are full logged runs (hash chain, demo recording) through the runner.

Usage: python scripts/eval_doom.py --policy laya --model data/ftdoom/ckpt --out docs/evidence/eval_doom_x.json
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import time
from pathlib import Path

from laya_agent.doom.engine import DoomEnv
from laya_agent.doom.facts import Perceiver, facts, reader_choice, reader_scores

SUITE = [("defend_the_center", s, 2.0) for s in (11, 12, 13)] + \
        [("defend_the_line", s, 2.0) for s in (11, 12)] + \
        [("deadly_corridor", s, 2.0) for s in (11, 12, 13)] + \
        [("freedoom1:E1M1", 11, 3.0), ("freedoom1:E1M2", 11, 3.0), ("freedoom2:MAP01", 11, 3.0)]


def play_simple(policy: str, scenario: str, seed: int, minutes: float) -> dict:
    rng = random.Random(seed)
    env = DoomEnv(scenario, seed=seed, timeout_tics=int(minutes * 60 * 35))
    env.start()
    p = Perceiver()
    steps = 0
    while not env.done:
        obs = env.observe()
        if obs is None:
            break
        s = p.scene(obs)
        sc = reader_scores(s, facts(s))
        a = reader_choice(sc) if policy == "reader" else rng.choice(sorted(sc))
        env.act(a)
        p.note(a)
        steps += 1
    out = env.outcome()
    env.close()
    return {**out, "steps": steps, "explored_cells": len(p.explored.seen)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", choices=["laya", "reader", "random"], default="laya")
    ap.add_argument("--model", default="english")
    ap.add_argument("--runs", default="runs_sim_doom_eval")
    ap.add_argument("--out", default=None)
    ap.add_argument("--only", default=None, help="comma list of scenario names to run")
    args = ap.parse_args()

    suite = [g for g in SUITE if not args.only or g[0] in args.only.split(",")]
    decider = None
    if args.policy == "laya":
        from laya_agent.doom.decider import DoomDecider
        from laya_agent.doom.runner import play_episode

        decider = DoomDecider(model=args.model)
        print("load:", decider.load(), flush=True)
    rows = []
    for scenario, seed, minutes in suite:
        t0 = time.perf_counter()
        if decider:
            env = DoomEnv(scenario, seed=seed, timeout_tics=int(minutes * 60 * 35))
            settings = {"scenario": scenario, "skill": 3, "seed": seed, "minutes": minutes, "realtime": False}
            r = play_episode(env, decider, args.runs, settings=settings, quiet=True)
        else:
            r = play_simple(args.policy, scenario, seed, minutes)
        row = {"scenario": scenario, "seed": seed, **{k: r.get(k) for k in ("kills", "items", "secrets", "health", "dead",
                                                                             "exited", "steps", "explored_cells",
                                                                             "log_verified", "session_id")},
               "seconds": round(time.perf_counter() - t0, 1)}
        rows.append(row)
        print(json.dumps(row), flush=True)
    by = {}
    for r in rows:
        by.setdefault(r["scenario"], []).append(r)
    summary = {sc: {"games": len(rs), "kills_mean": round(statistics.mean(r["kills"] for r in rs), 2),
                    "exited": sum(bool(r["exited"]) for r in rs), "died": sum(bool(r["dead"]) for r in rs),
                    "explored_mean": round(statistics.mean(r["explored_cells"] or 0 for r in rs), 1)}
               for sc, rs in by.items()}
    summary["all"] = {"kills_total": sum(r["kills"] for r in rows), "exited": sum(bool(r["exited"]) for r in rows),
                      "died": sum(bool(r["dead"]) for r in rows)}
    print("SUMMARY", json.dumps(summary), flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps({"policy": args.policy, "model": args.model, "summary": summary,
                                              "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
