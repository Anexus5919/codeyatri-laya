"""Decision-log event schema, redaction and bounding of large values."""

from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA_VERSION = 1

# Event types written to the JSONL log, in the order they normally appear.
EVENT_TYPES = (
    "run_start",
    "model_loaded",
    "state_invalid",
    "decision",
    "decision_rejected",
    "submission",
    "reconcile",
    "game_over",
    "pause",
    "run_end",
)

# Environment labels. Only HOSTED runs can ever be reported as competition results.
ENV_LOCAL_FIXTURE = "LOCAL_FIXTURE"
ENV_HOSTED = "HOSTED"

SECRET_EXACT = {"token", "password", "passwd", "secret", "authorization", "cookie", "set_cookie", "apikey", "api_key"}
SECRET_SUFFIXES = ("_token", "_password", "_secret", "_api_key", "_apikey")


def is_secret_key(key: str) -> bool:
    # Exact names and suffixes only, so usage fields like "input_tokens" stay visible.
    k = key.lower().replace("-", "_")
    return k in SECRET_EXACT or k.endswith(SECRET_SUFFIXES)


def redact(value: Any, secrets: tuple[str, ...] = ()) -> Any:
    """Recursively drop secret-looking keys and scrub known secret strings."""
    if isinstance(value, dict):
        return {k: ("<redacted>" if is_secret_key(str(k)) else redact(v, secrets)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v, secrets) for v in value]
    if isinstance(value, str):
        for s in secrets:
            if s and s in value:
                value = value.replace(s, "<redacted>")
        return value
    return value


def bound(value: Any, max_chars: int) -> Any:
    """Keep values small enough to log; oversized ones become a preview plus a sha256."""
    try:
        text = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = repr(value)
    if len(text) <= max_chars:
        return value
    return {
        "_truncated": True,
        "_chars": len(text),
        "_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "_preview": text[:max_chars],
    }
