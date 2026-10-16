"""Register a new grid game from a field mapping, for a game revealed on the day (stage 3).

A `GridSpec` says where in the game's state JSON to find the player, walls, hazards, enemies and
targets, plus the priorities line. `register(spec)` adds the game to `GAMES`, so the runner, log,
viewer and decider work unchanged. Example mapping (fields are illustrative, read the real state first):

    {
      "name": "doom", "title": "Doom-style arena",
      "width": "width", "height": "height",
      "player": "player",                      # {"x":..,"y":..} or [x, y]
      "grid": "grid", "grid_codes": {"wall": [1], "hazard": [4], "enemy": [3], "target": [2]},
      "enemies": "enemies", "targets": "exits", # optional lists of {"x","y"} in addition to grid codes
      "target_name": "the exit",
      "priorities": "Priorities: stay alive, never step next to an enemy, reach the exit, otherwise move closer to it.",
      "points": {"field": "score", "cap": 1000}
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .games import GAMES, DirFact
from .grid_facts import GridView, grid_facts, grid_state_text

Cell = tuple[int, int]


@dataclass
class GridSpec:
    name: str
    title: str
    width: str = "width"
    height: str = "height"
    player: str = "player"
    grid: str | None = "grid"
    grid_codes: dict[str, list[int]] = field(default_factory=dict)
    walls: str | None = None
    hazards: str | None = None
    enemies: str | None = None
    targets: str | None = None
    target_name: str = "the goal"
    priorities: str = ""
    blocked_from_direction: str | None = None   # field holding the current heading, for no-reverse games
    points: dict[str, Any] = field(default_factory=dict)
    extra_state_fields: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, path: str | Path) -> "GridSpec":
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))


def _get(state: dict, path: str | None, default=None):
    if not path:
        return default
    cur: Any = state
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


_XY_KEYS = (("x", "y"), ("col", "row"), ("c", "r"), ("column", "row"), ("px", "py"))


def _cell(v: Any) -> Cell:
    """Accepts {"x","y"}, {"col","row"} and similar pairs, or a [x, y] list."""
    if isinstance(v, dict):
        for kx, ky in _XY_KEYS:
            if kx in v and ky in v:
                return int(v[kx]), int(v[ky])
        raise ValueError(f"cannot read a cell from {v!r}: expected x/y or col/row keys")
    return int(v[0]), int(v[1])


def _cells(v: Any) -> set[Cell]:
    if not v:
        return set()
    if isinstance(v, dict) and any(kx in v for kx, _ in _XY_KEYS):
        return {_cell(v)}
    return {_cell(c) for c in v}


def build_view(spec: GridSpec, state: dict) -> GridView:
    grid = _get(state, spec.grid)
    if grid is not None and (spec.width not in state or spec.height not in state):
        h, w = len(grid), len(grid[0])
    else:
        w, h = int(_get(state, spec.width)), int(_get(state, spec.height))
    walls, hazards, threats, targets = set(), set(), set(), set()
    if grid is not None and spec.grid_codes:
        codes = {k: set(v) for k, v in spec.grid_codes.items()}
        for y, row in enumerate(grid):
            for x, c in enumerate(row):
                if c in codes.get("wall", ()):
                    walls.add((x, y))
                if c in codes.get("hazard", ()):
                    hazards.add((x, y))
                if c in codes.get("enemy", ()):
                    threats.add((x, y))
                if c in codes.get("target", ()):
                    targets.add((x, y))
    walls |= _cells(_get(state, spec.walls))
    hazards |= _cells(_get(state, spec.hazards))
    threats |= _cells(_get(state, spec.enemies))
    targets |= _cells(_get(state, spec.targets))
    player = _cell(_get(state, spec.player))
    blocked = set()
    if spec.blocked_from_direction:
        from .sims import OPPOSITE

        heading = _get(state, spec.blocked_from_direction)
        if heading in OPPOSITE:
            blocked.add(OPPOSITE[heading])
    return GridView(w, h, player, walls, hazards, threats, targets, spec.target_name, blocked, "reverses direction")


def register(spec: GridSpec) -> str:
    def facts(state: dict, style: str = "words") -> dict[str, DirFact]:
        return grid_facts(build_view(spec, state))

    def state_text(state: dict, **_: Any) -> str:
        extra = " ".join(f"{k}: {state[k]}." for k in spec.extra_state_fields if k in state)
        return grid_state_text(spec.title, build_view(spec, state), extra)

    def points(resp: dict) -> int:
        fld = spec.points.get("field", "score")
        cap = spec.points.get("cap", 1000)
        src = resp if fld in resp else (resp.get("state") or {})
        try:
            return min(int(cap), int(src.get(fld, 0)))
        except (TypeError, ValueError):
            return 0

    GAMES[spec.name] = {"facts": facts, "state_text": state_text, "priorities": spec.priorities, "points": points}
    return spec.name


def register_from_file(path: str | Path) -> str:
    return register(GridSpec.from_json(path))
