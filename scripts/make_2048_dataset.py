"""Build a 2048 fine-tuning dataset for laya-train (LOCAL SIMULATOR positions only).

Each row is one position: the exact state text and yes/no questions our decider sends, plus the
expected answer per direction. The label is a fixed reading of the priorities we state to Laya
(corner first, then board order, then empty cells); it is not a search and never looks ahead.
Positions come from three sources so the model sees boards it will actually reach:
  - games played by that priority reader
  - games played with random legal moves
  - boards from Laya's own earlier simulator games (runs_sim_eval*/2048/*.jsonl), if present
Train and held-out splits never share a game.

Usage: python scripts/make_2048_dataset.py --out data/ft2048 --reader-games 60 --random-games 30
"""

from __future__ import annotations

import argparse
import glob
import json
import random
from pathlib import Path

from laya_agent.arena.decider import LayaMoveDecider
from laya_agent.arena.games import g2048_facts_v3
from laya_agent.arena.sims import Sim2048

D = ("up", "down", "left", "right")


def key(f):
    return (f.data["in_corner"], -f.data["disorder"], f.data["empty_after"])


class _NoRouter:
    """The decider only builds question text here; Laya is never called."""


def make_row(dec: LayaMoveDecider, state: dict) -> dict | None:
    facts = g2048_facts_v3(state)
    legal = {d: f for d, f in facts.items() if f.legal}
    if len(legal) < 2:
        return None
    top = max(key(f) for f in legal.values())
    if all(key(f) == top for f in legal.values()):
        return None  # nothing to learn: every legal move is equally good under the priorities
    questions = dec._questions(facts, set())
    state_text = dec.spec["state_text"](state)
    laya_q = {f"q_{d}": {"type": "noul", "instructions": q, "criteria": {"true": "a good move for these priorities",
                                                                      "false": "a poor move for these priorities"}}
              for d, q in questions.items()}
    expected = {f"q_{d}": bool(key(legal[d]) == top) for d in questions}
    return {"state": state_text, "questions": laya_q, "expected": expected,
            "meta": {"best": state.get("best"), "legal": sorted(legal)}}


def reader_game(seed: int):
    sim = Sim2048(seed)
    while not sim.done:
        st = sim.state()
        yield st
        legal = [f for f in g2048_facts_v3(st).values() if f.legal]
        best = max(legal, key=lambda f: (key(f), -D.index(f.direction)))
        sim.act(best.direction)


def random_game(seed: int):
    rng = random.Random(seed)
    sim = Sim2048(seed)
    while not sim.done:
        st = sim.state()
        yield st
        legal = [f.direction for f in g2048_facts_v3(st).values() if f.legal]
        sim.act(rng.choice(legal))


def laya_boards(pattern: str):
    for path in glob.glob(pattern):
        for line in open(path, encoding="utf-8"):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("game") == "2048" and isinstance(row.get("state_before"), dict):
                yield row["state_before"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/ft2048")
    ap.add_argument("--reader-games", type=int, default=60)
    ap.add_argument("--random-games", type=int, default=30)
    ap.add_argument("--laya-logs", default="runs_sim_eval*/*/2048/*[!s].jsonl")
    ap.add_argument("--holdout-frac", type=float, default=0.15)
    ap.add_argument("--sample", type=float, default=0.6, help="keep this share of positions per game")
    ap.add_argument("--seed", type=int, default=2048)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    dec = LayaMoveDecider("2048", router=_NoRouter(), template="noul_nodir", style="v3")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    games: list[tuple[str, list[dict]]] = []
    for g in range(args.reader_games):
        games.append((f"reader-{g}", list(reader_game(5000 + g))))
    for g in range(args.random_games):
        games.append((f"random-{g}", list(random_game(7000 + g))))
    laya = list(laya_boards(args.laya_logs))
    if laya:
        games.append(("laya-own", laya))

    train, hold = [], []
    counts = {"train": 0, "holdout": 0, "skipped": 0}
    for name, states in games:
        bucket = hold if rng.random() < args.holdout_frac else train
        if name == "laya-own":
            bucket = train
        for st in states:
            if rng.random() > args.sample:
                continue
            row = make_row(dec, st)
            if row is None:
                counts["skipped"] += 1
                continue
            row["meta"]["source"] = name.split("-")[0]
            bucket.append(row)
    rng.shuffle(train)
    rng.shuffle(hold)
    for name, rows in (("train", train), ("holdout", hold)):
        with open(out / f"{name}.jsonl", "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        counts[name] = len(rows)
    pos = sum(v for r in train for v in r["expected"].values())
    tot = sum(len(r["expected"]) for r in train)
    print(json.dumps({**counts, "train_questions": tot, "train_true_share": round(pos / tot, 3),
                      "sources": {s: sum(r["meta"]["source"] == s for r in train) for s in ("reader", "random", "laya")}}))
    print("example:", json.dumps(train[0], ensure_ascii=False)[:600])


if __name__ == "__main__":
    main()
