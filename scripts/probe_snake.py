"""Offline question-design probe for Snake (LOCAL SIMULATOR states, real Laya).

Collects positions from simulator games (a random safe walker only generates test positions; it
never plays a real game), then asks Laya with each template and scores its pick against the facts:
a pick is "good" if it is safe and eats the food, or is safe, not trapped and among the closest to it.

Usage: python scripts/probe_snake.py --states 200 --templates noul_v1,noul_nodir,noul_nodir_short
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import statistics
import time

from laya_agent.arena.decider import LayaMoveDecider
from laya_agent.arena.games import snake_facts
from laya_agent.arena.sims import SnakeSim


EAT_ONLY = False


def collect(n: int, seed: int = 0) -> list[dict]:
    rng = random.Random(seed)
    states = []
    g = 0
    while len(states) < n:
        sim = SnakeSim(seed=seed * 1000 + g)
        g += 1
        while not sim.done and len(states) < n:
            st = sim.state()
            facts = snake_facts(st)
            safe = [d for d, f in facts.items() if f.legal and not f.fatal and "closed pocket" not in f.text]
            good = good_set(facts)
            has_eat = any(f.kind == "eat" for f in facts.values())
            if safe and good and len(good) < len(safe) and (not EAT_ONLY or has_eat):
                states.append(st)
            if not safe:
                break
            # bias the walker toward food so positions include long snakes and eats
            sim.act(rng.choice(sorted(good) if rng.random() < 0.7 else safe))
    return states


def good_set(facts) -> set[str]:
    ok = {d: f for d, f in facts.items() if f.legal and not f.fatal and "closed pocket" not in f.text}
    eats = {d for d, f in ok.items() if f.kind == "eat"}
    if eats:
        return eats
    dists = {d: f.data.get("dist_after") for d, f in ok.items() if f.data.get("dist_after") is not None}
    if not dists:
        return set(ok)
    best = min(dists.values())
    return {d for d, v in dists.items() if v == best}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", type=int, default=200)
    ap.add_argument("--templates", default="noul_v1,noul_nodir,noul_nodir_short")
    ap.add_argument("--style", default="words")
    ap.add_argument("--out", default=None)
    ap.add_argument("--model", default="english", help="english | multilingual | typed-decisions | checkpoint path")
    ap.add_argument("--eat-only", action="store_true")
    ap.add_argument("--styles", default=None, help="comma list of fact styles to compare with the first template")
    args = ap.parse_args()
    global EAT_ONLY
    EAT_ONLY = args.eat_only

    states = collect(args.states)
    chance = statistics.mean(len(good_set(snake_facts(s))) / sum(f.legal for f in snake_facts(s).values()) for s in states)
    dec = LayaMoveDecider("snake", model=args.model, template="noul_v1", style=args.style)
    print("load:", dec.load(), "| states:", len(states), f"| chance {chance:.3f}", flush=True)
    results = {}
    runs = [(t, args.style) for t in args.templates.split(",")]
    if args.styles:
        runs = [(args.templates.split(",")[0], st) for st in args.styles.split(",")]
    for tpl, style in runs:
        dec.template, dec.style = tpl, style
        hits, fatal, picks, eat_miss, t0 = 0, 0, collections.Counter(), 0, time.perf_counter()
        for st in states:
            facts = snake_facts(st, style=style)
            d = dec.decide(st, applied=1000, fallbacks=1000)  # budget exhausted: report Laya's own pick
            pick = d.laya_choice
            picks[pick] += 1
            hits += pick in good_set(facts)
            fatal += facts[pick].fatal
            eat_miss += any(f.kind == "eat" for f in facts.values()) and facts[pick].kind != "eat"
        n = len(states)
        results[f"{tpl}/{style}"] = {"accuracy": round(hits / n, 3), "fatal_picks": fatal, "missed_eats": eat_miss,
                        "pick_share": {k: round(v / n, 2) for k, v in picks.items()},
                        "ms_per_state": round((time.perf_counter() - t0) * 1000 / n, 1)}
        print(f"{tpl + '/' + style:>26}: {json.dumps(results[f'{tpl}/{style}'])}", flush=True)
    if args.out:
        json.dump({"chance": chance, "n": len(states), "results": results}, open(args.out, "w"), indent=1)


if __name__ == "__main__":
    main()
