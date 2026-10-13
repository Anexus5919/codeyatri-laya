"""Test doubles. FakeRouter mirrors the laya 0.4.6 response shape verified in docs/research.md.

It exists only under tests/ so no code path in src/ can choose a move without real Laya.
"""

from __future__ import annotations

from typing import Any, Callable

import pytest

from laya_agent.telemetry.events import ENV_LOCAL_FIXTURE
from laya_agent.telemetry.jsonl import EventLog


class FakeRouter:
    def __init__(self, pick: Callable[[list[str]], str] | None = None, response: Any = None, raises: Exception | None = None):
        self.pick = pick or (lambda labels: labels[0])
        self.response = response
        self.raises = raises
        self.calls: list[tuple] = []
        self.loaded_revisions = {"english": "fake-revision"}

    def load(self, name: str):
        return object()

    def register(self, name, source, description=None):
        return name

    def predict(self, state, questions, **kwargs):
        self.calls.append((state, questions, kwargs))
        if self.raises:
            raise self.raises
        if self.response is not None:
            return self.response
        answers = {}
        noul_qids = [qid for qid, q in questions.items() if q["type"] == "noul"]
        noul_pick = self.pick(noul_qids) if noul_qids else None
        for qid, q in questions.items():
            if q["type"] == "noul":
                p = 0.8 if qid == noul_pick else 0.3
                answers[qid] = {"type": "noul", "noul": p, "confidence": max(p, 1 - p), "answer_confidence": max(p, 1 - p), "action": {"act_probability": 1.0}}
                continue
            crit = q["criteria"]
            labels = list(crit if isinstance(crit, list) else crit.keys())
            chosen = self.pick(labels)
            rest = (1.0 - 0.7) / max(1, len(labels) - 1) if len(labels) > 1 else 0.0
            probs = {l: (0.7 if l == chosen else rest) for l in labels} if len(labels) > 1 else {chosen: 1.0}
            answers[qid] = {
                "type": "choice",
                "choice": chosen,
                "probabilities": probs,
                "confidence": 0.5,
                "answer_confidence": max(probs.values()),
                "action": {"act_probability": 1.0},
            }
        return {
            "model": "laya-rl-agent",
            "answers": answers,
            "usage": {"input_tokens": 100, "output_tokens": 0, "state_tokens": 40, "state_tokens_dropped": 0, "truncated": False, "truncated_questions": []},
            "routing": {"model": kwargs.get("model"), "reason": "explicit model"},
        }


@pytest.fixture
def make_log(tmp_path):
    logs = []

    def _make(sinks=()):
        log = EventLog(tmp_path / "run.jsonl", "test-run", ENV_LOCAL_FIXTURE, sinks=sinks, secrets=("s3cr3t",))
        logs.append(log)
        return log

    yield _make
    for log in logs:
        log.close()
