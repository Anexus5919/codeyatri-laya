import pytest

from conftest import FakeRouter
from laya_agent.contracts import Candidate, DecisionError, Observation, StateValidationError
from laya_agent.decision.laya_client import LayaDecider
from laya_agent.decision.questions import DESIGNS, build_question
from laya_agent.decision.validation import validate_decision


def obs(actions=("up", "left", "right")):
    cands = tuple(Candidate(a, {"action": a}, f"move {a}: fact about {a}") for a in actions)
    return Observation("g", "s", 3, False, 0.0, "Collect coins.", "state text", cands, {"turn": 3})


@pytest.mark.parametrize("design_id", sorted(DESIGNS))
def test_every_design_offers_exactly_the_legal_candidates(design_id):
    built = build_question(design_id, obs())
    assert sorted(built.label_to_action.values()) == ["left", "right", "up"]
    assert set(built.move_qids) <= set(built.questions)
    for q in built.questions.values():
        assert q["type"] in ("choice", "noul") and q["instructions"]


def test_opaque_design_hides_action_names_from_labels():
    built = build_question("opaque_v1", obs())
    assert list(built.questions["move"]["criteria"]) == ["A", "B", "C"]
    assert built.label_to_action == {"A": "up", "B": "left", "C": "right"}


def test_unknown_design_is_rejected():
    with pytest.raises(ValueError):
        build_question("nope", obs())


def test_duplicate_candidate_ids_are_a_validation_error():
    with pytest.raises(StateValidationError):
        obs(("up", "up")).check_candidates()


def test_decider_maps_laya_choice_to_the_action():
    router = FakeRouter(pick=lambda labels: "B")
    d = LayaDecider(design_id="opaque_v1", router=router).decide(obs())
    assert d.chosen_label == "B" and d.chosen_action_id == "left"
    assert set(d.probabilities) == {"up", "left", "right"}
    assert validate_decision(d, obs()) == []
    assert router.calls[0][2]["model"] == "english"


def test_decider_never_substitutes_a_move_when_laya_fails():
    with pytest.raises(DecisionError):
        LayaDecider(router=FakeRouter(raises=RuntimeError("CUDA OOM"))).decide(obs())


@pytest.mark.parametrize("response", [{}, {"answers": {}}, {"answers": {"move": {"type": "choice"}}}, None])
def test_malformed_laya_response_becomes_an_invalid_decision(response):
    router = FakeRouter(response=response if response is not None else ["not", "a", "dict"])
    d = LayaDecider(router=router).decide(obs())
    assert d.chosen_action_id is None
    assert validate_decision(d, obs())


def test_answer_outside_the_offered_labels_is_rejected():
    router = FakeRouter(pick=lambda labels: "teleport")
    d = LayaDecider(router=router).decide(obs())
    problems = validate_decision(d, obs())
    assert any("not one of the offered labels" in p for p in problems)


def test_answer_that_is_no_longer_legal_is_rejected():
    d = LayaDecider(router=FakeRouter(pick=lambda labels: "up")).decide(obs())
    assert validate_decision(d, obs(("left", "right")))


def test_bad_probabilities_and_collapsed_options_are_rejected():
    d = LayaDecider(router=FakeRouter()).decide(obs())
    d.probabilities = {"up": 0.9, "left": 0.9, "right": 0.1}
    assert any("sum" in p for p in validate_decision(d, obs()))
    d = LayaDecider(router=FakeRouter()).decide(obs())
    d.usage = {"options": {"move": {"total": 3, "distinct": 2}}}
    assert any("collapsed" in p for p in validate_decision(d, obs()))


def test_rotation_design_asks_every_cyclic_order_in_one_call_and_averages():
    router = FakeRouter(pick=lambda labels: "left")
    d = LayaDecider(design_id="rot_v1", router=router).decide(obs())
    assert len(router.calls) == 1
    asked = router.calls[0][1]
    assert sorted(q["option_order"] for q in asked.values()) == [[0, 1, 2], [1, 2, 0], [2, 0, 1]]
    assert d.aggregation == "mean_choice" and d.chosen_action_id == "left"
    assert d.aggregate_detail["views"] == 3 and validate_decision(d, obs()) == []


def test_noul_design_picks_the_highest_p_true_and_logs_it():
    router = FakeRouter(pick=lambda qids: qids[2])
    d = LayaDecider(design_id="noul_each_v1", router=router).decide(obs())
    assert len(router.calls) == 1
    assert d.aggregation == "noul_argmax" and d.chosen_action_id == "right"
    assert d.aggregate_detail["p_true"]["right"] == 0.8
    assert validate_decision(d, obs()) == []
