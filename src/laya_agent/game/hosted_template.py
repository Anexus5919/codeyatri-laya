"""Template for the real hosted games. Every UNRESOLVED item is filled from the official API docs.

Nothing here guesses an endpoint, a field name or an auth scheme. Copy this file per game
(for example game/stage1.py) on hackathon day and replace each UNRESOLVED marker.
"""

from __future__ import annotations

from typing import Any

from ..contracts import Candidate, Decision, Observation, StateValidationError, SubmitResult, SubmissionAmbiguous
from ..telemetry.events import ENV_HOSTED
from .base import GameAdapter, GameClient
from .transport import HttpTransport, TransportError

UNRESOLVED = "UNRESOLVED: fill from the official game API documentation"


class HostedGameClient(GameClient):
    env = ENV_HOSTED

    # UNRESOLVED: real paths are published on hackathon day.
    START_PATH: str | None = None
    STATE_PATH: str | None = None
    MOVE_PATH: str | None = None

    def __init__(self, transport: HttpTransport) -> None:
        self.t = transport
        self.session_id: str | None = None

    def _require(self, path: str | None) -> str:
        if not path:
            raise NotImplementedError(UNRESOLVED)
        return path

    def start(self) -> Any:
        body = self.t.post(self._require(self.START_PATH))[1]
        # UNRESOLVED: read the session id field from the documented start response.
        return body

    def get_state(self) -> Any:
        return self.t.get(self._require(self.STATE_PATH))

    def submit(self, candidate: Candidate, decision: Decision, observation: Observation) -> SubmitResult:
        # UNRESOLVED: request body shape, turn/sequence field and idempotency header, if any.
        # If the API supports an idempotency key, send decision.decision_id as that key.
        try:
            status, body = self.t.post(self._require(self.MOVE_PATH), json_body=candidate.payload)
        except SubmissionAmbiguous as exc:
            return SubmitResult("ambiguous", detail=str(exc))
        except TransportError as exc:
            return SubmitResult("error", response=exc.body, detail=str(exc))
        if 200 <= status < 300:
            return SubmitResult("accepted", response=body)
        return SubmitResult("rejected", response=body, detail=f"HTTP {status}")

    def reconcile(self, observation: Observation, decision: Decision) -> str:
        # UNRESOLVED: compare the documented turn/sequence counter before and after.
        return "unknown"

    def session_info(self) -> dict[str, Any]:
        return {"session_id": self.session_id}


class HostedGameAdapter(GameAdapter):
    game_id = "UNRESOLVED"

    def observe(self, raw: Any) -> Observation:
        if not isinstance(raw, dict):
            raise StateValidationError(f"expected a JSON object, got {type(raw).__name__}")
        raise NotImplementedError(UNRESOLVED)
