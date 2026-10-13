"""The only component that chooses moves: one Laya `choice` call per decision.

Verified against laya 0.4.6 (see docs/research.md). The answer is read from
result["answers"]["move"]["choice"], which laya computes as the argmax before rounding,
so the move never depends on re-deriving a winner from the rounded probabilities.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from ..contracts import Decision, DecisionError, Observation
from .questions import QUESTION_ID, build_question

BUILTIN_MODELS = {"english", "multilingual", "typed-decisions"}


class LayaDecider:
    def __init__(
        self,
        model: str = "english",
        device: str | None = None,
        design_id: str = "facts_v1",
        head_max_len: int | None = None,
        max_len: int | None = None,
        router: Any = None,
    ) -> None:
        if router is None:
            import laya

            router = laya.Router(device=device, max_loaded=1)
        self.router = router
        self.design_id = design_id
        self.head_max_len = head_max_len
        self.max_len = max_len
        if model in BUILTIN_MODELS:
            self.model_name = model
        else:
            # A local or Hub checkpoint path, for example a fine-tuned Laya checkpoint.
            self.model_name = self.router.register("custom", model, description="configured checkpoint")
        self._agent = None

    def load(self) -> dict[str, Any]:
        """Load weights once and report cold-start cost separately from per-move latency."""
        import laya

        t0 = time.perf_counter()
        self._agent = self.router.load(self.model_name)
        info = {
            "laya_version": laya.__version__,
            "model": self.model_name,
            "cold_load_s": round(time.perf_counter() - t0, 3),
            "device": str(getattr(self._agent, "device", None)),
            "revision": getattr(self.router, "loaded_revisions", {}).get(self.model_name),
            "head_max_len": self.head_max_len or getattr(self._agent, "cfg", {}).get("head_max_len"),
            "max_len": self.max_len or getattr(self._agent, "cfg", {}).get("max_len"),
        }
        return info

    def head_budget(self, question: dict) -> dict[str, Any] | None:
        """Whether laya's head budget cut the instructions or options (not reported by usage)."""
        if self._agent is None or not hasattr(self._agent, "tok"):
            return None
        try:
            from laya.common import build_head

            crit = question["criteria"]
            q = {"t": "choice", "ins": question["instructions"], "crit": crit if isinstance(crit, dict) else {c: None for c in crit}}
            limit = self.head_max_len or self._agent.cfg.get("head_max_len", 192)
            used, _, stats = build_head(self._agent.tok, q, limit)
            full, _, _ = build_head(self._agent.tok, q, 1_000_000)
            return {"head_tokens": len(used), "head_tokens_needed": len(full), "cut": len(used) < len(full), **stats}
        except Exception as exc:  # diagnostics only; never blocks a decision
            return {"error": str(exc)}

    def decide(self, observation: Observation) -> Decision:
        built = build_question(self.design_id, observation)
        kwargs: dict[str, Any] = {"model": self.model_name}
        if self.head_max_len:
            kwargs["head_max_len"] = self.head_max_len
        if self.max_len:
            kwargs["max_len"] = self.max_len

        decision_id = uuid.uuid4().hex
        t0 = time.perf_counter()
        try:
            result = self.router.predict(built.state, built.questions, **kwargs)
        except Exception as exc:
            raise DecisionError(f"laya predict failed: {type(exc).__name__}: {exc}") from exc
        latency_ms = (time.perf_counter() - t0) * 1000

        usage = dict(result.get("usage") or {}) if isinstance(result, dict) else {}
        budget = self.head_budget(built.questions[QUESTION_ID])
        if budget is not None:
            usage["head_budget"] = budget

        decision = Decision(
            decision_id=decision_id,
            design_id=built.design_id,
            model=self.model_name,
            question=built.questions,
            state_text=built.state,
            label_to_action=built.label_to_action,
            raw_response=result,
            chosen_label=None,
            chosen_action_id=None,
            probabilities={},
            answer_confidence=None,
            confidence=None,
            latency_ms=latency_ms,
            routing=result.get("routing") if isinstance(result, dict) else None,
            usage=usage,
        )
        try:
            answer = result["answers"][QUESTION_ID]
            label = answer["choice"]
            probs = answer["probabilities"]
        except (KeyError, TypeError) as exc:
            decision.error = f"unexpected laya response shape: missing {exc}"
            return decision

        decision.chosen_label = str(label)
        decision.chosen_action_id = built.label_to_action.get(str(label))
        decision.probabilities = {
            built.label_to_action.get(str(k), f"<unknown:{k}>"): float(v) for k, v in probs.items()
        }
        decision.answer_confidence = answer.get("answer_confidence")
        decision.confidence = answer.get("confidence")
        return decision
