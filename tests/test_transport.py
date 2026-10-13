import pytest
import requests

from laya_agent.contracts import SubmissionAmbiguous
from laya_agent.game import transport as transport_mod
from laya_agent.game.transport import HttpTransport, TransportError


class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.headers = headers or {}
        self.text = str(self._body)

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, gets=(), posts=()):
        self.gets = list(gets)
        self.posts = list(posts)
        self.headers = {}
        self.get_calls = 0
        self.post_calls = 0

    def _next(self, queue):
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def get(self, url, params=None, timeout=None):
        self.get_calls += 1
        return self._next(self.gets)

    def post(self, url, json=None, headers=None, timeout=None):
        self.post_calls += 1
        return self._next(self.posts)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(transport_mod.time, "sleep", lambda s: None)


def test_empty_base_url_is_refused():
    with pytest.raises(ValueError):
        HttpTransport("")


def test_auth_header_is_set_from_config():
    s = FakeSession()
    HttpTransport("https://x", token="tkn", session=s)
    assert s.headers["Authorization"] == "Bearer tkn"


def test_get_retries_transient_errors_then_succeeds():
    s = FakeSession(gets=[requests.ConnectionError("down"), Resp(503), Resp(200, {"turn": 1})])
    assert HttpTransport("https://x", session=s, get_retries=3).get("/state") == {"turn": 1}
    assert s.get_calls == 3


def test_get_client_errors_are_not_retried():
    s = FakeSession(gets=[Resp(404, {"error": "no"})])
    with pytest.raises(TransportError) as err:
        HttpTransport("https://x", session=s).get("/state")
    assert err.value.status == 404 and s.get_calls == 1


def test_get_gives_up_after_bounded_retries():
    s = FakeSession(gets=[Resp(500)] * 3)
    with pytest.raises(TransportError):
        HttpTransport("https://x", session=s, get_retries=2).get("/state")
    assert s.get_calls == 3


def test_post_timeout_is_ambiguous_and_never_retried():
    s = FakeSession(posts=[requests.ReadTimeout("slow")])
    with pytest.raises(SubmissionAmbiguous):
        HttpTransport("https://x", session=s).post("/move", {"a": 1})
    assert s.post_calls == 1


def test_post_connect_timeout_is_a_plain_failure():
    s = FakeSession(posts=[requests.ConnectTimeout("no route")])
    with pytest.raises(TransportError):
        HttpTransport("https://x", session=s).post("/move", {"a": 1})


def test_post_returns_status_and_body():
    s = FakeSession(posts=[Resp(409, {"error": "stale"})])
    assert HttpTransport("https://x", session=s).post("/move", {}) == (409, {"error": "stale"})
