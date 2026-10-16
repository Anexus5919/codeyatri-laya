"""Client for the topgameai arena API. Endpoints read from the arena's own page code (2026-10-16):

    POST /api/arena/sessions                 {"game", "agent_name"}  -> session response
    POST /api/arena/sessions/{id}/action     {"action": "up"}        -> session response or {"error"}
    GET  /api/arena/sessions/{id}                                    -> session response
"""

from __future__ import annotations

import time

import requests

from ..contracts import SubmissionAmbiguous

BASE_URL = "https://topgameai.com/api/arena"


class ArenaClient:
    env = "HOSTED"

    def __init__(self, base_url: str = BASE_URL, timeout_s: float = 15.0, get_retries: int = 4) -> None:
        self.base = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.get_retries = get_retries
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
        """Sends one move once. A timeout after sending is ambiguous and must be reconciled with get()."""
        try:
            r = self.http.post(f"{self.base}/sessions/{session_id}/action", json={"action": action}, timeout=self.timeout_s)
        except requests.ConnectTimeout as exc:
            return 0, {"error": f"could not connect: {exc}"}
        except (requests.ReadTimeout, requests.ConnectionError) as exc:
            raise SubmissionAmbiguous(str(exc)) from exc
        return r.status_code, self._body(r)

    def get(self, session_id: str) -> tuple[int, dict]:
        last: Exception | None = None
        for attempt in range(self.get_retries + 1):
            try:
                r = self.http.get(f"{self.base}/sessions/{session_id}", timeout=self.timeout_s)
                if r.status_code < 500:
                    return r.status_code, self._body(r)
                last = RuntimeError(f"HTTP {r.status_code}")
            except (requests.ConnectionError, requests.Timeout) as exc:
                last = exc
            time.sleep(min(0.5 * 2**attempt, 4))
        raise RuntimeError(f"GET session failed: {last}")
