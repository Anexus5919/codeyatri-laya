"""One Laya call per Doom decision: one yes/no question per offered action, answered in one pass.

The action played is the one with Laya's highest P(yes). There is no rule-based override in Doom: every action is
Laya's own pick (source "laya"); an action that does nothing right now (use with no door in reach) is not offered,
the same way a 2048 move that changes nothing is not offered.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from .engine import ACTIONS
from .facts import CRITERIA, ActFact, Scene, facts, questions, state_text


@dataclass
class DoomDecision:
    action: str
    source: str
    probabilities: dict[str, float]  # every action in ACTIONS, sums to 1 over the offered ones
    p_true: dict[str, float]         # Laya's raw P(yes) per offered action
    questions: dict[str, str]
    facts: dict[str, ActFact]
    state_text: str
    laya_ms: float
    extra: dict = field(default_factory=dict)

    @property
    def confidence(self) -> float:
        return self.probabilities[self.action]

    def decision_block(self) -> dict:
        return {
            "questions": [self.questions[a] for a in ACTIONS if a in self.questions],
            "probabilities": dict(self.probabilities),
            "chosen": self.action,
            "confidence": self.probabilities[self.action],
            "source": self.source,
        }


class DoomDecider:
    def __init__(self, router: Any = None, model: str = "english", device: str | None = None):
        if router is None:
            import laya

            router = laya.Router(device=device, max_loaded=1)
        self.router = router
        self.model_source = model
        if model not in ("english", "multilingual", "typed-decisions") and hasattr(router, "register"):
            model = router.register("custom", model, description="configured checkpoint")
        self.model = model
        self.agent = None
        self.info: dict = {}

    def load(self) -> dict:
        try:
            import laya

            version = laya.__version__
        except ImportError:
            version = None
        t0 = time.perf_counter()
        self.agent = self.router.load(self.model)
        info = {"laya_version": version, "model": self.model, "model_source": self.model_source,
                "device": str(getattr(self.agent, "device", "")), "load_s": round(time.perf_counter() - t0, 2)}
        self.warm_up()
        self.info = info
        return info

    def warm_up(self) -> None:
        """One throwaway call so the first real decision does not pay the GPU start-up cost."""
        q = {"q_warm": {"type": "noul", "instructions": "Is this a good action now? This action: moves forward.",
                        "criteria": dict(CRITERIA)}}
        self.router.predict("Doom. Health 100.", q, model=self.model)

    def decide(self, scene: Scene) -> DoomDecision:
        fs = facts(scene)
        qs = questions(fs)
        text = state_text(scene)
        laya_q = {f"q_{a}": {"type": "noul", "instructions": q, "criteria": dict(CRITERIA)} for a, q in qs.items()}
        t0 = time.perf_counter()
        raw = self.router.predict(text, laya_q, model=self.model)
        laya_ms = (time.perf_counter() - t0) * 1000
        p_true = {a: float(raw["answers"][f"q_{a}"]["noul"]) for a in qs}
        total = sum(p_true.values())
        if not total or any(math.isnan(v) for v in p_true.values()):
            raise RuntimeError(f"unusable Laya answer: {p_true}")
        probs = {a: (round(p_true[a] / total, 6) if a in p_true else 0.0) for a in ACTIONS}
        action = max(p_true, key=lambda a: (probs[a], -ACTIONS.index(a)))
        return DoomDecision(action, "laya", probs, p_true, qs, fs, text, laya_ms)
