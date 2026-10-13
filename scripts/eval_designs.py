"""Offline question-design experiment on the LOCAL FIXTURE with real Laya.

For a fixed probe set of coin-grid states, every design asks Laya for a move twice: options in
their normal order and in reverse. The fixture's BFS distances say which legal moves actually get
closer to the coin; they are used here only to score Laya's answers, never to choose a move.

Usage: python scripts/eval_designs.py --model english --seeds 60 --out docs/evidence/design_eval_english_cpu.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import replace
from pathlib import Path

from laya_agent.decision.laya_client import LayaDecider
from laya_agent.decision.questions import DESIGNS
from laya_agent.game.local_fixture import CoinGrid, CoinGridAdapter


def probe_set(n_seeds: int, style: str = "words"):
    adapter = CoinGridAdapter(style)
    probes = []
    for seed in range(n_seeds):
        obs = adapter.observe(CoinGrid(seed=seed).state())
        good = {
            c.action_id
            for c in obs.candidates
            if c.facts["coin_distance_after"] is not None
            and c.facts["coin_distance_before"] is not None
            and c.facts["coin_distance_after"] < c.facts["coin_distance_before"]
        }
        if 0 < len(good) < len(obs.candidates):
            probes.append((seed, obs, good))
    return probes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="english")
    ap.add_argument("--device", default=None)
    ap.add_argument("--seeds", type=int, default=60)
    ap.add_argument("--designs", default=",".join(DESIGNS))
    ap.add_argument("--style", default="words", choices=["words", "numeric"], help="fixture description style")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    probes = probe_set(args.seeds, args.style)
    chance = statistics.mean(len(g) / len(o.candidates) for _, o, g in probes)
    decider = LayaDecider(args.model, args.device, "facts_v1")
    load_info = decider.load()
    print(f"model={args.model} probes={len(probes)} chance={chance:.3f} load={load_info}", flush=True)

    results = {"model": args.model, "style": args.style, "load": load_info, "probes": len(probes), "chance_accuracy": round(chance, 4), "designs": {}}
    for design_id in args.designs.split(","):
        decider.design_id = design_id
        rows = []
        t_design = time.perf_counter()
        for seed, obs, good in probes:
            fwd = decider.decide(obs)
            rev = decider.decide(replace(obs, candidates=tuple(reversed(obs.candidates))))
            rows.append({
                "seed": seed,
                "good": sorted(good),
                "chosen": fwd.chosen_action_id,
                "chosen_reversed": rev.chosen_action_id,
                "p_good": round(sum(p for a, p in fwd.probabilities.items() if a in good), 4),
                "p_true": (fwd.aggregate_detail or {}).get("p_true"),
                "answer_confidence": fwd.answer_confidence,
                "latency_ms": round(fwd.latency_ms, 1),
                "error": fwd.error or rev.error,
            })
        acc = statistics.mean(r["chosen"] in r["good"] for r in rows)
        acc_rev = statistics.mean(r["chosen_reversed"] in r["good"] for r in rows)
        agree = statistics.mean(r["chosen"] == r["chosen_reversed"] for r in rows)
        confs = [r["answer_confidence"] for r in rows if r["answer_confidence"] is not None]
        med = statistics.median(confs) if confs else None
        hi = [r for r in rows if med is not None and r["answer_confidence"] is not None and r["answer_confidence"] > med]
        lo = [r for r in rows if med is not None and r["answer_confidence"] is not None and r["answer_confidence"] <= med]
        summary = {
            "accuracy": round(acc, 4),
            "accuracy_reversed": round(acc_rev, 4),
            "order_agreement": round(agree, 4),
            "mean_p_good": round(statistics.mean(r["p_good"] for r in rows), 4),
            "accuracy_high_conf": round(statistics.mean(r["chosen"] in r["good"] for r in hi), 4) if hi else None,
            "accuracy_low_conf": round(statistics.mean(r["chosen"] in r["good"] for r in lo), 4) if lo else None,
            "latency_ms_p50": round(statistics.median(r["latency_ms"] for r in rows), 1),
            "errors": sum(1 for r in rows if r["error"]),
            "wall_s": round(time.perf_counter() - t_design, 1),
        }
        results["designs"][design_id] = {"summary": summary, "rows": rows}
        print(f"{design_id:14} {json.dumps(summary)}", flush=True)

    print("\n| design | accuracy | reversed | order agreement | mean P(good) | acc high conf | acc low conf | p50 ms |")
    print("|---|---|---|---|---|---|---|---|")
    for d, r in results["designs"].items():
        s = r["summary"]
        print(f"| {d} | {s['accuracy']} | {s['accuracy_reversed']} | {s['order_agreement']} | {s['mean_p_good']} | {s['accuracy_high_conf']} | {s['accuracy_low_conf']} | {s['latency_ms_p50']} |")
    print(f"\nchance accuracy (uniform over legal moves): {chance:.3f}")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
