"""Typed contracts shared by the game adapters, the Laya decider and the loop."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


class StateValidationError(ValueError):
    """The server state is malformed, incomplete or inconsistent. Never repaired silently."""


class DecisionError(RuntimeError):
    """Laya could not produce a usable decision for the current state."""


class SubmissionAmbiguous(RuntimeError):
    """A move request may or may not have reached the server (timeout after send)."""


def canonical_json(value: Any) -> str:
    """Deterministic JSON used for hashing and for rendering structured state."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def state_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Candidate:
    """One legal action. `payload` is exactly what the game API expects for this move."""

    action_id: str
    payload: Any
    description: str
    facts: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Observation:
    """A validated, game-agnostic view of one game state."""

    game_id: str
    session_id: str | None
    turn_id: str | int | None
    terminal: bool
    score: float | None
    objective: str
    state_text: str
    candidates: tuple[Candidate, ...]
    raw: Any
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def state_hash(self) -> str:
        return state_hash(self.raw)

    def candidate(self, action_id: str) -> Candidate | None:
        for c in self.candidates:
            if c.action_id == action_id:
                return c
        return None

    def check_candidates(self) -> None:
        ids = [c.action_id for c in self.candidates]
        if len(ids) != len(set(ids)):
            raise StateValidationError(f"duplicate candidate ids: {ids}")
        if any(not isinstance(i, str) or not i for i in ids):
            raise StateValidationError(f"candidate ids must be non-empty strings: {ids}")


@dataclass
class Decision:
    """The result of exactly one Laya call. Created only by the Laya decider."""

    decision_id: str
    design_id: str
    model: str
    question: dict[str, Any]
    state_text: str
    label_to_action: dict[str, str]
    raw_response: Any
    chosen_label: str | None
    chosen_action_id: str | None
    probabilities: dict[str, float]
    answer_confidence: float | None
    confidence: float | None
    latency_ms: float
    routing: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.chosen_action_id is not None


@dataclass(frozen=True)
class SubmitResult:
    status: str  # accepted | rejected | ambiguous | error
    response: Any = None
    detail: str | None = None
    new_raw_state: Any = None
