"""Question designs: how an Observation becomes one Laya `choice` question.

Each design has an id that is written into every decision event, so experiments can be
compared run against run. Designs only change wording and layout; the candidate set is
always exactly the legal actions, and the answer is always Laya's own `choice`.

Budget facts from laya 0.4.6 (common.build_head): each option is cut to 48 tokens, options
and instructions share `head_max_len` (192 on the English checkpoint), and instructions only
get what the options leave. Keep option text short and put the decisive fact first.
"""

from __future__ import annotations

import string
from dataclasses import dataclass
from typing import Callable

from ..contracts import Observation

QUESTION_ID = "move"


@dataclass(frozen=True)
class BuiltQuestion:
    design_id: str
    questions: dict
    state: str
    label_to_action: dict[str, str]


def _opaque_labels(n: int) -> list[str]:
    letters = string.ascii_uppercase
    if n <= len(letters):
        return list(letters[:n])
    return [f"M{i:02d}" for i in range(1, n + 1)]


def _facts_v1(obs: Observation) -> BuiltQuestion:
    """Semantic labels (the action ids) plus the adapter's factual descriptions."""
    criteria = {}
    label_to_action = {}
    for c in obs.candidates:
        criteria[c.action_id] = c.description
        label_to_action[c.action_id] = c.action_id
    instructions = f"{obs.objective} Which move should be played now?"
    return BuiltQuestion(
        "facts_v1",
        {QUESTION_ID: {"type": "choice", "instructions": instructions, "criteria": criteria}},
        obs.state_text,
        label_to_action,
    )


def _opaque_v1(obs: Observation) -> BuiltQuestion:
    """Neutral letter labels, so label wording cannot pull the answer (README known issue)."""
    labels = _opaque_labels(len(obs.candidates))
    criteria = {}
    label_to_action = {}
    for label, c in zip(labels, obs.candidates):
        criteria[label] = c.description
        label_to_action[label] = c.action_id
    instructions = f"{obs.objective} Which move should be played now?"
    return BuiltQuestion(
        "opaque_v1",
        {QUESTION_ID: {"type": "choice", "instructions": instructions, "criteria": criteria}},
        obs.state_text,
        label_to_action,
    )


def _bare_v1(obs: Observation) -> BuiltQuestion:
    """Baseline: labels only, no per-option facts. Measures what the descriptions add."""
    label_to_action = {c.action_id: c.action_id for c in obs.candidates}
    return BuiltQuestion(
        "bare_v1",
        {
            QUESTION_ID: {
                "type": "choice",
                "instructions": f"{obs.objective} Which move should be played now?",
                "criteria": list(label_to_action),
            }
        },
        obs.state_text,
        label_to_action,
    )


DESIGNS: dict[str, Callable[[Observation], BuiltQuestion]] = {
    "facts_v1": _facts_v1,
    "opaque_v1": _opaque_v1,
    "bare_v1": _bare_v1,
}


def build_question(design_id: str, obs: Observation) -> BuiltQuestion:
    try:
        design = DESIGNS[design_id]
    except KeyError:
        raise ValueError(f"unknown question design {design_id!r}; known: {sorted(DESIGNS)}") from None
    built = design(obs)
    if set(built.label_to_action.values()) != {c.action_id for c in obs.candidates}:
        raise ValueError(f"design {design_id} does not cover every legal candidate exactly")
    return built
