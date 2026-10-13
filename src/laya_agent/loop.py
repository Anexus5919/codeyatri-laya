"""The controlled game loop. Every submitted move is preceded by its logged Laya decision."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from .contracts import Decision, DecisionError, Observation, StateValidationError, SubmissionAmbiguous, SubmitResult
from .decision.validation import validate_decision
from .game.base import GameAdapter, GameClient
from .telemetry.jsonl import EventLog


class Decider(Protocol):
    design_id: str
    model_name: str

    def decide(self, observation: Observation) -> Decision: ...


@dataclass
class RunSummary:
    status: str = "running"  # finished | paused | max_steps
    reason: str | None = None
    moves_submitted: int = 0
    moves_accepted: int = 0
    moves_rejected: int = 0
    decisions: int = 0
    decision_failures: int = 0
    final_score: float | None = None
    session: dict[str, Any] = field(default_factory=dict)
    latencies_ms: list[float] = field(default_factory=list)


class GameLoop:
    def __init__(
        self,
        client: GameClient,
        adapter: GameAdapter,
        decider: Decider,
        log: EventLog,
        max_steps: int = 1000,
        max_state_refetch: int = 3,
        max_decision_retries: int = 1,
    ) -> None:
        self.client = client
        self.adapter = adapter
        self.decider = decider
        self.log = log
        self.max_steps = max_steps
        self.max_state_refetch = max_state_refetch
        self.max_decision_retries = max_decision_retries
        self.summary = RunSummary()
        self._logged_decisions: set[str] = set()

    def _pause(self, reason: str, **fields: Any) -> RunSummary:
        self.summary.status = "paused"
        self.summary.reason = reason
        self.log.emit("pause", reason=reason, **fields)
        return self.summary

    def _observe(self, raw: Any) -> Observation | None:
        """Validate state, refetching a bounded number of times. Never invents missing fields."""
        for attempt in range(self.max_state_refetch + 1):
            try:
                return self.adapter.observe(raw)
            except StateValidationError as exc:
                self.log.emit("state_invalid", attempt=attempt, error=str(exc), raw_state=raw)
                if attempt == self.max_state_refetch:
                    return None
                raw = self.client.get_state()
        return None

    def _decide(self, obs: Observation) -> Decision | None:
        """One Laya call per attempt. A failed call is logged and never replaced by another policy."""
        for attempt in range(self.max_decision_retries + 1):
            try:
                decision = self.decider.decide(obs)
            except DecisionError as exc:
                self.summary.decision_failures += 1
                self.log.emit("decision_rejected", attempt=attempt, turn_id=obs.turn_id, error=str(exc))
                continue
            self.summary.decisions += 1
            self.summary.latencies_ms.append(decision.latency_ms)
            problems = validate_decision(decision, obs)
            self.log.emit(
                "decision",
                decision_id=decision.decision_id,
                attempt=attempt,
                game_id=obs.game_id,
                session_id=obs.session_id,
                turn_id=obs.turn_id,
                state_hash=obs.state_hash,
                state_text=decision.state_text,
                raw_state=obs.raw,
                candidates=[
                    {"action_id": c.action_id, "description": c.description, "facts": c.facts} for c in obs.candidates
                ],
                design_id=decision.design_id,
                model=decision.model,
                question=decision.question,
                label_to_action=decision.label_to_action,
                laya_response=decision.raw_response,
                routing=decision.routing,
                usage=decision.usage,
                chosen_label=decision.chosen_label,
                chosen_action_id=decision.chosen_action_id,
                probabilities=decision.probabilities,
                answer_confidence=decision.answer_confidence,
                confidence=decision.confidence,
                latency_ms=round(decision.latency_ms, 2),
                valid=not problems,
                validation_problems=problems,
                error=decision.error,
            )
            self._logged_decisions.add(decision.decision_id)
            if not problems:
                return decision
            self.summary.decision_failures += 1
            self.log.emit("decision_rejected", decision_id=decision.decision_id, attempt=attempt, problems=problems)
        return None

    def run(self, start: bool = True) -> RunSummary:
        raw = self.client.start() if start else self.client.get_state()
        steps = 0
        while True:
            obs = self._observe(raw)
            if obs is None:
                return self._finish(self._pause("state_invalid_after_refetch"))
            if obs.terminal:
                self.summary.final_score = obs.score
                self.summary.status = "finished"
                self.log.emit("game_over", turn_id=obs.turn_id, score=obs.score, session=self.client.session_info())
                return self._finish(self.summary)
            if steps >= self.max_steps:
                self.summary.status = "max_steps"
                return self._finish(self.summary)
            if not obs.candidates:
                return self._finish(self._pause("no_legal_actions", turn_id=obs.turn_id, raw_state=obs.raw))

            decision = self._decide(obs)
            if decision is None:
                return self._finish(self._pause("no_valid_laya_decision", turn_id=obs.turn_id))

            raw = self._submit(obs, decision)
            if raw is None:
                return self._finish(self.summary)
            steps += 1

    def _submit(self, obs: Observation, decision: Decision) -> Any | None:
        # Structural guard: nothing is sent unless its Laya decision is already on disk.
        assert decision.decision_id in self._logged_decisions, "move without a logged Laya decision"
        candidate = obs.candidate(decision.chosen_action_id or "")
        assert candidate is not None
        t0 = time.perf_counter()
        try:
            result = self.client.submit(candidate, decision, obs)
        except SubmissionAmbiguous as exc:
            result = SubmitResult("ambiguous", detail=str(exc))
        self.summary.moves_submitted += 1
        self.log.emit(
            "submission",
            decision_id=decision.decision_id,
            turn_id=obs.turn_id,
            action_id=candidate.action_id,
            payload=candidate.payload,
            status=result.status,
            detail=result.detail,
            response=result.response,
            submit_ms=round((time.perf_counter() - t0) * 1000, 2),
        )
        if result.status == "accepted":
            self.summary.moves_accepted += 1
            return result.new_raw_state if result.new_raw_state is not None else self.client.get_state()
        if result.status == "ambiguous":
            verdict = self.client.reconcile(obs, decision)
            self.log.emit("reconcile", decision_id=decision.decision_id, turn_id=obs.turn_id, verdict=verdict)
            if verdict == "applied":
                self.summary.moves_accepted += 1
                return self.client.get_state()
            if verdict == "not_applied":
                return self.client.get_state()
            self._pause("ambiguous_submission_unresolved", decision_id=decision.decision_id)
            return None
        self.summary.moves_rejected += 1
        self._pause("move_rejected", decision_id=decision.decision_id, status=result.status, detail=result.detail)
        return None

    def _finish(self, summary: RunSummary) -> RunSummary:
        lat = sorted(summary.latencies_ms)
        pct = lambda p: round(lat[min(len(lat) - 1, int(p * len(lat)))], 2) if lat else None  # noqa: E731
        self.log.emit(
            "run_end",
            status=summary.status,
            reason=summary.reason,
            final_score=summary.final_score,
            decisions=summary.decisions,
            decision_failures=summary.decision_failures,
            moves_submitted=summary.moves_submitted,
            moves_accepted=summary.moves_accepted,
            moves_rejected=summary.moves_rejected,
            latency_ms={"p50": pct(0.5), "p95": pct(0.95), "max": lat[-1] if lat else None},
            session=self.client.session_info(),
        )
        summary.session = self.client.session_info()
        return summary
