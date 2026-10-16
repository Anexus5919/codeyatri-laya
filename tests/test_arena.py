import json

import pytest

from laya_agent.arena.decider import LayaMoveDecider
from laya_agent.arena.games import g2048_facts, snake_facts
from laya_agent.arena.runner import play_session
from laya_agent.arena.sims import FakeArena, Sim2048, SnakeSim, slide_board
from laya_agent.arena.spec_log import SpecLog, canonical_json, line_hash, verify_log

# The real arena's first Snake response, captured 2026-10-16 (session ce20b214...).
REAL_SNAKE_START = {"snake": [{"x": 6, "y": 6}, {"x": 5, "y": 6}, {"x": 4, "y": 6}], "direction": "right",
                    "foodEaten": 0, "width": 12, "height": 12}


class FakeRouter:
    """Answers each yes/no question from a scoring function of the question text. Tests only."""

    def __init__(self, score):
        self.score = score
        self.calls = 0
        self.loaded_revisions = {}

    def load(self, name):
        return type("A", (), {"device": "cpu"})()

    def predict(self, state, questions, model=None):
        self.calls += 1
        return {"answers": {qid: {"type": "noul", "noul": self.score(q["instructions"])} for qid, q in questions.items()}}


def greedy_score(text):
    if "game over" in text:
        return 0.05
    if "eats the food" in text:
        return 0.9
    if "closer to the food" in text:
        return 0.7
    if "keeps the largest tile" in text:
        return 0.6
    return 0.4


def test_snake_sim_matches_the_real_start_state():
    st = SnakeSim(seed=1).state()
    for k, v in REAL_SNAKE_START.items():
        assert st[k] == v
    assert st["grid"][6][6] == 3 and st["grid"][6][5] == 1 and st["grid"][6][4] == 1


def test_snake_rules():
    s = SnakeSim(seed=1)
    assert s.act("left") == {"error": "Cannot reverse direction"}
    assert s.steps == 0
    for _ in range(5):
        assert s.act("right") is None  # head x goes 7..11, still on the board
    assert not s.done
    assert s.act("right") is None
    assert s.done and not s.won  # x = 12 is outside the 12-wide board


def test_snake_facts_at_start():
    f = snake_facts(SnakeSim(seed=1).state())
    assert not f["left"].legal and f["left"].kind == "reverse"
    assert all(f[d].legal and not f[d].fatal for d in ("up", "down", "right"))


def test_snake_facts_wall_body_and_pocket():
    st = {"width": 5, "height": 5, "direction": "up", "foodEaten": 0, "food": {"x": 4, "y": 4},
          "snake": [{"x": 0, "y": 1}, {"x": 0, "y": 2}, {"x": 1, "y": 2}, {"x": 1, "y": 1}, {"x": 1, "y": 0},
                    {"x": 2, "y": 0}]}
    f = snake_facts(st)
    assert f["left"].kind == "wall" and f["left"].fatal
    assert f["right"].kind == "body" and f["right"].fatal
    assert f["up"].kind == "move" and "closed pocket" in f["up"].text  # (0,0) is a dead end


def test_2048_slide_and_noop():
    g = [[2, 2, 4, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 2]]
    new, pts, merges = slide_board(g, "left")
    assert new[0] == [4, 4, 0, 0] and pts == 4 and merges == 1
    f = g2048_facts({"grid": [[2, 4, 8, 16]] + [[0] * 4] * 3, "score": 0, "best": 16})
    assert not f["up"].legal and not f["left"].legal and not f["right"].legal and f["down"].legal
    sim = Sim2048(seed=3)
    noop = next((d for d in ("up", "down", "left", "right") if slide_board(sim.grid, d)[0] == sim.grid), None)
    if noop:
        assert "error" in sim.act(noop)


def test_spec_log_hash_chain_and_tamper(tmp_path):
    p = tmp_path / "s.jsonl"
    log = SpecLog(p, "sid-1", "snake")
    dec = {"questions": ["q"], "probabilities": {"up": 0.4, "down": 0.1, "left": 0.0, "right": 0.5},
           "chosen": "right", "confidence": 0.5, "source": "laya"}
    log.write(step=1, state_before={"a": 1}, action="right", state_after={"a": 2}, result="applied",
              decision=dec, timing={"decide_ms": 10, "api_ms": 20, "turn_ms": 30})
    log.close()
    line = json.loads(p.read_text().splitlines()[0])
    assert line["prev_hash"] == "GENESIS-sid-1"
    body = {k: v for k, v in line.items() if k != "hash"}
    assert line["hash"] == line_hash("GENESIS-sid-1", body)
    assert canonical_json({"b": 1, "a": [1, 2]}) == '{"a":[1,2],"b":1}'
    assert verify_log(p)["ok"]
    p.write_text(p.read_text().replace('"action":"right"', '"action":"up"', 1))
    assert not verify_log(p)["ok"]


def test_spec_log_rejects_bad_decision_blocks(tmp_path):
    log = SpecLog(tmp_path / "s.jsonl", "s", "snake")
    bad = {"questions": ["q"], "probabilities": {"up": 1.0}, "chosen": "up", "confidence": 1.0, "source": "laya"}
    with pytest.raises(ValueError):
        log.write(step=1, state_before={}, action="up", state_after={}, result="applied", decision=bad,
                  timing={"decide_ms": 1, "api_ms": 1, "turn_ms": 1})


def run(tmp_path, game, score_fn, seed=1, **kw):
    d = LayaMoveDecider(game, router=FakeRouter(score_fn), **kw)
    d.load()
    return play_session(FakeArena(seed=seed), d, game, tmp_path, "TEST", quiet=True)


def test_full_snake_session_verifies(tmp_path):
    report = run(tmp_path, "snake", greedy_score)
    assert report["ok"], report["problems"]
    assert report["applied"] > 0
    files = list((tmp_path / "snake").glob("*"))
    assert any(f.name.endswith(".final.json") for f in files)
    assert any(f.name.endswith(".events.jsonl") for f in files)


def test_fatal_laya_pick_becomes_a_logged_fallback(tmp_path):
    # This fake prefers the wall, so the safety fallback must step in (within the 10% budget)
    report = run(tmp_path, "snake", lambda t: 0.9 if "hits the wall" in t else 0.3)
    lines = [json.loads(l) for l in next((tmp_path / "snake").glob("*[!s].jsonl")).read_text().splitlines()]
    sources = [l["decision"]["source"] for l in lines]
    assert "fallback" in sources
    assert report["fallback_share"] <= 0.10 or not report["ok"]


def test_offer_all_never_sends_an_illegal_move(tmp_path):
    report = run(tmp_path, "snake", lambda t: 0.99 if "not allowed" in t else greedy_score(t), offer="all")
    log = next((tmp_path / "snake").glob("*[!s].jsonl"))
    lines = [json.loads(l) for l in log.read_text().splitlines()]
    assert all(l["result"] == "applied" for l in lines)
    assert report["ok"], report["problems"]


def test_full_2048_session_verifies(tmp_path):
    report = run(tmp_path, "2048", greedy_score, seed=2)
    assert report["ok"], report["problems"]
