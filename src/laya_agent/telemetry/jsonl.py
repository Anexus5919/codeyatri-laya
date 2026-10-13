"""Append-only JSONL decision log. Each event is flushed and fsynced before the next step."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .events import SCHEMA_VERSION, bound, is_secret_key, redact

Sink = Callable[[dict], None]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


class EventLog:
    """Writes every event to a JSONL file first, then fans it out to live sinks."""

    def __init__(
        self,
        path: str | Path,
        run_id: str,
        env: str,
        sinks: Iterable[Sink] = (),
        secrets: tuple[str, ...] = (),
        max_field_chars: int = 4000,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.env = env
        self.sinks = list(sinks)
        self.secrets = tuple(s for s in secrets if s)
        self.max_field_chars = max_field_chars
        self._seq = 0
        self._lock = threading.Lock()
        self._fh = open(self.path, "a", encoding="utf-8")

    def emit(self, event_type: str, **fields: Any) -> dict:
        with self._lock:
            self._seq += 1
            record = {
                "schema": SCHEMA_VERSION,
                "seq": self._seq,
                "ts": utc_now(),
                "run_id": self.run_id,
                "env": self.env,
                "type": event_type,
            }
            for key, value in fields.items():
                if is_secret_key(key):
                    record[key] = "<redacted>"
                    continue
                record[key] = bound(redact(value, self.secrets), self.max_field_chars)
            line = json.dumps(record, ensure_ascii=False, default=str)
            self._fh.write(line + "\n")
            self._fh.flush()
            os.fsync(self._fh.fileno())
        for sink in self.sinks:
            try:
                sink(record)
            except Exception:  # a broken viewer must never stop the bot or lose the log
                pass
        return record

    def close(self) -> None:
        with self._lock:
            if not self._fh.closed:
                self._fh.close()

    def __enter__(self) -> "EventLog":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def read_events(path: str | Path) -> list[dict]:
    """Read a log, skipping a torn final line left by a crash mid-write."""
    events = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events
