import json
import os
import threading
import time
import urllib.error
import urllib.request

import pytest

from laya_agent.arena.spec_log import SpecLog, save_final_response
from laya_agent.viewer.arena_web import make_server, points_2048, snake_points

DIRS = ("up", "down", "left", "right")
SID = "snake-test-0001"


def snake_state(body, food, eaten, direction):
    grid = [[0] * 6 for _ in range(6)]
    for i, (x, y) in enumerate(body):
        grid[y][x] = 3 if i == 0 else 1
    grid[food[1]][food[0]] = 2
    return {"grid": grid, "snake": [{"x": x, "y": y} for x, y in body], "food": {"x": food[0], "y": food[1]},
            "direction": direction, "foodEaten": eaten, "width": 6, "height": 6}


def decision(chosen, source="laya"):
    probs = {d: 0.1 for d in DIRS}
    probs[chosen] = 0.7
    return {"questions": [f"Snake on a 6x6 board, eat food. Is this a good move now? Moving {d}: free cell." for d in DIRS],
            "probabilities": probs, "chosen": chosen, "confidence": probs[chosen], "source": source}


def write_events(path, rows):
    with open(path, "a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


@pytest.fixture
def runs(tmp_path):
    folder = tmp_path / "snake"
    s0 = snake_state([(2, 2), (1, 2), (0, 2)], (4, 2), 0, "right")
    s1 = snake_state([(3, 2), (2, 2), (1, 2)], (4, 2), 0, "right")
    s2 = snake_state([(4, 2), (3, 2), (2, 2), (1, 2)], (1, 4), 1, "right")
    s3 = snake_state([(4, 3), (4, 2), (3, 2), (2, 2)], (1, 4), 1, "down")
    moves = [  # step, before, action, after, result
        (1, s0, "right", s1, "applied"),
        (2, s1, "left", s1, "rejected"),
        (2, s1, "right", s2, "applied"),
        (3, s2, "down", s3, "applied"),
    ]
    events = folder / f"{SID}.events.jsonl"
    log = SpecLog(folder / f"{SID}.jsonl", SID, "snake")
    write_events(events, [{"type": "session_start", "session_id": SID, "game": "snake", "agent_name": "TEST-FIXTURE",
                           "design": "noul_each_v1", "model": "english", "device": "cpu", "ts": "2026-10-16T10:00:00Z"}])
    for i, (step, before, action, after, result) in enumerate(moves):
        d = decision(action)
        write_events(events, [{"type": "decision", "session_id": SID, "step": step,
                               "facts": {x: f"Moving {x}: free cell." for x in DIRS},
                               "p_true": {x: round(p + 0.1, 3) for x, p in d["probabilities"].items()},
                               "probabilities": d["probabilities"], "chosen": action, "source": "laya",
                               "laya_choice": action, "decide_ms": 100 + i, "ts": "2026-10-16T10:00:01Z"}])
        log.write(step=step, state_before=before, action=action, state_after=after, result=result, decision=d,
                  timing={"decide_ms": 100 + i, "api_ms": 50, "turn_ms": 160 + i})
    log.close()
    # Decided but not yet sent, so it is one step ahead of the submission log
    write_events(events, [{"type": "decision", "session_id": SID, "step": 4, "facts": {x: "x" for x in DIRS},
                           "p_true": {x: 0.5 for x in DIRS}, "probabilities": {x: 0.25 for x in DIRS},
                           "chosen": "left", "source": "laya", "laya_choice": "left", "decide_ms": 90,
                           "ts": "2026-10-16T10:00:02Z"}])
    return tmp_path, folder, s3


@pytest.fixture
def server(runs):
    root = runs[0]
    srv = make_server(root, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


def get(url):
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read())


def test_points_follow_the_published_formulas():
    assert snake_points(10, False) == 600
    assert snake_points(15, True) == 1000
    assert snake_points(20, True) == 1000
    assert points_2048(512, 3500) == 3 * 143 + 3
    assert points_2048(64, 999) == 0
    assert points_2048(0, 0) == 0


def test_sessions_lists_the_snake_session(server):
    body = get(f"{server}/api/sessions")
    assert body["newest"] == SID
    (s,) = body["sessions"]
    assert s["game"] == "snake"
    assert s["session_id"] == SID
    assert s["steps"] == 3
    assert s["last_score"] == 1  # foods eaten, no final score yet
    assert s["done"] is False
    assert s["agent_name"] == "TEST-FIXTURE"


def test_session_returns_lines_events_and_summary(server):
    body = get(f"{server}/api/session?id={SID}&after=0")
    assert [line["step"] for line in body["lines"]] == [1, 2, 2, 3]
    assert [line["result"] for line in body["lines"]] == ["applied", "rejected", "applied", "applied"]
    assert body["next_after"] == 4
    assert [e["type"] for e in body["events"]] == ["session_start"] + ["decision"] * 5
    assert body["events"][-1]["step"] == 4  # the decision written before its move was sent
    assert body["session_start"]["model"] == "english"
    assert body["final"] is None
    summ = body["summary"]
    assert (summ["steps"], summ["rejected"], summ["lines"]) == (3, 1, 4)
    assert summ["foods"] == 1 and summ["length"] == 4
    assert summ["points"] == 60 and summ["points_source"] == "computed"
    assert summ["fallback_share"] == 0.0
    assert summ["done"] is False
    assert summ["timing"]["decide_ms"]["last"] == 103
    assert summ["timing"]["decide_ms"]["mean"] == 101.5
    assert summ["timing"]["api_ms"]["p95"] == 50
    assert summ["timing"]["turn_ms"]["last"] == 163

    newer = get(f"{server}/api/session?id={SID}&after=3&eafter=6")
    assert [line["step"] for line in newer["lines"]] == [3]
    assert newer["events"] == [] and newer["reset"] is False


def test_session_counts_fallbacks_and_reported_points(server, runs):
    folder = runs[1]
    write_events(folder / f"{SID}.events.jsonl",
                 [{"type": "session_end", "session_id": SID, "score": 10, "won": False, "steps": 3, "points": 60}])
    body = get(f"{server}/api/session?id={SID}")
    assert body["summary"]["done"] is True
    assert body["summary"]["points_source"] == "session_end"
    assert body["session_end"]["score"] == 10


def test_verify_reports_an_intact_chain_and_final_response(server, runs):
    folder, last_state = runs[1], runs[2]
    body = get(f"{server}/api/verify?id={SID}")
    assert body["ok"] is True, body["problems"]
    assert body["chain_ok"] is True
    assert body["lines"] == 4 and body["applied"] == 3

    save_final_response(folder, SID, {"session_id": SID, "steps": 3, "state": last_state, "score": 1, "done": True})
    body = get(f"{server}/api/verify?id={SID}")
    assert body["ok"] is True, body["problems"]
    assert body["final_done"] is True
    session = get(f"{server}/api/session?id={SID}")
    assert session["final"]["score"] == 1
    assert session["summary"]["done"] is True


def test_half_written_line_waits_and_tampering_breaks_the_chain(server, runs):
    path = runs[1] / f"{SID}.jsonl"
    with open(path, "ab") as fh:
        fh.write(b'{"session_id": "' + SID.encode() + b'", "step": 4')  # still being written
    assert len(get(f"{server}/api/session?id={SID}")["lines"]) == 4
    assert get(f"{server}/api/verify?id={SID}")["ok"] is True

    lines = path.read_bytes().split(b"\n")[:4]
    lines[1] = lines[1].replace(b'"rejected"', b'"applied"')
    path.write_bytes(b"\n".join(lines) + b"\n")
    body = get(f"{server}/api/verify?id={SID}")
    assert body["ok"] is False
    assert body["chain_ok"] is False


def test_newest_session_is_listed_first(server, runs):
    root = runs[0]
    sid = "g2048-test-0002"
    log = SpecLog(root / "2048" / f"{sid}.jsonl", sid, "2048")
    before = {"grid": [[2, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 2]], "score": 0, "best": 0}
    after = {"grid": [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 2], [2, 0, 0, 2]], "score": 0, "best": 0}
    log.write(step=1, state_before=before, action="down", state_after=after, result="applied",
              decision={**decision("down", "fallback"), "questions": ["q"]},
              timing={"decide_ms": 5, "api_ms": 5, "turn_ms": 10})
    log.close()
    future = time.time() + 60
    os.utime(root / "2048" / f"{sid}.jsonl", (future, future))

    body = get(f"{server}/api/sessions")
    assert [s["session_id"] for s in body["sessions"]] == [sid, SID]
    assert body["sessions"][0]["game"] == "2048"
    summ = get(f"{server}/api/session?id={sid}")["summary"]
    assert summ["best_tile"] == 2 and summ["fallback_share"] == 1.0


def test_unknown_session_is_404_and_page_is_served(server):
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(f"{server}/api/session?id=../../etc", timeout=5)
    assert err.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(f"{server}/api/verify?id=nope", timeout=5)
    assert err.value.code == 404
    page = urllib.request.urlopen(f"{server}/", timeout=5).read().decode()
    assert "CodeYatri | Laya Decision Viewer" in page
    for asset in ("/style.css", "/app.js"):
        assert urllib.request.urlopen(f"{server}{asset}", timeout=5).status == 200
