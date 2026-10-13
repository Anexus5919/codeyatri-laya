import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from laya_agent.viewer.terminal import render
from laya_agent.viewer.web import make_handler


def test_terminal_render_marks_the_chosen_move():
    text = render({"seq": 4, "env": "LOCAL_FIXTURE", "type": "decision", "turn_id": 2, "design_id": "facts_v1",
                   "model": "english", "latency_ms": 31.2, "valid": True, "chosen_action_id": "left",
                   "probabilities": {"up": 0.2, "left": 0.8}, "answer_confidence": 0.8, "confidence": 0.3})
    lines = text.splitlines()
    assert "turn=2" in lines[0]
    assert lines[1].strip().startswith("> left")  # highest probability first, chosen marked


def test_web_viewer_serves_the_same_events_as_the_log(tmp_path):
    log = tmp_path / "run.jsonl"
    events = [{"seq": i, "type": "decision", "run_id": "r", "env": "LOCAL_FIXTURE"} for i in (1, 2, 3)]
    log.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(str(tmp_path)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_address[1]
        body = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/events?after=1").read())
        assert [e["seq"] for e in body["events"]] == [2, 3]
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/").read().decode()
        assert "Laya Decision Viewer" in page
    finally:
        server.shutdown()
