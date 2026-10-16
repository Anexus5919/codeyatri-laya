"""Client for the topgameai arena API. Endpoints read from the arena's own page code (2026-10-16):

    POST /api/arena/sessions                 {"game", "agent_name"}  -> session response
    POST /api/arena/sessions/{id}/action     {"action": "up"}        -> session response or {"error"}
    GET  /api/arena/sessions/{id}                                    -> session response

A move is sent at most once. Failures are sorted into three cases:
  - NotSent: the request never left (no connection, rate limited); safe to decide and send again.
  - SubmissionAmbiguous: the request may have reached the server (lost response, server error);
    the runner reads the session back before doing anything else.
  - a normal response with {"error"}: the game rejected the move.
"""

from __future__ import annotations

import time
from typing import Callable

import requests

from ..contracts import SubmissionAmbiguous

BASE_URL = "https://topgameai.com/api/arena"


class NotSent(RuntimeError):
    """The move certainly did not reach the server; it is safe to send it again."""


class ArenaUnreachable(RuntimeError):
    """The arena could not be read for longer than the patience window."""


class ArenaClient:
    env = "HOSTED"

    def __init__(self, base_url: str = BASE_URL, timeout_s: float = 15.0, patience_s: float = 900.0,
                 on_wait: Callable[[str], None] | None = None) -> None:
        self.base = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.patience_s = patience_s  # how long get() keeps trying through a network drop
        self.on_wait = on_wait or (lambda msg: None)
        self.http = requests.Session()
        self.http.headers["User-Agent"] = "CodeYatri-laya-agent/1.0"

    @staticmethod
    def _body(resp: requests.Response) -> dict:
        try:
            return resp.json()
        except ValueError:
            return {"error": f"non-JSON response (HTTP {resp.status_code})", "text": resp.text[:500]}

    def create(self, game: str, agent_name: str) -> tuple[int, dict]:
        # Never retried: a lost response could still have created a session on the server
        r = self.http.post(f"{self.base}/sessions", json={"game": game, "agent_name": agent_name}, timeout=self.timeout_s)
        return r.status_code, self._body(r)

    def act(self, session_id: str, action: str) -> tuple[int, dict]:
        """Sends one move once. Raises NotSent or SubmissionAmbiguous instead of guessing."""
        try:
            r = self.http.post(f"{self.base}/sessions/{session_id}/action", json={"action": action}, timeout=self.timeout_s)
        except requests.ConnectTimeout as exc:
            raise NotSent(f"could not connect: {exc}") from exc
        except (requests.ReadTimeout, requests.ConnectionError) as exc:
            raise SubmissionAmbiguous(f"no response: {exc}") from exc
        if r.status_code == 429:
            raise NotSent("rate limited (HTTP 429)")
        if r.status_code >= 500:
            raise SubmissionAmbiguous(f"server error HTTP {r.status_code}")
        return r.status_code, self._body(r)

    def get(self, session_id: str) -> tuple[int, dict]:
        """Reads the session, waiting through network drops for up to `patience_s` seconds."""
        deadline = time.monotonic() + self.patience_s
        delay, last = 1.0, None
        while True:
            try:
                r = self.http.get(f"{self.base}/sessions/{session_id}", timeout=self.timeout_s)
                if r.status_code < 500:
                    return r.status_code, self._body(r)
                last = f"HTTP {r.status_code}"
            except (requests.ConnectionError, requests.Timeout) as exc:
                last = f"{type(exc).__name__}"
            if time.monotonic() + delay > deadline:
                raise ArenaUnreachable(f"arena unreachable for {self.patience_s:.0f} s (last: {last})")
            self.on_wait(f"arena not reachable ({last}), retrying in {delay:.0f} s")
            time.sleep(delay)
            delay = min(delay * 2, 15.0)
