"""Checks that a Laya decision maps to exactly one current legal candidate. Never picks a move."""

from __future__ import annotations

import math

from ..contracts import Decision, Observation


def validate_decision(decision: Decision, obs: Observation) -> list[str]:
    problems: list[str] = []
    if decision.error:
        problems.append(f"laya error: {decision.error}")
        return problems
    if decision.chosen_label is None:
        problems.append("laya answer has no choice")
        return problems
    if decision.chosen_label not in decision.label_to_action:
        problems.append(f"choice {decision.chosen_label!r} is not one of the offered labels")
        return problems
    action_id = decision.label_to_action[decision.chosen_label]
    if action_id != decision.chosen_action_id:
        problems.append("chosen_action_id does not match the label mapping")
    if obs.candidate(action_id) is None:
        problems.append(f"action {action_id!r} is not legal in the current state")

    probs = decision.probabilities
    if set(probs) != set(decision.label_to_action.values()):
        problems.append("probabilities do not cover exactly the offered candidates")
    values = list(probs.values())
    if any(not isinstance(v, (int, float)) or math.isnan(v) or v < 0 for v in values):
        problems.append("probabilities contain invalid values")
    elif values and abs(sum(values) - 1.0) > 0.01:
        problems.append(f"probabilities sum to {sum(values):.4f}, not 1")

    usage = decision.usage or {}
    if usage.get("options"):
        problems.append(f"options collapsed in the head budget: {usage['options']}")
    return problems
