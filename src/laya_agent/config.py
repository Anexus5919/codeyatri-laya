"""Central configuration, read from environment variables and an optional .env file."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """Load KEY=VALUE lines into os.environ without overriding values already set."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def _str(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _opt_int(name: str) -> int | None:
    raw = _str(name)
    return int(raw) if raw else None


def _int(name: str, default: int) -> int:
    raw = _str(name)
    return int(raw) if raw else default


def _float(name: str, default: float) -> float:
    raw = _str(name)
    return float(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    laya_model: str = "english"
    device: str | None = None
    head_max_len: int | None = None
    max_len: int | None = None
    question_design: str = "facts_v1"

    game_base_url: str = ""
    game_token: str = field(default="", repr=False)
    game_auth_header: str = "Authorization"
    game_auth_scheme: str = "Bearer"
    http_timeout_s: float = 10.0
    http_get_retries: int = 3

    max_steps: int = 1000
    max_state_refetch: int = 3
    max_decision_retries: int = 1

    log_dir: str = "logs"
    log_max_field_chars: int = 4000
    viewer_port: int = 8765

    @classmethod
    def from_env(cls, dotenv: str | Path | None = ".env") -> "Settings":
        if dotenv:
            load_dotenv(dotenv)
        return cls(
            laya_model=_str("BOT_LAYA_MODEL", "english"),
            device=_str("BOT_DEVICE") or None,
            head_max_len=_opt_int("BOT_HEAD_MAX_LEN"),
            max_len=_opt_int("BOT_MAX_LEN"),
            question_design=_str("BOT_QUESTION_DESIGN", "facts_v1"),
            game_base_url=_str("BOT_GAME_BASE_URL"),
            game_token=_str("BOT_GAME_TOKEN"),
            game_auth_header=_str("BOT_GAME_AUTH_HEADER", "Authorization"),
            game_auth_scheme=_str("BOT_GAME_AUTH_SCHEME", "Bearer"),
            http_timeout_s=_float("BOT_HTTP_TIMEOUT_S", 10.0),
            http_get_retries=_int("BOT_HTTP_GET_RETRIES", 3),
            max_steps=_int("BOT_MAX_STEPS", 1000),
            max_state_refetch=_int("BOT_MAX_STATE_REFETCH", 3),
            max_decision_retries=_int("BOT_MAX_DECISION_RETRIES", 1),
            log_dir=_str("BOT_LOG_DIR", "logs"),
            log_max_field_chars=_int("BOT_LOG_MAX_FIELD_CHARS", 4000),
            viewer_port=_int("BOT_VIEWER_PORT", 8765),
        )

    def public_dict(self) -> dict:
        """Settings safe to log: secrets are replaced by a presence flag."""
        data = asdict(self)
        data["game_token"] = "<set>" if self.game_token else "<unset>"
        return data
