"""Interfaces every game integration implements. Game rules live only behind these."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..contracts import Candidate, Decision, Observation, SubmitResult


class GameClient(ABC):
    """Talks to one game's agent API. Knows endpoints and auth, not strategy."""

    env: str  # ENV_HOSTED or ENV_LOCAL_FIXTURE

    @abstractmethod
    def start(self) -> Any:
        """Start or attach to a session. Returns the raw server response."""

    @abstractmethod
    def get_state(self) -> Any:
        """Fetch the current raw state."""

    @abstractmethod
    def submit(self, candidate: Candidate, decision: Decision, observation: Observation) -> SubmitResult:
        """Send one move. Must not retry on its own after the request may have been sent."""

    def reconcile(self, observation: Observation, decision: Decision) -> str:
        """After an ambiguous submit, decide from fresh state: 'applied', 'not_applied' or 'unknown'."""
        return "unknown"

    def session_info(self) -> dict[str, Any]:
        """Session id and verification details for the log, when the API exposes them."""
        return {}


class GameAdapter(ABC):
    """Turns a raw game state into a validated Observation with factual candidates."""

    game_id: str

    @abstractmethod
    def observe(self, raw: Any) -> Observation:
        """Validate `raw` and build an Observation. Raise StateValidationError on bad input."""
