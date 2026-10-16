"""Doom sessions in the dashboard: listed, paged and verified by the same store as Snake and 2048."""

import hashlib
import json

from laya_agent.arena.spec_log import SpecLog
from laya_agent.doom.engine import ACTIONS
from laya_agent.viewer.arena_web import RunStore
from laya_agent.viewer.doom_web import frame_bytes


def write_session(folder, sid="doom-test-1", steps=3, finished=True):
    folder.mkdir(parents=True, exist_ok=True)
    log = SpecLog(folder / f"{sid}.jsonl", sid, "doom", keys=ACTIONS)
    events = open(folder / f"{sid}.events.jsonl", "w", encoding="utf-8")
    events.write(json.dumps({"type": "session_start", "game": "doom", "agent_name": "CodeYatri",
                             "settings": {"scenario": "defend_the_center", "seed": 1}}) + "\n")
    probs = {a: 0.0 for a in ACTIONS}
    probs["shoot"], probs["forward"] = 0.7, 0.3
    for step in range(1, steps + 1):
        events.write(json.dumps({"type": "decision", "step": step, "tic": 4 * step, "state_text": "Doom.",
                                 "facts": {"shoot": "fires"}, "offered": ["shoot", "forward"],
                                 "p_true": {"shoot": 0.9, "forward": 0.4}, "probabilities": probs,
                                 "chosen": "shoot", "source": "laya", "laya_ms": 90}) + "\n")
        log.write(step=step, state_before={"tic": 4 * step, "health": 100, "kills": step - 1}, action="shoot",
                  state_after={"tic": 4 * step + 4, "health": 100, "kills": step}, result="applied",
                  decision={"questions": ["q shoot", "q forward"], "probabilities": probs, "chosen": "shoot",
                            "confidence": 0.7, "source": "laya"},
                  timing={"decide_ms": 90, "api_ms": 1, "turn_ms": 95})
    log.close()
    lmp = folder / f"{sid}.lmp"
    lmp.write_bytes(b"demo bytes")
    if finished:
        events.write(json.dumps({"type": "session_end", "steps": steps, "kills": steps, "dead": True}) + "\n")
        (folder / f"{sid}.final.json").write_text(json.dumps({
            "session_id": sid, "game": "doom", "steps": steps, "kills": steps, "dead": True, "exited": False,
            "health": 0, "settings": {"scenario": "defend_the_center", "seed": 1}, "log_verified": True,
            "recording_sha256": hashlib.sha256(b"demo bytes").hexdigest()}))
    events.close()
    (folder / f"{sid}.frames").mkdir(exist_ok=True)
    (folder / f"{sid}.frames" / "00002.jpg").write_bytes(b"jpg")
    return sid


def test_doom_sessions_join_the_main_list_with_their_outcome(tmp_path):
    sid = write_session(tmp_path / "runs" / "doom")
    store = RunStore(tmp_path / "runs")
    rows = store.sessions()
    assert [r["session_id"] for r in rows] == [sid]
    assert rows[0]["game"] == "doom" and rows[0]["done"] and rows[0]["source"] == "arena"
    hist = store.history(sid)
    assert hist["summary"]["kills"] == 3 and hist["summary"]["dead"] is True and hist["summary"]["env_kind"] == "engine"
    assert [r["action"] for r in hist["records"]] == ["shoot"] * 3
    assert hist["records"][0]["event"]["offered"] == ["shoot", "forward"]
    step = store.step(sid, 0)
    assert step["questions_by_dir"] == {"shoot": "q shoot", "forward": "q forward"}


def test_doom_verify_adds_the_recording_checks(tmp_path):
    folder = tmp_path / "runs" / "doom"
    sid = write_session(folder)
    store = RunStore(tmp_path / "runs")
    v = store.verify(sid)
    assert v["ok"] and all(v["checks"].values()) and v["frames"]
    (folder / f"{sid}.lmp").write_bytes(b"edited")
    v = store.verify(sid)
    assert not v["ok"] and v["checks"]["recording matches its sha256"] is False


def test_frames_are_served_by_step(tmp_path):
    folder = tmp_path / "runs" / "doom"
    sid = write_session(folder)
    assert frame_bytes(folder, sid, "2") == b"jpg"
    assert frame_bytes(folder, sid, "9") is None and frame_bytes(folder, sid, "x") is None
