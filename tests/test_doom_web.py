"""Doom dashboard data: session listing, live decisions, frames and the proof checks, without the engine."""

import hashlib
import json

from laya_agent.arena.spec_log import SpecLog
from laya_agent.doom.engine import ACTIONS
from laya_agent.viewer.arena_web import RunStore
from laya_agent.viewer.doom_web import DoomStore


def write_session(folder, sid="doom-test-1", steps=3, finished=True):
    folder.mkdir(parents=True, exist_ok=True)
    log = SpecLog(folder / f"{sid}.jsonl", sid, "doom", keys=ACTIONS)
    events = open(folder / f"{sid}.events.jsonl", "w", encoding="utf-8")
    events.write(json.dumps({"type": "session_start", "settings": {"scenario": "defend_the_center", "seed": 1}}) + "\n")
    probs = {a: 0.0 for a in ACTIONS}
    probs["shoot"], probs["forward"] = 0.7, 0.3
    for step in range(1, steps + 1):
        events.write(json.dumps({"type": "decision", "step": step, "tic": 4 * step, "state_text": "Doom.",
                                 "facts": {"shoot": "fires"}, "p_true": {"shoot": 0.9, "forward": 0.4},
                                 "probabilities": probs, "chosen": "shoot", "source": "laya", "laya_ms": 90}) + "\n")
        log.write(step=step, state_before={"tic": 4 * step, "health": 100, "kills": step - 1}, action="shoot",
                  state_after={"tic": 4 * step + 4}, result="applied",
                  decision={"questions": ["q"], "probabilities": probs, "chosen": "shoot", "confidence": 0.7,
                            "source": "laya"}, timing={"decide_ms": 90, "api_ms": 1, "turn_ms": 95})
    log.close()
    events.close()
    lmp = folder / f"{sid}.lmp"
    lmp.write_bytes(b"demo bytes")
    if finished:
        (folder / f"{sid}.final.json").write_text(json.dumps({
            "session_id": sid, "steps": steps, "kills": steps - 1, "dead": True, "exited": False, "health": 0,
            "settings": {"scenario": "defend_the_center", "seed": 1}, "log_verified": True,
            "recording_sha256": hashlib.sha256(b"demo bytes").hexdigest()}))
    (folder / f"{sid}.frames").mkdir(exist_ok=True)
    (folder / f"{sid}.frames" / "00002.jpg").write_bytes(b"jpg")
    return sid


def test_doom_sessions_are_listed_and_served(tmp_path):
    sid = write_session(tmp_path / "runs" / "doom")
    store = DoomStore(tmp_path / "runs")
    rows = store.sessions()
    assert [r["session_id"] for r in rows] == [sid] and rows[0]["kills"] == 2 and rows[0]["done"]
    body = store.session(sid, after=1)
    assert body["total"] == 3 and [d["step"] for d in body["decisions"]] == [2, 3]
    assert body["decisions"][0]["hash"] and body["decisions"][0]["state_before"]["kills"] == 1
    assert store.frame(sid, "2") == b"jpg" and store.frame(sid, "9") is None


def test_doom_proof_checks_catch_a_changed_recording(tmp_path):
    folder = tmp_path / "runs" / "doom"
    sid = write_session(folder)
    store = DoomStore(tmp_path / "runs")
    assert store.verify(sid)["ok"]
    (folder / f"{sid}.lmp").write_bytes(b"edited")
    v = store.verify(sid)
    assert not v["ok"] and v["checks"]["recording matches its sha256"] is False


def test_doom_folders_stay_out_of_the_arena_session_list(tmp_path):
    write_session(tmp_path / "runs" / "doom")
    assert RunStore(tmp_path / "runs").scan() == {}
