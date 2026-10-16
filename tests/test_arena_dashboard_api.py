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


def write_session(folder, sid, env, agent, steps=2):
    log = SpecLog(folder / f"{sid}.jsonl", sid, "snake")
    events = folder / f"{sid}.events.jsonl"
    write_rows(events, [{"type": "session_start", "session_id": sid, "game": "snake", "agent_name": agent, "env": env,
                         "ts": "2026-10-16T10:00:00Z"}])
    body = [(2, 2), (1, 2), (0, 2)]
    for step in range(1, steps + 1):
        before = snake_state(body, (5, 5), 0, "right")
        body = [(body[0][0] + 1, 2)] + body[:-1]
        after = snake_state(body, (5, 5), 0, "right")
        p = {"up": 0.3, "down": 0.3, "right": 0.6}
        write_rows(events, [decision_event(step, p, "right", {"up": "move", "down": "move", "left": "reverse", "right": "move"})])
        log.write(step=step, state_before=before, action="right", state_after=after, result="applied",
                  decision=decision_block(p, p, "right"), timing={"decide_ms": 10, "api_ms": 0, "turn_ms": 10})
    log.close()


def test_sim_roots_get_unique_keys_and_a_source(tmp_path):
    real = tmp_path / "runs" / "snake"
    real.mkdir(parents=True)
    write_session(real, "same-id", "HOSTED", "CodeYatri")
    for name in ("runs_sim_a", "runs_sim_b"):
        folder = tmp_path / name / "design" / "snake"
        folder.mkdir(parents=True)
        write_session(folder, "same-id", "LOCAL_SIM", "SIM-EVAL", steps=3)
    roots = arena_web.resolve_sim_roots([str(tmp_path / "runs_sim*"), str(tmp_path / "runs")])
    assert [r.name for r in roots] == ["runs_sim_a", "runs_sim_b", "runs"]
    srv = make_server(tmp_path / "runs", "127.0.0.1", 0, roots)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        body = get(f"{base}/api/sessions")
        rows = {s["key"]: s for s in body["sessions"]}
        # the main runs folder passed as a simulator root is ignored, so nothing is listed twice
        assert sorted(rows) == ["runs_sim_a/design/snake/same-id", "runs_sim_b/design/snake/same-id", "same-id"]
        assert rows["same-id"]["source"] == "arena" and rows["same-id"]["origin"] == "runs"
        assert rows["runs_sim_a/design/snake/same-id"]["source"] == "simulator"
        assert rows["runs_sim_a/design/snake/same-id"]["steps"] == 3 and rows["same-id"]["steps"] == 2
        # a plain session id still means the main runs folder, as the classic viewer expects
        assert get(f"{base}/api/session?id=same-id")["summary"]["steps"] == 2
        hist = get(f"{base}/api/history?id=runs_sim_b/design/snake/same-id")
        assert hist["total"] == 3 and hist["source"] == "simulator" and hist["key"] == "runs_sim_b/design/snake/same-id"
        assert get(f"{base}/api/verify?id=runs_sim_b/design/snake/same-id")["ok"] is True
    finally:
        srv.shutdown()
        srv.server_close()


def test_unlabelled_sessions_take_their_source_from_the_folder():
    assert arena_web.session_source("hosted", "sim") == "arena"
    assert arena_web.session_source("simulator", "runs") == "simulator"
    assert arena_web.session_source("unknown", "runs") == "arena"
    assert arena_web.session_source("unknown", "sim") == "simulator"


BOARD = {"game": "snake", "leaderboard": [
    {"rank": 1, "agentName": "OtherTeam", "score": 1000, "steps": 120, "gameId": "aaaa-1111", "timestamp": 1792100000000},
    {"rank": 2, "agentName": "CodeYatri", "score": 1000, "steps": 127, "gameId": SID, "timestamp": 1792133933372},
]}


def test_leaderboard_caches_matches_local_sessions_and_keeps_the_last_good_copy(server, monkeypatch):
    calls = []

    def fake_fetch(game):
        calls.append(game)
        return json.loads(json.dumps(BOARD))

    monkeypatch.setattr(arena_web, "fetch_leaderboard_json", fake_fetch)
    first = get(f"{server}/api/leaderboard?game=snake")
    assert first["stale"] is False and first["error"] is None and first["fetched_at"]
    assert first["leaderboard"] == BOARD["leaderboard"]
    assert first["local"] == {SID: SID}  # the CodeYatri row is the local session
    assert get(f"{server}/api/leaderboard?game=snake")["fetched_at"] == first["fetched_at"]
    assert calls == ["snake"]  # served from the 60 s cache

    def offline(game):
        raise urllib.error.URLError("no network")

    monkeypatch.setattr(arena_web, "LEADERBOARD_TTL_S", 0.0)
    monkeypatch.setattr(arena_web, "fetch_leaderboard_json", offline)
    stale = get(f"{server}/api/leaderboard?game=snake")
    assert stale["stale"] is True and "no network" in stale["error"]
    assert stale["leaderboard"] == BOARD["leaderboard"] and stale["fetched_at"] == first["fetched_at"]


def test_leaderboard_without_a_copy_never_invents_rows(server, monkeypatch):
    def offline(game):
        raise TimeoutError("timed out")

    monkeypatch.setattr(arena_web, "fetch_leaderboard_json", offline)
    body = get(f"{server}/api/leaderboard?game=2048")
    assert body["leaderboard"] == [] and body["stale"] is True and body["fetched_at"] is None
    assert "timed out" in body["error"]
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(f"{server}/api/leaderboard?game=../x", timeout=5)
    assert err.value.code == 400


def test_leaderboard_request_uses_the_agreed_url_timeout_and_user_agent(monkeypatch):
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps(BOARD).encode()

    def fake_urlopen(req, timeout):
        seen.update(url=req.full_url, ua=req.get_header("User-agent"), timeout=timeout)
        return Resp()

    monkeypatch.setattr(arena_web.urllib.request, "urlopen", fake_urlopen)
    assert arena_web.fetch_leaderboard_json("snake")["game"] == "snake"
    assert seen == {"url": "https://topgameai.com/api/arena/leaderboard/snake", "ua": "CodeYatri-laya-agent/1.0", "timeout": 10.0}
