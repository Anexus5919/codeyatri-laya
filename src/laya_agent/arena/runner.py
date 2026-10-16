"""Plays one arena session: state -> Laya -> log decision -> send move -> log line -> repeat.

Usage:
  python -m laya_agent.arena.runner --game snake                 # REAL arena (topgameai.com), agent CodeYatri
  python -m laya_agent.arena.runner --game snake --sim --seed 1  # LOCAL SIMULATOR, never a real result
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from ..contracts import SubmissionAmbiguous
from .decider import LayaMoveDecider
from .games import GAMES
from .spec_log import SpecLog, save_final_response, utc_ts, verify_log

AGENT_NAME = "CodeYatri"


class EventLog:
    """Extra live events for the viewer (decision written BEFORE the move is sent)."""

    def __init__(self, path: Path) -> None:
        self._fh = open(path, "a", encoding="utf-8", newline="\n")

    def write(self, obj: dict) -> None:
        self._fh.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def close(self) -> None:
        self._fh.close()


def ms(t0: float, t1: float) -> int:
    return int(round((t1 - t0) * 1000))


def play_session(client: Any, decider: LayaMoveDecider, game: str, runs_dir: Path, agent_name: str = AGENT_NAME,
                 load_info: dict | None = None, quiet: bool = False, max_rejects: int = 5) -> dict:
    status, resp = client.create(game, agent_name)
    if status >= 400 or "session_id" not in resp:
        raise RuntimeError(f"could not create session: HTTP {status} {resp}")
    sid = resp["session_id"]
    if hasattr(decider, "new_session"):
        decider.new_session()
    folder = runs_dir / game
    folder.mkdir(parents=True, exist_ok=True)
    log = SpecLog(folder / f"{sid}.jsonl", sid, game)
    events = EventLog(folder / f"{sid}.events.jsonl")
    events.write({"type": "session_start", "session_id": sid, "game": game, "agent_name": agent_name,
                  "env": getattr(client, "env", "HOSTED"), "design": decider.template, "offer": decider.offer,
                  "model": decider.model, "model_source": getattr(decider, "model_source", decider.model),
                  "device": (load_info or {}).get("device"), "load": load_info,
                  "first_response": resp, "ts": utc_ts()})
    points = GAMES[game]["points"]

    t_prev_resp = time.monotonic()
    state = resp["state"]
    rejects_this_step: set[str] = set()
    try:
        while not resp.get("done"):
            t_state = time.monotonic()
            dec = decider.decide(state, applied=log.applied, fallbacks=log.fallbacks, exclude=rejects_this_step)
            t_decided = time.monotonic()
            step = log.applied + 1
            events.write({"type": "decision", "session_id": sid, "step": step,
                          "facts": {d: f.text for d, f in dec.facts.items()},
                          "kinds": {d: f.kind for d, f in dec.facts.items()},
                          "p_true": dec.p_true, "probabilities": dec.probabilities, "chosen": dec.action,
                          "source": dec.source, "laya_choice": dec.laya_choice, "reason": dec.reason,
                          "state_text": dec.state_text, "decide_ms": ms(t_state, t_decided),
                          "laya_ms": round(dec.laya_ms, 1), "ts": utc_ts()})

            t_send = time.monotonic()
            try:
                code, body = client.act(sid, dec.action)
            except SubmissionAmbiguous:
                # The move may or may not have landed: read the session back instead of resending
                code, body = client.get(sid)
                if body.get("steps", -1) <= log.applied:
                    events.write({"type": "reconcile", "step": step, "verdict": "not_applied", "ts": utc_ts()})
                    continue
                events.write({"type": "reconcile", "step": step, "verdict": "applied", "ts": utc_ts()})
            t_resp = time.monotonic()
            timing = {"decide_ms": ms(t_state, t_decided), "api_ms": ms(t_send, t_resp), "turn_ms": ms(t_prev_resp, t_resp)}
            t_prev_resp = t_resp

            if "error" in body or code >= 400:
                # Rejected: log it with the state the game reports now, then ask Laya again without that move
                _, now = client.get(sid)
                log.write(step=step, state_before=state, action=dec.action, state_after=now.get("state"),
                          result="rejected", decision=dec.decision_block(), timing=timing)
                events.write({"type": "rejected", "step": step, "action": dec.action, "error": body.get("error"), "ts": utc_ts()})
                rejects_this_step.add(dec.action)
                if len(rejects_this_step) >= max_rejects or len(rejects_this_step) >= 4:
                    raise RuntimeError(f"too many rejected moves at step {step}: {body}")
                state = now.get("state", state)
                continue

            log.write(step=step, state_before=state, action=dec.action, state_after=body["state"],
                      result="applied", decision=dec.decision_block(), timing=timing)
            rejects_this_step = set()
            if hasattr(decider, "note_applied"):
                decider.note_applied()
            resp, state = body, body["state"]
            if not quiet:
                print(f"step {step:>3} {dec.action:>5} [{dec.source}] p={dec.confidence:.3f} "
                      f"score={resp.get('score')} laya={dec.laya_ms:.0f}ms api={timing['api_ms']}ms", flush=True)
    finally:
        _, final = client.get(sid)
        save_final_response(folder, sid, final)
        events.write({"type": "session_end", "session_id": sid, "score": final.get("score"), "won": final.get("won"),
                      "steps": final.get("steps"), "done": final.get("done"), "points": points(final), "ts": utc_ts()})
        log.close()
        events.close()

    report = verify_log(folder / f"{sid}.jsonl", final)
    report["points"] = points(final)
    report["won"] = final.get("won")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid-spec", default=None, help="JSON field mapping that registers a new grid game (stage 3)")
    ap.add_argument("--game", required=True, help="snake | 2048 | the name given in --grid-spec")
    ap.add_argument("--sim", action="store_true", help="use the LOCAL simulator instead of the real arena")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--runs", default="runs", help="output folder (sim runs go to runs_sim by default)")
    ap.add_argument("--template", default="noul_nodir")
    ap.add_argument("--offer", default="legal", choices=["legal", "all"])
    ap.add_argument("--style", default="words", choices=["words", "numbers"])
    ap.add_argument("--model", default="english")
    ap.add_argument("--device", default=None)
    ap.add_argument("--agent-name", default=AGENT_NAME)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    if args.grid_spec:
        from .grid_game import register_from_file

        register_from_file(args.grid_spec)
    if args.game not in GAMES:
        ap.error(f"unknown game {args.game!r}; known: {sorted(GAMES)}")

    if args.sim:
        from .sims import FakeArena

        client = FakeArena(seed=args.seed)
        runs = Path(args.runs if args.runs != "runs" else "runs_sim")
    else:
        from .client import ArenaClient

        client = ArenaClient()
        runs = Path(args.runs)
    decider = LayaMoveDecider(args.game, model=args.model, device=args.device, template=args.template,
                              offer=args.offer, style=args.style)
    info = decider.load()
    print(f"laya loaded: {info}", flush=True)
    report = play_session(client, decider, args.game, runs, args.agent_name, info, args.quiet)
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
