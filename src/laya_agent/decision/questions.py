"""Question designs: how an Observation becomes the typed questions of one Laya call.

Each design has an id written into every decision event, so experiments can be compared run
against run. A design only changes wording, layout and which typed questions are asked; the
candidate set is always exactly the legal actions, and the move always comes from Laya's
answers through one of three documented aggregation rules:

  choice       the `choice` answer of a single question (laya's own argmax)
  mean_choice  the same choice question asked under every cyclic option order in the same
               forward pass; the move is the argmax of the mean of Laya's probabilities
               (option_order exists upstream for exactly this presentation-bias averaging)
  noul_argmax  one `noul` question per candidate in the same pass; the move is the candidate
               with the highest P(true)

Budget facts from laya 0.4.6 (common.build_head): each option is cut to 48 tokens, options and
instructions share `head_max_len` (192 on the English checkpoint), and instructions only get
what the options leave. Keep option text short and put the decisive fact first.
"""

from __future__ import annotations

import string
from dataclasses import dataclass, field
from typing import Callable

from ..contracts import Observation

QUESTION_ID = "move"


@dataclass(frozen=True)
class BuiltQuestion:
    design_id: str
    questions: dict
    state: str
    label_to_action: dict[str, str]
    aggregation: str = "choice"
    move_qids: tuple[str, ...] = (QUESTION_ID,)
    notes: dict = field(default_factory=dict)


def _letters(n: int) -> list[str]:
    return list(string.ascii_uppercase[:n]) if n <= 26 else [f"M{i:02d}" for i in range(1, n + 1)]


def _instructions(obs: Observation, with_priorities: bool) -> str:
    parts = [obs.objective]
    if with_priorities and obs.priorities:
        parts.append(obs.priorities)
    parts.append("Which move should be played now?")
    return " ".join(p.strip() for p in parts if p)


def _choice(obs: Observation, design_id: str, labels: list[str], describe: bool, priorities: bool) -> BuiltQuestion:
    criteria = {}
    label_to_action = {}
    for label, c in zip(labels, obs.candidates):
        criteria[label] = c.description if describe else None
        label_to_action[label] = c.action_id
    q = {"type": "choice", "instructions": _instructions(obs, priorities), "criteria": criteria}
    return BuiltQuestion(design_id, {QUESTION_ID: q}, obs.state_text, label_to_action)


def _bare_v1(obs: Observation) -> BuiltQuestion:
    """Baseline: action names only. Measures what the factual descriptions add."""
    return _choice(obs, "bare_v1", [c.action_id for c in obs.candidates], describe=False, priorities=False)


def _facts_v1(obs: Observation) -> BuiltQuestion:
    """Action names plus the adapter's factual descriptions, generic instruction."""
    return _choice(obs, "facts_v1", [c.action_id for c in obs.candidates], describe=True, priorities=False)


def _goal_v1(obs: Observation) -> BuiltQuestion:
    """facts_v1 plus the game's general priorities in the instruction (never a per-turn verdict)."""
    return _choice(obs, "goal_v1", [c.action_id for c in obs.candidates], describe=True, priorities=True)


def _opaque_v1(obs: Observation) -> BuiltQuestion:
    """goal_v1 with neutral letter labels, so label wording cannot pull the answer."""
    return _choice(obs, "opaque_v1", _letters(len(obs.candidates)), describe=True, priorities=True)


def _rot_v1(obs: Observation) -> BuiltQuestion:
    """goal_v1 asked under every cyclic option order in one pass; Laya's probabilities averaged."""
    base = _goal_v1(obs)
    q = base.questions[QUESTION_ID]
    n = len(obs.candidates)
    questions = {}
    for r in range(n):
        order = [(i + r) % n for i in range(n)]
        questions[f"{QUESTION_ID}_r{r}"] = {**q, "option_order": order}
    return BuiltQuestion("rot_v1", questions, base.state, base.label_to_action, "mean_choice", tuple(questions))


def _noul_each_v1(obs: Observation) -> BuiltQuestion:
    """One yes/no question per legal move in one pass; the move is the highest P(true)."""
    questions = {}
    label_to_action = {}
    head = obs.objective + (" " + obs.priorities if obs.priorities else "")
    for i, c in enumerate(obs.candidates):
        qid = f"ok_{i}"
        questions[qid] = {
            "type": "noul",
            "instructions": f"{head} Is this a good move now? {c.description}",
            "criteria": {"true": "a good move for the objective", "false": "a poor move for the objective"},
        }
        label_to_action[qid] = c.action_id
    return BuiltQuestion("noul_each_v1", questions, obs.state_text, label_to_action, "noul_argmax", tuple(questions))


DESIGNS: dict[str, Callable[[Observation], BuiltQuestion]] = {
    "bare_v1": _bare_v1,
    "facts_v1": _facts_v1,
    "goal_v1": _goal_v1,
    "opaque_v1": _opaque_v1,
    "rot_v1": _rot_v1,
    "noul_each_v1": _noul_each_v1,
}

MAX_QUESTIONS = 32  # laya.studio documents 32 questions per request


def build_question(design_id: str, obs: Observation) -> BuiltQuestion:
    try:
        design = DESIGNS[design_id]
    except KeyError:
        raise ValueError(f"unknown question design {design_id!r}; known: {sorted(DESIGNS)}") from None
    built = design(obs)
    if sorted(set(built.label_to_action.values())) != sorted(c.action_id for c in obs.candidates):
        raise ValueError(f"design {design_id} does not cover every legal candidate exactly")
    if len(built.questions) > MAX_QUESTIONS:
        raise ValueError(f"design {design_id} asks {len(built.questions)} questions; the limit is {MAX_QUESTIONS}")
    return built
