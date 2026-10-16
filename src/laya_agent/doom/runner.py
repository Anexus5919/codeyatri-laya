"""Plays Doom episodes with every action chosen by a logged Laya call.

Each episode writes, under runs/doom/:
  <id>.jsonl         the hash-chained submission log (same fields and hash rule as the arena games)
  <id>.events.jsonl  the full decision record: state text, every fact and question, Laya's raw P(yes), timings
  <id>.lmp           the engine's own demo recording of the episode (replays exactly; the proof of play)
  <id>.final.json    how the episode ended, the run settings and the recording's sha256
  <id>.frames/       optional screen captures for the dashboard (not committed)

Usage:
  python -m laya_agent.doom.runner --scenario freedoom1:E1M1 --model data/ftdoom/ckpt --realtime --visible
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path

from ..arena.spec_log import SpecLog, utc_ts, verify_log
from .decider import DoomDecider
from .engine import ACTIONS, DoomEnv, Observation
from .facts import Perceiver, Scene


def compact(scene: Scene, tic: int) -> dict:
    """The state_before / state_after record: what the facts were written from, rounded and small."""
    return {
        "tic": int(tic), "health": scene.health, "armor": scene.armor, "weapon": scene.weapon, "ammo": scene.ammo,
        "kills": scene.kills, "x": round(scene.x), "y": round(scene.y), "angle": round(scene.angle),
        "enemies": [{"name": e.name, "dist": round(e.dist), "bearing": round(e.bearing), "in_view": e.visible,
                     "in_crosshair": e.in_crosshair} for e in sorted(scene.enemies, key=lambda e: e.dist)[:5]],
        "items_in_view": len(scene.items),
    }


def compact_vars(obs: Observation) -> dict:
    """The state_after record: the engine's own variables right after the action."""
    v = obs.vars
    return {"tic": int(obs.tic), "health": int(v["HEALTH"]), "armor": int(v["ARMOR"]), "weapon": int(v["SELECTED_WEAPON"]),
            "ammo": int(v["SELECTED_WEAPON_AMMO"]), "kills": int(v["KILLCOUNT"]), "x": round(v["POSITION_X"]),
            "y": round(v["POSITION_Y"]), "angle": round(v["ANGLE"])}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class FrameSaver:
    def __init__(self, folder: Path, every: int = 1):
        from PIL import Image  # only needed when frames are kept

        self.Image = Image
        self.folder = folder
        self.every = every
        folder.mkdir(parents=True, exist_ok=True)

    def save(self, step: int, screen) -> None:
        if screen is None:
            return
        img = self.Image.fromarray(screen)
        tmp = self.folder / "latest.tmp.jpg"
        img.save(tmp, quality=75)
        os.replace(tmp, self.folder / "latest.jpg")
        if step % self.every == 0:
            img.save(self.folder / f"{step:05d}.jpg", quality=70)


def play_episode(env: DoomEnv, decider: DoomDecider, runs_dir: str | Path, agent_name: str = "CodeYatri",
                 settings: dict | None = None, frames: bool = False, quiet: bool = False,
                 max_steps: int | None = None) -> dict:
    sid = f"doom-{uuid.uuid4()}"
    folder = Path(runs_dir) / "doom"
    folder.mkdir(parents=True, exist_ok=True)
    log = SpecLog(folder / f"{sid}.jsonl", sid, "doom", keys=ACTIONS)
    events = open(folder / f"{sid}.events.jsonl", "a", encoding="utf-8", newline="\n")
    lmp = folder / f"{sid}.lmp"
    saver = FrameSaver(folder / f"{sid}.frames") if frames else None
    perceiver = Perceiver()

    def event(rec: dict) -> None:
        events.write(json.dumps({"session_id": sid, "ts": utc_ts(), **rec}, ensure_ascii=False) + "\n")
        events.flush()

    event({"type": "session_start", "game": "doom", "agent_name": agent_name, "settings": settings or {},
           "model_source": decider.model_source})
    env.start(str(lmp))
    obs = env.observe()
    step = 0
    t_episode = time.perf_counter()
    try:
        while obs is not None and not env.done and (max_steps is None or step < max_steps):
            t_turn = time.perf_counter()
            scene = perceiver.scene(obs)
            before = compact(scene, obs.tic)
            if saver:
                saver.save(step + 1, obs.screen)
            t0 = time.perf_counter()
            dec = decider.decide(scene)
            decide_ms = (time.perf_counter() - t0) * 1000
            event({"type": "decision", "step": step + 1, "tic": obs.tic, "state_text": dec.state_text,
                   "facts": {a: f.text for a, f in dec.facts.items()},
                   "offered": [a for a, f in dec.facts.items() if f.offered],
                   "p_true": {a: round(p, 6) for a, p in dec.p_true.items()},
                   "probabilities": dec.probabilities, "chosen": dec.action, "source": dec.source,
                   "laya_ms": round(dec.laya_ms, 1), "decide_ms": round(decide_ms)})
            t1 = time.perf_counter()
            reward = env.act(dec.action)
            engine_ms = (time.perf_counter() - t1) * 1000
            perceiver.note(dec.action)
            obs = None if env.done else env.observe()
            after = compact_vars(obs) if obs is not None else {"episode_over": True, **env.outcome()}
            step += 1
            log.write(step=step, state_before=before, action=dec.action, state_after=after, result="applied",
                      decision=dec.decision_block(),
                      timing={"decide_ms": decide_ms, "api_ms": engine_ms,
                              "turn_ms": (time.perf_counter() - t_turn) * 1000})
            if not quiet and (step % 25 == 0 or env.done):
                print(f"  step {step:5d}  {dec.action:15s} p={dec.confidence:.3f}  health {before['health']:4d}  "
                      f"kills {before['kills']:3d}  laya {dec.laya_ms:5.0f} ms  reward {reward:+.2f}", flush=True)
    finally:
        outcome = env.outcome()
        env.close()  # the engine finishes writing the demo recording on close, so hash it only after this
        log.close()
        report = verify_log(folder / f"{sid}.jsonl", keys=ACTIONS) if step else {"ok": False, "problems": ["no moves"]}
        final = {"session_id": sid, "game": "doom", "agent_name": agent_name, "steps": step, **outcome,
                 "seconds": round(time.perf_counter() - t_episode, 1), "settings": settings or {},
                 "model_source": decider.model_source, "log_verified": bool(report.get("ok")),
                 "recording": lmp.name, "recording_sha256": sha256_file(lmp) if lmp.exists() else None,
                 "explored_cells": len(perceiver.explored.seen)}
        with open(folder / f"{sid}.final.json", "w", encoding="utf-8") as fh:
            json.dump(final, fh, indent=2)
        event({"type": "session_end", **{k: final[k] for k in ("steps", "kills", "dead", "exited", "health")}})
        events.close()
    return final


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default="freedoom1:E1M1", help="freedoom1:E1M1, freedoom2:MAP01 or a ViZDoom scenario")
    ap.add_argument("--model", default="english", help="english or a fine-tuned checkpoint folder")
    ap.add_argument("--episodes", type=int, default=1)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--skill", type=int, default=3, help="1 (easiest) to 5")
    ap.add_argument("--realtime", action="store_true", help="the game runs at 35 tics/s while Laya decides")
    ap.add_argument("--visible", action="store_true", help="show the game window (for judging)")
    ap.add_argument("--resolution", default=None, help="320x240 (default) or 640x480 / 800x600 with --visible")
    ap.add_argument("--minutes", type=float, default=10.0, help="episode time limit in game minutes")
    ap.add_argument("--frames", action="store_true", help="save screen captures for the dashboard")
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--agent-name", default="CodeYatri")
    ap.add_argument("--device", default=None)
    args = ap.parse_args(argv)

    resolution = args.resolution or ("640x480" if args.visible else "320x240")
    settings = {"scenario": args.scenario, "skill": args.skill, "realtime": args.realtime, "seed": args.seed,
                "minutes": args.minutes, "resolution": resolution}
    decider = DoomDecider(model=args.model, device=args.device)
    info = decider.load()
    print("laya:", info, flush=True)
    results = []
    for ep in range(args.episodes):
        env = DoomEnv(args.scenario, skill=args.skill, seed=args.seed + ep, realtime=args.realtime,
                      visible=args.visible, resolution=resolution, timeout_tics=int(args.minutes * 60 * 35),
                      keep_screen=args.frames)
        try:
            final = play_episode(env, decider, args.runs, args.agent_name, {**settings, "seed": args.seed + ep},
                                 frames=args.frames)
        finally:
            env.close()
        results.append(final)
        print(json.dumps({k: final[k] for k in ("session_id", "steps", "kills", "items", "dead", "exited", "health",
                                                "log_verified")}), flush=True)
    return 0 if all(r["log_verified"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
