"""Real Laya smoke test: install check, cold load, warm latency, output shape, determinism, order bias.

Usage: python scripts/smoke_laya.py [--model english] [--device cpu] [--out docs/evidence/smoke.json]
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

STATE = "Coin grid 7x7. Player at 2,3. Coin at 5,3. Shortest path to coin: 3 steps. Score 0. Steps left 40."
QUESTION = {
    "move": {
        "type": "choice",
        "instructions": "Pick the move that gets the player to the coin fastest.",
        "criteria": {
            "up": "move up: same distance to the coin (3 steps)",
            "down": "move down: same distance to the coin (3 steps)",
            "left": "move left: farther from the coin (3 to 4 steps)",
            "right": "move right: closer to the coin (3 to 2 steps)",
        },
    }
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="english")
    ap.add_argument("--device", default=None)
    ap.add_argument("--warm-runs", type=int, default=10)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    report: dict = {"python": sys.version.split()[0], "platform": platform.platform()}
    t0 = time.perf_counter()
    import laya
    import torch

    report["laya_version"] = laya.__version__
    report["torch"] = torch.__version__
    report["cuda_available"] = torch.cuda.is_available()
    report["import_s"] = round(time.perf_counter() - t0, 2)

    router = laya.Router(device=args.device)
    t1 = time.perf_counter()
    agent = router.load(args.model)
    report["cold_load_s"] = round(time.perf_counter() - t1, 2)
    report["device"] = str(getattr(agent, "device", None))
    report["revisions"] = router.loaded_revisions

    t2 = time.perf_counter()
    first = router.predict(STATE, QUESTION, model=args.model)
    report["first_call_ms"] = round((time.perf_counter() - t2) * 1000, 1)
    report["result"] = first

    warm = []
    for _ in range(args.warm_runs):
        t = time.perf_counter()
        r = router.predict(STATE, QUESTION, model=args.model)
        warm.append((time.perf_counter() - t) * 1000)
    report["warm_ms"] = {
        "n": len(warm),
        "p50": round(statistics.median(warm), 1),
        "max": round(max(warm), 1),
    }
    report["deterministic"] = r["answers"]["move"]["probabilities"] == first["answers"]["move"]["probabilities"]

    # Same options shown in reverse order; probabilities come back keyed by label either way.
    rev = json.loads(json.dumps(QUESTION))
    rev["move"]["option_order"] = [3, 2, 1, 0]
    reversed_result = router.predict(STATE, rev, model=args.model)
    report["reversed_order"] = reversed_result["answers"]["move"]

    text = json.dumps(report, indent=2, default=str)
    print(text)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
