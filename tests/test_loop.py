from conftest import FakeRouter
from laya_agent.audit import audit_events
from laya_agent.contracts import SubmissionAmbiguous, SubmitResult
from laya_agent.decision.laya_client import LayaDecider
from laya_agent.game.local_fixture import CoinGridAdapter, LocalFixtureClient
from laya_agent.loop import GameLoop
from laya_agent.telemetry.jsonl import read_events


def toward_coin(labels):
    return labels[0]


def run(make_log, tmp_path, client=None, router=None, **kw):
    log = make_log()
    client = client or LocalFixtureClient(seed=1, max_steps=8)
    decider = LayaDecider(router=router or FakeRouter(), design_id="facts_v1")
    summary = GameLoop(client, CoinGridAdapter(), decider, log, **kw).run()
    log.close()
    return summary, read_events(tmp_path / "run.jsonl")


def test_full_fixture_game_every_move_traces_to_a_logged_laya_decision(make_log, tmp_path):
    summary, events = run(make_log, tmp_path)
    assert summary.status == "finished"
    assert summary.moves_accepted == 8 == summary.decisions
    types = [e["type"] for e in events]
    assert types[-2:] == ["game_over", "run_end"]
    # Each submission comes right after the decision that produced it.
    for i, e in enumerate(events):
        if e["type"] == "submission":
            assert events[i - 1]["type"] == "decision"
            assert events[i - 1]["decision_id"] == e["decision_id"]
    assert audit_events(events)["ok"]
    assert all(e["env"] == "LOCAL_FIXTURE" for e in events)


def test_laya_failure_pauses_without_submitting(make_log, tmp_path):
    summary, events = run(make_log, tmp_path, router=FakeRouter(raises=RuntimeError("boom")), max_decision_retries=1)
    assert summary.status == "paused" and summary.reason == "no_valid_laya_decision"
    assert not any(e["type"] == "submission" for e in events)
    assert sum(e["type"] == "decision_rejected" for e in events) == 2


def test_invalid_answer_pauses_without_submitting(make_log, tmp_path):
    summary, events = run(make_log, tmp_path, router=FakeRouter(pick=lambda labels: "teleport"), max_decision_retries=0)
    assert summary.status == "paused"
    assert not any(e["type"] == "submission" for e in events)
    decision = next(e for e in events if e["type"] == "decision")
    assert decision["valid"] is False and decision["laya_response"]


class FlakyStateClient(LocalFixtureClient):
    def __init__(self, bad_reads, **kw):
        super().__init__(**kw)
        self.bad_reads = bad_reads

    def start(self):
        super().start()
        return {"garbage": True}

    def get_state(self):
        if self.bad_reads > 0:
            self.bad_reads -= 1
            return {"garbage": True}
        return super().get_state()


def test_malformed_state_is_refetched_not_repaired(make_log, tmp_path):
    summary, events = run(make_log, tmp_path, client=FlakyStateClient(bad_reads=1, seed=1, max_steps=3), max_state_refetch=3)
    assert summary.status == "finished"
    assert sum(e["type"] == "state_invalid" for e in events) == 2


def test_persistently_malformed_state_pauses(make_log, tmp_path):
    summary, events = run(make_log, tmp_path, client=FlakyStateClient(bad_reads=99, seed=1), max_state_refetch=2)
    assert summary.status == "paused" and summary.reason == "state_invalid_after_refetch"
    assert not any(e["type"] in ("decision", "submission") for e in events)


class AmbiguousClient(LocalFixtureClient):
    """Applies the move on the server but loses the response once."""

    def __init__(self, applied: bool, verdict=None, **kw):
        super().__init__(**kw)
        self.applied = applied
        self.verdict = verdict
        self.fired = False
        self.submits = 0

    def submit(self, candidate, decision, observation):
        self.submits += 1
        if not self.fired:
            self.fired = True
            if self.applied:
                super().submit(candidate, decision, observation)
            raise SubmissionAmbiguous("read timeout")
        return super().submit(candidate, decision, observation)

    def reconcile(self, observation, decision):
        return self.verdict or super().reconcile(observation, decision)


def test_ambiguous_submission_that_was_applied_is_not_resent(make_log, tmp_path):
    client = AmbiguousClient(applied=True, seed=1, max_steps=3)
    summary, events = run(make_log, tmp_path, client=client)
    assert summary.status == "finished"
    assert client.submits == 3 and client.game.turn == 3
    rec = next(e for e in events if e["type"] == "reconcile")
    assert rec["verdict"] == "applied"


def test_ambiguous_submission_that_was_not_applied_gets_a_fresh_laya_decision(make_log, tmp_path):
    client = AmbiguousClient(applied=False, seed=1, max_steps=2)
    summary, events = run(make_log, tmp_path, client=client)
    assert summary.status == "finished"
    assert summary.decisions == 3  # the lost move is decided again by a new Laya call
    assert audit_events(events)["ok"]


def test_unresolvable_ambiguity_pauses(make_log, tmp_path):
    client = AmbiguousClient(applied=True, verdict="unknown", seed=1)
    summary, _ = run(make_log, tmp_path, client=client)
    assert summary.status == "paused" and summary.reason == "ambiguous_submission_unresolved"
    assert client.submits == 1


class RejectingClient(LocalFixtureClient):
    def submit(self, candidate, decision, observation):
        return SubmitResult("rejected", response={"error": "stale turn"}, detail="HTTP 409")


def test_rejected_move_pauses(make_log, tmp_path):
    summary, events = run(make_log, tmp_path, client=RejectingClient(seed=1))
    assert summary.status == "paused" and summary.reason == "move_rejected"
    assert summary.moves_rejected == 1


def test_fixture_rejects_stale_turns():
    client = LocalFixtureClient(seed=1)
    state = client.start()
    action = state["legal_actions"][0]
    assert client.game.step(action, state["turn"])["ok"]
    assert not client.game.step(client.game.legal()[0], state["turn"])["ok"]


def test_max_steps_stops_the_loop(make_log, tmp_path):
    summary, _ = run(make_log, tmp_path, client=LocalFixtureClient(seed=1, max_steps=50), max_steps=5)
    assert summary.status == "max_steps" and summary.moves_accepted == 5
