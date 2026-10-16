"""One Laya call per move: one yes/no (noul) question per offered direction, answered in one pass.

The move is Laya's highest P(true). A rule-based safety move ("fallback") is used only when Laya's
pick is immediately fatal, it is logged as source "fallback", and it is capped at 10% of a session.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from .games import DIRECTIONS, GAMES, DirFact

TEMPLATES = {
    # priorities + question + the fact for this direction, decisive fact last so it sits next to the question
    "noul_v1": "{priorities} Is moving {d} a good move now? {fact}",
    # fact first, then the question; priorities moved into the state text
    "noul_fact_first": "{fact} Is moving {d} a good move now?",
    # direction word removed, so Laya judges the facts and not the word "right" or "up"
    "noul_nodir": "{priorities} Is this a good move now? This move: {fact_nodir}",
    "noul_nodir_short": "Is this a good move now? This move: {fact_nodir}",
}
CRITERIA = {"true": "a good move for these priorities", "false": "a poor move for these priorities"}


@dataclass
class MoveDecision:
    action: str
    source: str                      # laya | fallback
    laya_choice: str
    probabilities: dict[str, float]  # exactly up/down/left/right, sums to 1
    p_true: dict[str, float]         # raw Laya P(true) for the offered directions
    questions: dict[str, str]        # direction -> question text sent to Laya
    facts: dict[str, DirFact]
    state_text: str
    laya_ms: float
    raw: Any = None
    reason: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def confidence(self) -> float:
        return self.probabilities[self.action]

    def decision_block(self) -> dict:
        return {
            "questions": [self.questions[d] for d in DIRECTIONS if d in self.questions],
            "probabilities": dict(self.probabilities),
            "chosen": self.action,
            "confidence": self.probabilities[self.action],
            "source": self.source,
        }


class LayaMoveDecider:
    def __init__(self, game: str, router: Any = None, model: str = "english", device: str | None = None,
                 template: str = "noul_nodir", offer: str = "legal", style: str = "words",
                 fallback_cap: float = 0.10, fallback_horizon: int = 50) -> None:
        if router is None:
            import laya

            router = laya.Router(device=device, max_loaded=1)
        self.router = router
        self.game = game
        self.spec = GAMES[game]
        self.model_source = model  # what was asked for: a built-in name or a checkpoint path
        if model not in ("english", "multilingual", "typed-decisions") and hasattr(router, "register"):
            # A local or Hub checkpoint path, for example a fine-tuned Laya
            model = router.register("custom", model, description="configured checkpoint")
        self.model = model
        self.template = template
        self.offer = offer
        self.style = style
        self.fallback_cap = fallback_cap
        self.fallback_horizon = fallback_horizon
        self.agent = None
        self._last_eaten = -1
        self._since_food = 0

    def new_session(self) -> None:
        self._last_eaten, self._since_food = -1, 0

    def note_applied(self) -> None:
        self._since_food += 1

    def load(self) -> dict:
        try:
            import laya

            version = laya.__version__
        except ImportError:
            version = None
        t0 = time.perf_counter()
        self.agent = self.router.load(self.model)
        return {"laya_version": version, "model": self.model, "device": str(getattr(self.agent, "device", "")),
                "load_s": round(time.perf_counter() - t0, 2), "revision": getattr(self.router, "loaded_revisions", {}).get(self.model),
                "template": self.template, "offer": self.offer, "style": self.style}

    def _questions(self, facts: dict[str, DirFact], exclude: set[str]) -> dict[str, str]:
        tpl = TEMPLATES[self.template]
        offered = [d for d in DIRECTIONS if d not in exclude and (self.offer == "all" or facts[d].legal)]
        return {d: tpl.format(priorities=self.spec["priorities"], d=d, fact=facts[d].text,
                              fact_nodir=facts[d].text.split(": ", 1)[-1]) for d in offered}

    def decide(self, state: dict, applied: int, fallbacks: int, exclude: set[str] | None = None) -> MoveDecision:
        facts = self.spec["facts"](state, style=self.style)
        exclude = set(exclude or ())
        questions = self._questions(facts, exclude)
        if not questions:
            raise RuntimeError("no direction left to ask Laya about")
        if self.game == "snake":
            # A true, changing fact: breaks repeated identical questions when the snake circles
            eaten = state.get("foodEaten", 0)
            if eaten != self._last_eaten:
                self._last_eaten, self._since_food = eaten, 0
            state_text = self.spec["state_text"](state, since_food=self._since_food)
        else:
            state_text = self.spec["state_text"](state)
        if self.template in ("noul_fact_first", "noul_nodir_short"):
            state_text = self.spec["priorities"] + " " + state_text
        laya_q = {f"q_{d}": {"type": "noul", "instructions": q, "criteria": dict(CRITERIA)} for d, q in questions.items()}

        t0 = time.perf_counter()
        raw = self.router.predict(state_text, laya_q, model=self.model)
        laya_ms = (time.perf_counter() - t0) * 1000

        p_true = {d: float(raw["answers"][f"q_{d}"]["noul"]) for d in questions}
        total = sum(p_true.values())
        if not total or any(math.isnan(v) for v in p_true.values()):
            raise RuntimeError(f"unusable Laya answer: {p_true}")
        probabilities = {d: (round(p_true[d] / total, 6) if d in p_true else 0.0) for d in DIRECTIONS}
        ranked = sorted(p_true, key=lambda d: (-probabilities[d], DIRECTIONS.index(d)))
        laya_choice = ranked[0]

        action, source, reason = laya_choice, "laya", ""
        pick = facts[laya_choice]
        if not pick.legal or pick.fatal:
            safe = [d for d in ranked if facts[d].legal and not facts[d].fatal]
            budget = math.floor(self.fallback_cap * max(applied + 1, self.fallback_horizon))
            if safe and fallbacks + 1 <= budget:
                action, source = safe[0], "fallback"
                reason = f"Laya's pick '{laya_choice}' is {pick.kind}; playing Laya's highest-ranked safe move"
            elif not pick.legal:
                # Never send a move the server will reject; ask Laya again without it
                return self.decide(state, applied, fallbacks, exclude | {laya_choice})
            else:
                reason = f"Laya's pick '{laya_choice}' is {pick.kind}; fallback budget used up, sending Laya's move"
        return MoveDecision(action, source, laya_choice, probabilities, p_true, questions, facts, state_text, laya_ms,
                            raw=raw, reason=reason, extra={"excluded": sorted(exclude)})
