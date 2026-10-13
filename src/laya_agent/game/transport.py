"""HTTP transport for hosted game APIs: timeouts, bounded GET retries, no blind POST retries."""

from __future__ import annotations

import time
from typing import Any

import requests

from ..contracts import SubmissionAmbiguous


class TransportError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class HttpTransport:
    """Thin wrapper over requests. Game-specific clients build on top of it."""

    RETRYABLE_STATUS = {429, 500, 502, 503, 504}

    def __init__(
        self,
        base_url: str,
        token: str = "",
        auth_header: str = "Authorization",
        auth_scheme: str = "Bearer",
        timeout_s: float = 10.0,
        get_retries: int = 3,
        session: requests.Session | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is empty: set BOT_GAME_BASE_URL once the organisers publish it")
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.get_retries = max(0, get_retries)
        self.session = session or requests.Session()
        if token:
            self.session.headers[auth_header] = f"{auth_scheme} {token}".strip() if auth_scheme else token

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    @staticmethod
    def _body(resp: requests.Response) -> Any:
        try:
            return resp.json()
        except ValueError:
            return resp.text

    def get(self, path: str, params: dict | None = None) -> Any:
        """GET is treated as idempotent, so transient failures are retried with backoff."""
        last: Exception | None = None
        for attempt in range(self.get_retries + 1):
            retry_after: str | None = None
            try:
                resp = self.session.get(self._url(path), params=params, timeout=self.timeout_s)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last = exc
            else:
                if resp.status_code in self.RETRYABLE_STATUS:
                    last = TransportError(f"GET {path} -> {resp.status_code}", resp.status_code, self._body(resp))
                    retry_after = resp.headers.get("Retry-After")
                elif resp.status_code >= 400:
                    raise TransportError(f"GET {path} -> {resp.status_code}", resp.status_code, self._body(resp))
                else:
                    return self._body(resp)
            if attempt < self.get_retries:
                try:
                    delay = min(float(retry_after), 30.0) if retry_after else min(0.25 * 2**attempt, 4.0)
                except ValueError:
                    delay = min(0.25 * 2**attempt, 4.0)
                time.sleep(delay)
        raise TransportError(f"GET {path} failed after {self.get_retries + 1} attempts: {last}")

    def post(self, path: str, json_body: Any = None, headers: dict | None = None) -> tuple[int, Any]:
        """POST is side-effecting and is never retried here.

        A connection error before the request is sent is safe to report as a plain failure.
        A timeout or reset after sending is ambiguous: the move may have been applied, so the
        caller must reconcile against fresh server state instead of resending.
        """
        try:
            resp = self.session.post(self._url(path), json=json_body, headers=headers, timeout=self.timeout_s)
        except requests.ConnectTimeout as exc:
            raise TransportError(f"POST {path} could not connect: {exc}") from exc
        except (requests.ReadTimeout, requests.ConnectionError) as exc:
            raise SubmissionAmbiguous(f"POST {path} outcome unknown: {exc}") from exc
        return resp.status_code, self._body(resp)
