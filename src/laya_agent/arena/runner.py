"""Plays one arena session: state -> Laya -> log decision -> send move -> log line -> repeat.

Usage:
  python -m laya_agent.arena.runner --game snake                 # REAL arena (topgameai.com), agent CodeYatri
  python -m laya_agent.arena.runner --game 2048 --model <ckpt>   # REAL arena with a fine-tuned checkpoint
  python -m laya_agent.arena.runner --game 2048 --model <ckpt> --resume <session_id>   # continue an open session
  python -m laya_agent.arena.runner --game snake --sim --seed 1  # LOCAL SIMULATOR, never a real result

Network drops: a move is never sent twice. If a request fails before it leaves, the bot waits and
sends again; if the response is lost, it reads the session back first. If the arena stays
unreachable, the bot stops cleanly and prints the command that continues the same session.
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
DEFAULT_STYLE = {"snake": "words", "2048": "v3"}  # measured best fact wording per game (docs/experiments.md E3, E9)


class EventLog:
    """Extra live events for the viewer (decision written BEFORE the move is sent)."""

    def __init__(self, path: Path) -> None:
        self._fh = open(path, "a", encoding="utf-8", newline="\n")

    def write(self, obj: dict) -> None:
        self._fh.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()


def ms(t0: float, t1: float) -> int:
    return int(round((t1 - t0) * 1000))


def _not_sent_types() -> tuple[type, ...]:
    try:
        from .client import NotSent

        return (NotSent,)
    except ImportError:  # pragma: no cover
        return ()


SERVER_ERROR_LIMIT = 3


def _play_loop(client: Any, decider: LayaMoveDecider, sid: str, log: SpecLog, events: EventLog, resp: dict,
               quiet: bool, max_rejects: int, say) -> dict:
    """Plays until the server says done. Returns the last server response."""
    t_prev_resp = time.monotonic()
    state = resp["state"]
    rejects_this_step: set[str] = set()
    # A move the arena keeps answering with a server error (and never applies) is set aside for this step after
    # SERVER_ERROR_LIMIT tries, and Laya chooses among the other moves; nothing is logged as applied or rejected
    server_errors: dict[str, int] = {}
    set_aside: set[str] = set()
    not_sent = _not_sent_types()
    while not resp.get("done"):
        t_state = time.monotonic()
        dec = decider.decide(state, applied=log.applied, fallbacks=log.fallbacks, exclude=rejects_this_step | set_aside)
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
        except not_sent as exc:
            # The move never left: confirm the server did not move, then decide and send again
            say(f"step {step}: move not sent ({exc}); checking the session before trying again")
            events.write({"type": "network", "step": step, "what": "not_sent", "detail": str(exc), "ts": utc_ts()})
            _, now = client.get(sid)
            if now.get("steps", -1) != log.applied:
                raise RuntimeError(f"server moved although the request was not sent: {now.get('steps')} vs {log.applied}")
            continue
        except SubmissionAmbiguous as exc:
            # The move may or may not have landed: read the session back instead of resending
            say(f"step {step}: no clear answer ({exc}); reading the session back")
            code, body = client.get(sid)
            if body.get("steps", -1) <= log.applied:
                events.write({"type": "reconcile", "step": step, "verdict": "not_applied", "ts": utc_ts()})
                n = server_errors[dec.action] = server_errors.get(dec.action, 0) + 1
                if n >= SERVER_ERROR_LIMIT:
                    set_aside.add(dec.action)
                    say(f"step {step}: the arena failed '{dec.action}' {n} times without applying it; asking Laya "
                        f"to choose among the other moves")
                    events.write({"type": "set_aside", "step": step, "action": dec.action, "server_errors": n,
                                  "ts": utc_ts()})
                    legal = [d for d, f in dec.facts.items() if f.legal]
                    if legal and set(legal) <= set_aside | rejects_this_step:
                        raise RuntimeError(f"the arena fails every legal move at step {step}")
                time.sleep(min(10.0, 2.0 * n))  # give the arena a moment instead of hammering it
                continue
            events.write({"type": "reconcile", "step": step, "verdict": "applied", "ts": utc_ts()})
        t_resp = time.monotonic()
        timing = {"decide_ms": ms(t_state, t_decided), "api_ms": ms(t_send, t_resp), "turn_ms": ms(t_prev_resp, t_resp)}
        t_prev_resp = t_resp

        if "error" in body or code >= 400:
            # Rejected by the game: log it with the state the game reports now, then ask Laya again without that move
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
        server_errors, set_aside = {}, set()
        if hasattr(decider, "note_applied"):
            decider.note_applied()
        resp, state = body, body["state"]
        if not quiet:
            print(f"step {step:>3} {dec.action:>5} [{dec.source}] p={dec.confidence:.3f} "
                  f"score={resp.get('score')} laya={dec.laya_ms:.0f}ms api={timing['api_ms']}ms", flush=True)
    return resp


def _finish(client: Any, sid: str, game: str, folder: Path, log: SpecLog, events: EventLog, interrupted: str | None,
            model_source: str, say) -> dict | None:
    """Saves the final response (section 3.5) when the arena can be read; never raises."""
    points = GAMES[game]["points"]
    final = None
    try:
        _, final = client.get(sid)
    except Exception as exc:  # noqa: BLE001 - shutdown must not lose the log
        say(f"could not read the final session state: {exc}")
    try:
        if final is not None and final.get("done"):
            save_final_response(folder, sid, final)
        events.write({"type": "session_end", "session_id": sid, "score": (final or {}).get("score"),
                      "won": (final or {}).get("won"), "steps": (final or {}).get("steps"),
                      "done": (final or {}).get("done"), "points": points(final) if final else None,
                      "interrupted": interrupted, "ts": utc_ts()})
    finally:
        log.close()
        events.close()
    if final is None or not final.get("done"):
        say("")
        say(f"Session {sid} is still open on the arena at step {log.applied}. Continue it with:")
        say(f"  python -m laya_agent.arena.runner --game {game} --model {model_source} --resume {sid}")
    return final


def _report(folder: Path, sid: str, game: str, final: dict | None) -> dict:
    points = GAMES[game]["points"]
    report = verify_log(folder / f"{sid}.jsonl", final if final and final.get("done") else None)
    report["points"] = points(final) if final else None
    report["won"] = (final or {}).get("won")
    report["done"] = (final or {}).get("done")
    return report


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
    model_source = getattr(decider, "model_source", decider.model)
    events.write({"type": "session_start", "session_id": sid, "game": game, "agent_name": agent_name,
                  "env": getattr(client, "env", "HOSTED"), "design": decider.template, "offer": decider.offer,
                  "model": decider.model, "model_source": model_source,
                  "device": (load_info or {}).get("device"), "load": load_info,
                  "first_response": resp, "ts": utc_ts()})
    return _run(client, decider, sid, game, folder, log, events, resp, quiet, max_rejects, model_source)


def resume_session(client: Any, decider: LayaMoveDecider, game: str, runs_dir: Path, sid: str,
                   load_info: dict | None = None, quiet: bool = False, max_rejects: int = 5) -> dict:
    """Continues an open session from its existing log: same file, hash chain continued, no step gap."""
    folder = runs_dir / game
    path = folder / f"{sid}.jsonl"
    if not path.exists():
        raise SystemExit(f"no log at {path}; resume needs the original session log")
    say = print if not quiet else (lambda *_: None)
    log, lines, torn = SpecLog.resume(path, sid, game)
    events = EventLog(folder / f"{sid}.events.jsonl")
    model_source = getattr(decider, "model_source", decider.model)
    code, resp = client.get(sid)
    if code != 200 or "state" not in resp:
        log.close()
        events.close()
        raise SystemExit(f"cannot read session {sid}: HTTP {code} {resp}")
    applied = [ln for ln in lines if ln["result"] == "applied"]
    last_state = applied[-1]["state_after"] if applied else None
    server_steps = resp.get("steps")
    if server_steps == log.applied:
        if last_state is not None and resp["state"] != last_state:
            log.close()
            events.close()
            raise SystemExit("cannot resume: the server board differs from the last logged board")
    elif server_steps == log.applied + 1 and applied:
        # The last move landed but its response was lost before the line was written
        log.close()
        events.close()
        raise SystemExit(f"the server has one more move ({server_steps}) than the log ({log.applied}); "
                         "that move's line cannot be rebuilt honestly, stop here and record the session as is")
    else:
        log.close()
        events.close()
        raise SystemExit(f"cannot resume: server steps {server_steps}, log has {log.applied} applied lines")
    if hasattr(decider, "restore"):
        decider.restore([ln["state_before"] for ln in applied])
    events.write({"type": "resume", "session_id": sid, "game": game, "from_step": log.applied + 1,
                  "server_steps": server_steps, "server_done": resp.get("done"), "torn_line_removed": torn,
                  "model": decider.model, "model_source": model_source, "device": (load_info or {}).get("device"),
                  "load": load_info, "ts": utc_ts()})
    say(f"resuming {sid} at step {log.applied + 1} (server agrees: {server_steps} moves, board matches)")
    return _run(client, decider, sid, game, folder, log, events, resp, quiet, max_rejects, model_source)


def _run(client, decider, sid, game, folder, log, events, resp, quiet, max_rejects, model_source) -> dict:
    say = print if not quiet else (lambda *_: None)
    if hasattr(client, "on_wait"):
        client.on_wait = lambda msg: say(f"  {msg}")
    interrupted = None
    try:
        _play_loop(client, decider, sid, log, events, resp, quiet, max_rejects, say)
    except KeyboardInterrupt:
        interrupted = "stopped by hand"
        raise
    except Exception as exc:
        interrupted = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        final = _finish(client, sid, game, folder, log, events, interrupted, model_source, say)
    return _report(folder, sid, game, final)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid-spec", default=None, help="JSON field mapping that registers a new grid game (stage 3)")
    ap.add_argument("--game", required=True, help="snake | 2048 | the name given in --grid-spec")
    ap.add_argument("--resume", default=None, metavar="SESSION_ID", help="continue an open session from its log")
    ap.add_argument("--sim", action="store_true", help="use the LOCAL simulator instead of the real arena")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--runs", default="runs", help="output folder (sim runs go to runs_sim by default)")
    ap.add_argument("--template", default="noul_nodir")
    ap.add_argument("--offer", default="legal", choices=["legal", "all"])
    ap.add_argument("--style", default=None, choices=["words", "numbers", "v2", "v3", "v3s", "v3n", "v3c"],
                    help="fact wording; default is the measured best per game (snake: words, 2048: v3)")
    ap.add_argument("--model", default="english")
    ap.add_argument("--device", default=None)
    ap.add_argument("--agent-name", default=AGENT_NAME)
    ap.add_argument("--patience", type=float, default=900, help="seconds to keep retrying through a network drop")
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

        client = ArenaClient(patience_s=args.patience)
        runs = Path(args.runs)
    style = args.style or DEFAULT_STYLE.get(args.game, "words")
    decider = LayaMoveDecider(args.game, model=args.model, device=args.device, template=args.template,
                              offer=args.offer, style=style)
    info = decider.load()
    print(f"laya loaded: {info}", flush=True)
    try:
        if args.resume:
            report = resume_session(client, decider, args.game, runs, args.resume, info, args.quiet)
        else:
            report = play_session(client, decider, args.game, runs, args.agent_name, info, args.quiet)
    except KeyboardInterrupt:
        print("stopped by hand", flush=True)
        return 130
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["ok"] and report.get("done") else 1


if __name__ == "__main__":
    sys.exit(main())
