"""Crash, network-drop and resume behaviour of the arena runner."""

import json

import pytest

from laya_agent.arena.client import NotSent
from laya_agent.arena.decider import LayaMoveDecider
from laya_agent.arena.runner import play_session, resume_session
from laya_agent.arena.sims import FakeArena
from laya_agent.arena.spec_log import SpecLog, verify_log
from laya_agent.contracts import SubmissionAmbiguous


class Router:
    loaded_revisions = {}

    def __init__(self, crash_on_call=None):
        self.calls = 0
        self.crash_on_call = crash_on_call

    def load(self, name):
        return type("A", (), {"device": "cpu"})()

    def predict(self, state, questions, model=None):
        self.calls += 1
        if self.crash_on_call and self.calls == self.crash_on_call:
            raise ConnectionError("simulated crash in the middle of a game")

        def score(t):
            return 0.05 if "game over" in t else 0.9 if "eats the food" in t else 0.7 if "closer" in t else 0.4
        return {"answers": {q: {"type": "noul", "noul": score(d["instructions"])} for q, d in questions.items()}}


def decider(**kw):
    d = LayaMoveDecider("snake", router=Router(**kw))
    d.load()
    return d


def lines_of(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_crash_then_resume_completes_one_verified_log(tmp_path):
    arena = FakeArena(seed=11)
    with pytest.raises(ConnectionError):
        play_session(arena, decider(crash_on_call=20), "snake", tmp_path, "TEST", quiet=True)
    sid = next(iter(arena.sessions))
    log = tmp_path / "snake" / f"{sid}.jsonl"
    assert len(lines_of(log)) == 19
    assert not (tmp_path / "snake" / f"{sid}.final.json").exists()  # game still open, nothing final yet

    report = resume_session(arena, decider(), "snake", tmp_path, sid, quiet=True)
    assert report["ok"], report["problems"]
    assert report["done"]
    lines = lines_of(log)
    assert [ln["step"] for ln in lines if ln["result"] == "applied"] == list(range(1, len(lines) + 1))
    final = json.loads((tmp_path / "snake" / f"{sid}.final.json").read_text(encoding="utf-8"))
    assert final["steps"] == len(lines)
    events = [json.loads(x) for x in (tmp_path / "snake" / f"{sid}.events.jsonl").read_text().splitlines()]
    assert any(e["type"] == "resume" and e["from_step"] == 20 for e in events)


def test_resume_matches_the_since_food_memory_of_an_uninterrupted_run(tmp_path):
    whole = FakeArena(seed=12)
    play_session(whole, decider(), "snake", tmp_path / "a", "TEST", quiet=True)
    sid_a = next(iter(whole.sessions))
    texts_a = [e["state_text"] for e in map(json.loads, (tmp_path / "a" / "snake" / f"{sid_a}.events.jsonl").read_text().splitlines()) if e["type"] == "decision"]

    split = FakeArena(seed=12)
    with pytest.raises(ConnectionError):
        play_session(split, decider(crash_on_call=30), "snake", tmp_path / "b", "TEST", quiet=True)
    sid_b = next(iter(split.sessions))
    resume_session(split, decider(), "snake", tmp_path / "b", sid_b, quiet=True)
    texts_b = [e["state_text"] for e in map(json.loads, (tmp_path / "b" / "snake" / f"{sid_b}.events.jsonl").read_text().splitlines()) if e["type"] == "decision"]
    assert texts_a == texts_b  # same questions to Laya, move for move, despite the crash


class FlakyArena(FakeArena):
    """The first action fails before sending; a later one loses its response after applying."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.calls = 0

    def act(self, sid, action):
        self.calls += 1
        if self.calls == 3:
            raise NotSent("no connection")
        if self.calls == 7:
            super().act(sid, action)
            raise SubmissionAmbiguous("response lost")
        return super().act(sid, action)


def test_not_sent_and_lost_response_never_create_rejected_or_duplicate_lines(tmp_path):
    arena = FlakyArena(seed=13)
    report = play_session(arena, decider(), "snake", tmp_path, "TEST", quiet=True)
    assert report["ok"], report["problems"]
    sid = next(iter(arena.sessions))
    lines = lines_of(tmp_path / "snake" / f"{sid}.jsonl")
    assert all(ln["result"] == "applied" for ln in lines)
    assert len(lines) == arena.sessions[sid][1].steps
    events = [json.loads(x) for x in (tmp_path / "snake" / f"{sid}.events.jsonl").read_text().splitlines()]
    assert any(e["type"] == "network" and e["what"] == "not_sent" for e in events)
    assert any(e["type"] == "reconcile" and e["verdict"] == "applied" for e in events)


def test_torn_last_line_is_set_aside_not_kept(tmp_path):
    arena = FakeArena(seed=14)
    with pytest.raises(ConnectionError):
        play_session(arena, decider(crash_on_call=8), "snake", tmp_path, "TEST", quiet=True)
    sid = next(iter(arena.sessions))
    log = tmp_path / "snake" / f"{sid}.jsonl"
    with open(log, "a", encoding="utf-8") as fh:
        fh.write('{"session_id": "half a line')
    _, lines, torn = SpecLog.resume(log, sid, "snake")
    assert torn.startswith('{"session_id"') and len(lines) == 7
    assert (tmp_path / "snake" / f"{sid}.jsonl.torn").exists()
    assert verify_log(log)["ok"]


def test_resume_refuses_when_the_server_board_differs(tmp_path):
    arena = FakeArena(seed=15)
    with pytest.raises(ConnectionError):
        play_session(arena, decider(crash_on_call=6), "snake", tmp_path, "TEST", quiet=True)
    sid = next(iter(arena.sessions))
    sim = arena.sessions[sid][1]
    sim.food = next((x, y) for y in range(sim.h) for x in range(sim.w) if (x, y) not in sim.snake and (x, y) != sim.food)
    with pytest.raises(SystemExit):  # same step count, different board
        resume_session(arena, decider(), "snake", tmp_path, sid, quiet=True)


def test_resume_refuses_when_the_server_has_an_unlogged_move(tmp_path):
    arena = FakeArena(seed=16)
    with pytest.raises(ConnectionError):
        play_session(arena, decider(crash_on_call=6), "snake", tmp_path, "TEST", quiet=True)
    sid = next(iter(arena.sessions))
    sim = arena.sessions[sid][1]
    assert sim.act(sim.direction) is None  # a move the log never recorded
    with pytest.raises(SystemExit):
        resume_session(arena, decider(), "snake", tmp_path, sid, quiet=True)
