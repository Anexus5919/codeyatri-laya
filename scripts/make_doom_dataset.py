"""Build a Doom fine-tuning dataset for laya-train (offline engine games only, never counted runs).

Each row is one decision: the exact state text and yes/no questions the Doom decider sends, plus the expected answer
per action. The label is the fixed priority reading of the same one-step facts (laya_agent.doom.facts.reader_scores):
it reads one action at a time, never searches for a path and never looks ahead. Decisions come from offline games
played by that reader with some random actions mixed in, across Freedoom maps and the ViZDoom combat scenarios.
Train and held-out splits never share a game.

Usage: python scripts/make_doom_dataset.py --out data/ftdoom --workers 4
Round 2 (states that a fine-tuned Laya reaches, still labelled by the reader, one process on the GPU):
       python scripts/make_doom_dataset.py --out data/ftdoom_r2laya --laya data/ftdoom/ckpt_quick_frozen
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

from laya_agent.doom.engine import DoomEnv
from laya_agent.doom.facts import CRITERIA, Perceiver, facts, questions, reader_choice, reader_scores, state_text

MAPS1 = [f"freedoom1:E1M{i}" for i in range(1, 10)]
MAPS2 = [f"freedoom2:MAP0{i}" for i in range(1, 9)]
SCENARIOS = {"defend_the_center": 6, "defend_the_line": 6, "deadly_corridor": 8, "deathmatch": 6,
             "health_gathering_supreme": 2, "my_way_home": 3, "basic": 6, "take_cover": 2}


def episodes(seed0: int) -> list[dict]:
    eps = []
    for i, m in enumerate(MAPS1):
        for k in range(2):
            eps.append({"scenario": m, "skill": 2 + (i + k) % 3, "seed": seed0 + 10 * i + k, "minutes": 4.0})
    for i, m in enumerate(MAPS2):
        eps.append({"scenario": m, "skill": 3, "seed": seed0 + 500 + i, "minutes": 4.0})
    for name, n in SCENARIOS.items():
        for k in range(n):
            eps.append({"scenario": name, "skill": 3, "seed": seed0 + 900 + 7 * k, "minutes": 4.0})
    return eps


_DECIDER = None


def play(ep: dict) -> dict:
    rng = random.Random(ep["seed"])
    decider = _DECIDER if ep.get("laya") else None
    env = DoomEnv(ep["scenario"], skill=ep["skill"], seed=ep["seed"], timeout_tics=int(ep["minutes"] * 60 * 35))
    rows, best_counts = [], Counter()
    try:
        env.start()
        p = Perceiver()
        burst = 0
        while not env.done:
            obs = env.observe()
            if obs is None:
                break
            s = p.scene(obs)
            fs = facts(s)
            sc = reader_scores(s, fs)
            top = max(sc.values())
            if len(sc) >= 2 and top > min(sc.values()):
                qs = questions(fs)
                best = sorted(a for a, v in sc.items() if v == top)
                rows.append({"state": state_text(s),
                             "questions": {f"q_{a}": {"type": "noul", "instructions": q, "criteria": dict(CRITERIA)}
                                           for a, q in qs.items()},
                             "expected": {f"q_{a}": bool(sc[a] == top) for a in qs},
                             "meta": {"scenario": ep["scenario"], "best": best, "seed": ep["seed"]}})
                best_counts[best[0]] += 1
            if burst > 0 or rng.random() < (0.05 if decider else 0.15):
                burst = burst - 1 if burst > 0 else rng.randint(0, 3)
                a = rng.choice(sorted(sc))  # random actions widen the states the reader alone would reach
            elif decider is not None:
                a = decider.decide(s).action  # round 2: go where the fine-tuned Laya itself goes
            else:
                a = reader_choice(sc)
            env.act(a)
            p.note(a)
        out = env.outcome()
    finally:
        env.close()
    return {"ep": ep, "rows": rows, "outcome": out, "best": dict(best_counts)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/ftdoom")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--holdout-frac", type=float, default=0.15)
    ap.add_argument("--keep", type=float, default=0.35, help="share of decisions kept per game")
    ap.add_argument("--shoot-keep", type=float, default=0.6, help="extra thinning of rows whose answer is shoot")
    ap.add_argument("--forward-keep", type=float, default=0.5, help="extra thinning of rows whose answer is forward")
    ap.add_argument("--seed", type=int, default=1993)
    ap.add_argument("--laya", default=None, help="a checkpoint: Laya plays the games (one process), the reader labels")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    eps = episodes(args.seed)
    if args.laya:
        global _DECIDER
        from laya_agent.doom.decider import DoomDecider

        _DECIDER = DoomDecider(model=args.laya)
        print("laya:", _DECIDER.load(), flush=True)
        eps = [{**e, "laya": True, "minutes": 2.5} for e in eps[::2]]
        results = []
        for e in eps:
            results.append(play(e))
            print(f"  played {e['scenario']}: {len(results[-1]['rows'])} rows", flush=True)
    else:
        with Pool(args.workers) as pool:
            results = pool.map(play, eps, chunksize=1)

    train, hold, seen = [], [], set()
    best_kept = Counter()
    for res in results:
        bucket = hold if rng.random() < args.holdout_frac else train
        for row in res["rows"]:
            best = row["meta"]["best"]
            keep = args.keep * (args.shoot_keep if best == ["shoot"] else args.forward_keep if best == ["forward"] else 1.0)
            if rng.random() > keep:
                continue
            key = (row["state"], tuple(sorted((k, v["instructions"]) for k, v in row["questions"].items())))
            if key in seen:
                continue
            seen.add(key)
            bucket.append(row)
            best_kept["+".join(row["meta"]["best"])] += 1
        print(f"{res['ep']['scenario']:26s} skill {res['ep']['skill']} rows {len(res['rows']):5d} "
              f"kills {res['outcome']['kills']:3d} dead {res['outcome']['dead']}", flush=True)
    rng.shuffle(train)
    rng.shuffle(hold)
    for name, rows in (("train", train), ("holdout", hold)):
        with open(out / f"{name}.jsonl", "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    pos = sum(v for r in train for v in r["expected"].values())
    tot = sum(len(r["expected"]) for r in train)
    print(json.dumps({"train": len(train), "holdout": len(hold), "train_questions": tot,
                      "train_true_share": round(pos / max(tot, 1), 3),
                      "best_action_mix": dict(best_kept.most_common(12))}))
    print("example:", json.dumps(train[0], ensure_ascii=False)[:900])


if __name__ == "__main__":
    main()
