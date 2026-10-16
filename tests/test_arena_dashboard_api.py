"""Endpoints the dashboard in frontend/ reads: /api/history, /api/step, session status and env labels."""

import json
import os
import threading
import time
import urllib.error
import urllib.request

import pytest

from laya_agent.arena.spec_log import SpecLog, save_final_response
from laya_agent.viewer import arena_web
from laya_agent.viewer.arena_web import env_kind, make_server, pair_decisions, session_status

DIRS = ("up", "down", "left", "right")
SID = "dash-test-0001"


def snake_state(body, food, eaten, direction):
    grid = [[0] * 6 for _ in range(6)]
    for i, (x, y) in enumerate(body):
        grid[y][x] = 3 if i == 0 else 1
    grid[food[1]][food[0]] = 2
    return {"grid": grid, "snake": [{"x": x, "y": y} for x, y in body], "food": {"x": food[0], "y": food[1]},
            "direction": direction, "foodEaten": eaten, "width": 6, "height": 6}


def write_rows(path, rows):
    with open(path, "a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def decision_block(asked, p_true, chosen, source="laya"):
    total = sum(p_true.values())
    probs = {d: (round(p_true[d] / total, 6) if d in p_true else 0.0) for d in DIRS}
    return {"questions": [f"Is this a good move now? This move: fact for {d}." for d in DIRS if d in asked],
            "probabilities": probs, "chosen": chosen, "confidence": probs[chosen], "source": source}


def decision_event(step, p_true, chosen, kinds, source="laya", reason=""):
    total = sum(p_true.values())
    return {"type": "decision", "session_id": SID, "step": step,
            "facts": {d: f"move {d}: fact for {d}." for d in DIRS}, "kinds": kinds, "p_true": p_true,
            "probabilities": {d: (round(p_true[d] / total, 6) if d in p_true else 0.0) for d in DIRS},
            "chosen": chosen, "source": source, "laya_choice": chosen, "reason": reason,
            "state_text": f"state text {step}", "decide_ms": 100, "laya_ms": 95.5, "ts": "2026-10-16T10:00:01Z"}


@pytest.fixture
def runs(tmp_path):
    folder = tmp_path / "snake"
    s0 = snake_state([(2, 2), (1, 2), (0, 2)], (4, 2), 0, "right")
    s1 = snake_state([(3, 2), (2, 2), (1, 2)], (4, 2), 0, "right")
    s2 = snake_state([(4, 2), (3, 2), (2, 2), (1, 2)], (1, 4), 1, "right")
    events = folder / f"{SID}.events.jsonl"
    log = SpecLog(folder / f"{SID}.jsonl", SID, "snake")
    legal = {"up": "move", "down": "move", "left": "reverse", "right": "move"}
    write_rows(events, [{"type": "session_start", "session_id": SID, "game": "snake", "agent_name": "CodeYatri",
                         "env": "HOSTED", "design": "noul_nodir", "model": "english", "device": "cuda",
                         "ts": "2026-10-16T10:00:00Z"}])
    # step 1 applied
    p1 = {"up": 0.4, "down": 0.3, "right": 0.7}
    write_rows(events, [decision_event(1, p1, "right", legal)])
    log.write(step=1, state_before=s0, action="right", state_after=s1, result="applied",
              decision=decision_block(p1, p1, "right"), timing={"decide_ms": 100, "api_ms": 40, "turn_ms": 150})
    # step 2: the server rejects "up", then the retry without "up" is applied
    p2a = {"up": 0.8, "down": 0.3, "right": 0.6}
    write_rows(events, [decision_event(2, p2a, "up", legal)])
    log.write(step=2, state_before=s1, action="up", state_after=s1, result="rejected",
              decision=decision_block(p2a, p2a, "up"), timing={"decide_ms": 101, "api_ms": 41, "turn_ms": 151})
    write_rows(events, [{"type": "rejected", "step": 2, "action": "up", "error": "invalid move", "ts": "x"}])
    # a lost response that never landed: decided, reconciled as not applied, decided again
    p2b = {"down": 0.3, "right": 0.6}
    write_rows(events, [decision_event(2, p2b, "right", legal),
                        {"type": "reconcile", "step": 2, "verdict": "not_applied", "ts": "x"},
                        decision_event(2, p2b, "right", legal, source="fallback", reason="logged reason")])
    log.write(step=2, state_before=s1, action="right", state_after=s2, result="applied",
              decision=decision_block(p2b, p2b, "right", "fallback"), timing={"decide_ms": 102, "api_ms": 42, "turn_ms": 152})
    log.close()
    # decided, not sent yet
    write_rows(events, [decision_event(3, {"up": 0.5, "down": 0.2}, "up", legal)])
    return tmp_path, folder, s2


@pytest.fixture
def server(runs):
    srv = make_server(runs[0], "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


def get(url):
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read())


def test_status_and_env_rules():
    assert session_status(True, 1.0) == "finished"
    assert session_status(False, 3.0) == "live"
    assert session_status(False, 60.0) == "idle"
    assert session_status(False, 600.0) == "interrupted"
    assert env_kind({"env": "HOSTED", "agent_name": "CodeYatri"}) == "hosted"
    assert env_kind({"env": "LOCAL_SIM", "agent_name": "CodeYatri"}) == "simulator"
    assert env_kind({"env": "HOSTED", "agent_name": "SIM-EVAL"}) == "simulator"
    assert env_kind({"agent_name": "TEST-FIXTURE"}) == "simulator"
    assert env_kind({"agent_name": "CodeYatri"}) == "unknown"
    assert env_kind(None) == "unknown"


def test_pairing_skips_not_applied_decisions_and_keeps_the_pending_one():
    lines = [{"step": 1, "action": "right"}, {"step": 2, "action": "up"}, {"step": 2, "action": "right"}]
    events = [{"type": "decision", "step": 1, "chosen": "right"},
              {"type": "decision", "step": 2, "chosen": "up"},
              {"type": "decision", "step": 2, "chosen": "right", "tag": "lost"},
              {"type": "reconcile", "step": 2, "verdict": "not_applied"},
              {"type": "decision", "step": 2, "chosen": "right", "tag": "sent"},
              {"type": "decision", "step": 3, "chosen": "down"}]
    paired, pending = pair_decisions(lines, events)
    assert [p["chosen"] for p in paired] == ["right", "up", "right"]
    assert paired[2]["tag"] == "sent"
    assert pending["step"] == 3
    paired, pending = pair_decisions(lines, events[:-1])
    assert pending is None


def test_history_returns_paired_records_and_pending(server):
    body = get(f"{server}/api/history?id={SID}")
    assert body["total"] == 3 and body["next_after"] == 3 and body["reset"] is False
    assert [r["result"] for r in body["records"]] == ["applied", "rejected", "applied"]
    first, rejected, retry = body["records"]
    assert first["event"]["p_true"] == {"up": 0.4, "down": 0.3, "right": 0.7}
    assert first["state_before"]["snake"][0] == {"x": 2, "y": 2}
    assert rejected["error"] == "invalid move"
    assert retry["source"] == "fallback" and retry["event"]["reason"] == "logged reason"
    assert "up" not in retry["event"]["p_true"]
    assert body["pending"]["step"] == 3 and body["pending"]["chosen"] == "up"
    assert body["status"] == "live"
    assert body["summary"]["env_kind"] == "hosted" and body["summary"]["env"] == "HOSTED"

    page = get(f"{server}/api/history?id={SID}&after=1&limit=1")
    assert [r["i"] for r in page["records"]] == [1] and page["next_after"] == 2
    assert get(f"{server}/api/history?id={SID}&after=99")["reset"] is True


def test_step_maps_questions_to_the_asked_directions(server):
    body = get(f"{server}/api/step?id={SID}&i=2")
    assert body["line"]["action"] == "right" and body["line"]["hash"]
    assert body["event"]["state_text"] == "state text 2"
    assert body["questions_by_dir"] == {"down": "Is this a good move now? This move: fact for down.",
                                        "right": "Is this a good move now? This move: fact for right."}
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(f"{server}/api/step?id={SID}&i=7", timeout=5)
    assert err.value.code == 404


def test_sessions_carry_env_and_status_and_finish(server, runs):
    (s,) = get(f"{server}/api/sessions")["sessions"]
    assert (s["env"], s["env_kind"], s["status"], s["model"], s["device"]) == ("HOSTED", "hosted", "live", "english", "cuda")
    assert s["rejected"] == 1 and s["fallbacks"] == 1 and s["fallback_share"] == 0.5
    folder, state = runs[1], runs[2]
    save_final_response(folder, SID, {"session_id": SID, "steps": 2, "state": state, "score": 60, "done": True})
    assert get(f"{server}/api/sessions")["sessions"][0]["status"] == "finished"
    old = time.time() - 3600
    for p in folder.iterdir():
        if p.name.endswith(".final.json"):
            p.unlink()
        else:
            os.utime(p, (old, old))
    assert get(f"{server}/api/sessions")["sessions"][0]["status"] == "interrupted"


def test_built_app_is_served_and_classic_stays_available(server, tmp_path, monkeypatch):
    classic = urllib.request.urlopen(f"{server}/classic", timeout=5).read().decode()
    assert "CodeYatri | Laya Decision Viewer" in classic and 'src="app.js"' in classic
    for asset in ("/classic/style.css", "/classic/app.js", "/style.css", "/app.js"):
        assert urllib.request.urlopen(f"{server}{asset}", timeout=5).status == 200

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<title>CodeYatri | Laya Decision Viewer</title>NEW-APP", encoding="utf-8")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setattr(arena_web, "APP_DIST", dist)
    assert "NEW-APP" in urllib.request.urlopen(f"{server}/", timeout=5).read().decode()
    with urllib.request.urlopen(f"{server}/assets/index-abc123.js", timeout=5) as resp:
        assert resp.headers["Content-Type"].startswith("application/javascript")
        assert "immutable" in resp.headers["Cache-Control"]
    for bad in ("/assets/..%2Findex.html", "/assets/../index.html", "/assets/missing.js", "/a/b/c.js"):
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(f"{server}{bad}", timeout=5)
        assert err.value.code == 404
