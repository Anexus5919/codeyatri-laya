"""Simple HTML live viewer. Serves one page that polls the JSONL log; standard library only.

Usage: python -m laya_agent.viewer.web logs/            (newest log in the folder)
       python -m laya_agent.viewer.web logs/<run>.jsonl --port 8765
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..telemetry.jsonl import read_events
from .terminal import latest_log

PAGE = Path(__file__).with_name("index.html")


def make_handler(log_source: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # keep the console for the bot
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/":
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
                return
            if url.path == "/events":
                after = int(parse_qs(url.query).get("after", ["0"])[0] or 0)
                try:
                    path = latest_log(log_source)
                    events = [e for e in read_events(path) if e.get("seq", 0) > after]
                    body = {"log": str(path), "events": events}
                except FileNotFoundError as exc:
                    body = {"log": None, "events": [], "error": str(exc)}
                self._send(200, json.dumps(body, default=str).encode("utf-8"), "application/json")
                return
            self._send(404, b"not found", "text/plain")

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("log", nargs="?", default="logs")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(args.log))
    print(f"viewer on http://{args.host}:{args.port}  (log: {args.log})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
