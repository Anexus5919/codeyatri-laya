"""Rebuild a Doom session's screen captures from its demo recording.

The engine replays the recording exactly, so the screen at every decision can be regenerated after the fact: for a
run made without --frames, or one whose captures stopped part way. Existing captures are kept.

Usage: python -m laya_agent.doom.frames runs_sim_doom/doom/<session_id>.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

from .engine import DoomEnv, demo_path


def rebuild(spec: Path, overwrite: bool = False) -> dict:
    sid = spec.name[: -len(".jsonl")]
    folder = spec.parent
    final = json.loads((folder / f"{sid}.final.json").read_text(encoding="utf-8"))
    settings = final.get("settings") or {}
    wanted: dict[int, int] = {}  # game tic of each decision -> its step
    with open(folder / f"{sid}.events.jsonl", encoding="utf-8") as fh:
        for raw in fh:
            ev = json.loads(raw)
            if ev.get("type") == "decision" and isinstance(ev.get("tic"), int):
                wanted.setdefault(ev["tic"], ev["step"])
    out = folder / f"{sid}.frames"
    out.mkdir(exist_ok=True)
    env = DoomEnv(settings.get("scenario", "freedoom1:E1M1"), skill=settings.get("skill", 3),
                  seed=settings.get("seed", 0), resolution=settings.get("resolution", "320x240"), keep_screen=True)
    g = env.game
    g.replay_episode(demo_path(folder / final["recording"]))
    written = kept = 0
    tics = sorted(wanted)
    k = 0
    while not g.is_episode_finished() and k < len(tics):
        st = g.get_state()
        if st is not None:
            # Save the first screen at or after each decision's tic (the state Laya decided on)
            while k < len(tics) and st.tic >= tics[k]:
                path = out / f"{wanted[tics[k]]:05d}.jpg"
                if path.exists() and not overwrite:
                    kept += 1
                else:
                    Image.fromarray(st.screen_buffer).save(path, quality=70)
                    written += 1
                k += 1
        g.advance_action()
    env.close()
    return {"session_id": sid, "decisions": len(tics), "written": written, "kept": kept}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs", nargs="+", help="session logs (<session_id>.jsonl)")
    ap.add_argument("--overwrite", action="store_true", help="also replace captures that already exist")
    args = ap.parse_args(argv)
    for p in args.logs:
        print(json.dumps(rebuild(Path(p), args.overwrite)), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
