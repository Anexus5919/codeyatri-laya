"""Offline 2048 question-design probe (LOCAL SIMULATOR positions, real Laya).

Positions come from simulator games played by a perfect reader of the v3 facts (offline only; it
never plays a real game). For each position Laya is asked with a given fact style, and its pick is
scored against what a perfect reader of the stated priorities would choose: corner first, then
board order, then empty cells.

Usage: python scripts/probe_2048.py --states 150 --styles v3,v3s
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import time

from laya_agent.arena.decider import LayaMoveDecider
from laya_agent.arena.games import g2048_facts_v3
from laya_agent.arena.sims import Sim2048

D = ("up", "down", "left", "right")


def key(f):
    return (f.data["in_corner"], -f.data["disorder"], f.data["empty_after"])


def collect(n: int, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    states, g = [], 0
    while len(states) < n:
        sim = Sim2048(seed=1000 + g)
        g += 1
        while not sim.done and len(states) < n:
            st = sim.state()
            legal = [f for f in g2048_facts_v3(st).values() if f.legal]
            keys = {key(f) for f in legal}
            if len(legal) >= 2 and len(keys) >= 2 and rng.random() < 0.35:
                states.append(st)
            best = max(legal, key=lambda f: (key(f), -D.index(f.direction)))
            sim.act(best.direction)
    return states


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", type=int, default=150)
    ap.add_argument("--styles", default="v3")
    ap.add_argument("--template", default="noul_nodir")
    ap.add_argument("--out", default=None)
    ap.add_argument("--model", default="english", help="english | multilingual | typed-decisions | checkpoint path")
    args = ap.parse_args()

    states = collect(args.states)
    dec = LayaMoveDecider("2048", model=args.model, template=args.template)
    print("load:", dec.load(), "| states:", len(states), flush=True)
    results = {}
    for style in args.styles.split(","):
        dec.style = style
        hit = corner_lost = corner_lost_possible = 0
        picks = collections.Counter()
        t0 = time.perf_counter()
        for st in states:
            facts = g2048_facts_v3(st)
            legal = {d: f for d, f in facts.items() if f.legal}
            top = max(key(f) for f in legal.values())
            good = {d for d, f in legal.items() if key(f) == top}
            pick = dec.decide(st, applied=1000, fallbacks=1000).laya_choice
            picks[pick] += 1
            hit += pick in good
            if any(not f.data["corner_lost"] for f in legal.values()):
                corner_lost_possible += 1
                corner_lost += legal[pick].data["corner_lost"]
        n = len(states)
        results[style] = {"accuracy": round(hit / n, 3), "corner_lost_picks": corner_lost,
                          "pick_share": {k: round(v / n, 2) for k, v in picks.items()},
                          "ms_per_state": round((time.perf_counter() - t0) * 1000 / n, 1)}
        print(f"{args.template}/{style}: {json.dumps(results[style])}", flush=True)
    if args.out:
        json.dump({"n": len(states), "results": results}, open(args.out, "w"), indent=1)


if __name__ == "__main__":
    main()
