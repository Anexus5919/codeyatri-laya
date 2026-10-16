"""ArenaClient against a local fake HTTP arena: lost responses must never cause a duplicate move."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from laya_agent.arena.client import ArenaClient
from laya_agent.arena.decider import LayaMoveDecider
from laya_agent.arena.runner import play_session
from laya_agent.arena.sims import FakeArena


class FakeRouter:
    loaded_revisions = {}

    def load(self, name):
        return type("A", (), {"device": "cpu"})()

    def predict(self, state, questions, model=None):
        def score(t):
            return 0.05 if "game over" in t else 0.9 if "eats the food" in t else 0.7 if "closer" in t else 0.4
        return {"answers": {q: {"type": "noul", "noul": score(d["instructions"])} for q, d in questions.items()}}


def make_server(arena, hang_on_steps):
    """Serves the arena's JSON; on the listed step numbers it applies the move but never answers."""

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or b"{}"))
            parts = self.path.strip("/").split("/")
            if parts == ["api", "arena", "sessions"]:
                return self._json(*arena.create(body["game"], body["agent_name"]))
            sid = parts[3]
            code, resp = arena.act(sid, body["action"])
            if code == 200 and resp["steps"] in hang_on_steps:
                hang_on_steps.discard(resp["steps"])
                time.sleep(1.5)  # longer than the client timeout: the move landed, the answer is lost
                return
            return self._json(code, resp)

        def do_GET(self):
            sid = self.path.strip("/").split("/")[3]
            return self._json(*arena.get(sid))

    return ThreadingHTTPServer(("127.0.0.1", 0), H)


@pytest.fixture
def served(tmp_path):
    arena = FakeArena(seed=5)
    hang = {3, 7}
    server = make_server(arena, hang)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield arena, f"http://127.0.0.1:{server.server_address[1]}/api/arena", hang
    server.shutdown()


def test_lost_response_is_reconciled_not_resent(served, tmp_path):
    arena, base, hang = served
    client = ArenaClient(base_url=base, timeout_s=0.5)
    dec = LayaMoveDecider("snake", router=FakeRouter())
    dec.load()
    report = play_session(client, dec, "snake", tmp_path, "TEST", quiet=True)
    assert report["ok"], report["problems"]
    assert not hang, "both hangs should have been triggered"
    sid = report["session_id"]
    _, sim = arena.sessions[sid]
    log_lines = [json.loads(l) for l in (tmp_path / "snake" / f"{sid}.jsonl").read_text().splitlines()]
    applied = [l for l in log_lines if l["result"] == "applied"]
    assert len(applied) == sim.steps, "one log line per move the server applied, no duplicates"
    assert [l["step"] for l in applied] == list(range(1, sim.steps + 1))
    events = [json.loads(l) for l in (tmp_path / "snake" / f"{sid}.events.jsonl").read_text().splitlines()]
    verdicts = [e["verdict"] for e in events if e["type"] == "reconcile"]
    assert verdicts.count("applied") == 2
