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
from .questions import BuiltQuestion, build_question

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
        first = built.questions[built.move_qids[0]]
        if first.get("type") == "choice":
            budget = self.head_budget(first)
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
        decision.aggregation = built.aggregation
        try:
            self._read_answers(decision, built, result["answers"])
        except (KeyError, TypeError, ValueError) as exc:
            decision.error = f"unexpected laya response shape: {type(exc).__name__} {exc}"
        return decision

    @staticmethod
    def _read_answers(decision: Decision, built: BuiltQuestion, answers: dict) -> None:
        to_action = built.label_to_action
        if built.aggregation == "choice":
            answer = answers[built.move_qids[0]]
            label = str(answer["choice"])
            probs = answer["probabilities"]
            decision.chosen_label = label
            decision.chosen_action_id = to_action.get(label)
            decision.probabilities = {to_action.get(str(k), f"<unknown:{k}>"): float(v) for k, v in probs.items()}
            decision.answer_confidence = answer.get("answer_confidence")
            decision.confidence = answer.get("confidence")
            return

        if built.aggregation == "mean_choice":
            labels = list(to_action)
            per_view = [answers[qid]["probabilities"] for qid in built.move_qids]
            mean = {l: sum(float(v[l]) for v in per_view) / len(per_view) for l in labels}
            # Ties keep candidate order; the tie itself is recorded so it is never hidden.
            label = max(labels, key=lambda l: mean[l])
            decision.aggregate_detail = {
                "views": len(per_view),
                "view_choices": [str(answers[qid]["choice"]) for qid in built.move_qids],
                "tie": sum(1 for l in labels if mean[l] == mean[label]) > 1,
            }
        elif built.aggregation == "noul_argmax":
            labels = list(to_action)
            p_true = {l: float(answers[l]["noul"]) for l in labels}
            label = max(labels, key=lambda l: p_true[l])
            total = sum(p_true.values()) or 1.0
            mean = {l: p_true[l] / total for l in labels}
            decision.aggregate_detail = {
                "p_true": {to_action[l]: p_true[l] for l in labels},
                "tie": sum(1 for l in labels if p_true[l] == p_true[label]) > 1,
            }
        else:
            raise ValueError(f"unknown aggregation {built.aggregation!r}")

        decision.chosen_label = label
        decision.chosen_action_id = to_action[label]
        decision.probabilities = {to_action[l]: round(mean[l], 6) for l in labels}
        decision.answer_confidence = round(max(mean.values()), 6)
        decision.confidence = None
