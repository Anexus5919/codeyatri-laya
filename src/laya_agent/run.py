"""Run the bot against one game.

Usage:
  python -m laya_agent.run --game fixture --seed 0            # LOCAL TEST FIXTURE, never a verified result
  python -m laya_agent.run --game <hosted-game>               # after the hosted adapter is written
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from .config import Settings
from .decision.laya_client import LayaDecider
from .game.base import GameAdapter, GameClient
from .loop import GameLoop
from .telemetry.jsonl import EventLog, new_run_id
from .viewer.terminal import ConsoleSink


def build_game(name: str, settings: Settings, seed: int) -> tuple[GameClient, GameAdapter]:
    if name == "fixture":
        from .game.local_fixture import CoinGridAdapter, LocalFixtureClient

        return LocalFixtureClient(seed=seed), CoinGridAdapter()
    # Hosted games are registered here on hackathon day, for example:
    #   if name == "stage1": return Stage1Client(transport(settings)), Stage1Adapter()
    raise SystemExit(f"unknown game {name!r}: hosted adapters are added once the official APIs are published")


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="fixture")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--design", default=None, help="question design id (overrides BOT_QUESTION_DESIGN)")
    ap.add_argument("--model", default=None, help="laya checkpoint (overrides BOT_LAYA_MODEL)")
    ap.add_argument("--max-steps", type=int, default=None)
    ap.add_argument("--quiet", action="store_true", help="log only, no terminal viewer")
    args = ap.parse_args(argv)

    settings = Settings.from_env()
    design = args.design or settings.question_design
    model = args.model or settings.laya_model
    client, adapter = build_game(args.game, settings, args.seed)

    run_id = new_run_id()
    log_path = Path(settings.log_dir) / f"{run_id}_{args.game}.jsonl"
    sinks = [] if args.quiet else [ConsoleSink()]
    with EventLog(log_path, run_id, client.env, sinks, (settings.game_token,), settings.log_max_field_chars) as log:
        log.emit(
            "run_start",
            game_id=adapter.game_id,
            design_id=design,
            model=model,
            seed=args.seed if args.game == "fixture" else None,
            git_commit=git_commit(),
            python=sys.version.split()[0],
            settings=settings.public_dict(),
        )
        decider = LayaDecider(model, settings.device, design, settings.head_max_len, settings.max_len)
        log.emit("model_loaded", info=decider.load())
        loop = GameLoop(
            client,
            adapter,
            decider,
            log,
            max_steps=args.max_steps or settings.max_steps,
            max_state_refetch=settings.max_state_refetch,
            max_decision_retries=settings.max_decision_retries,
        )
        summary = loop.run()
    print(f"log: {log_path}")
    return 0 if summary.status == "finished" else 2


if __name__ == "__main__":
    raise SystemExit(main())
