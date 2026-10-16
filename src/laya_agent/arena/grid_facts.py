"""Generic per-direction facts for any grid game with up/down/left/right moves.

This is the reusable core behind the Snake facts, written so a new grid game (maze, Doom-style
arena, sliding puzzle with a player) only needs a small mapping from its state fields to a
`GridView`. Facts are immediate, one-move consequences computed deterministically; nothing here
chooses a move or looks more than one step ahead.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .games import DIRECTIONS, DirFact
from .sims import DIRS

Cell = tuple[int, int]


@dataclass
class GridView:
    """What the facts need to know about a grid game, independent of the API's field names."""

    width: int
    height: int
    player: Cell
    walls: set[Cell] = field(default_factory=set)        # cells that cannot be entered (move rejected or no-op)
    hazards: set[Cell] = field(default_factory=set)      # cells that end the game or cost a life on entry
    threats: set[Cell] = field(default_factory=set)      # cells next to which it is dangerous to stand (enemies)
    targets: set[Cell] = field(default_factory=set)      # cells worth reaching (goal, food, pickup)
    target_name: str = "the goal"
    blocked_dirs: set[str] = field(default_factory=set)  # directions the rules forbid outright (e.g. reverse)
    blocked_reason: str = "not allowed"
    body_size: int = 1                                    # for pocket detection: space needed to survive


def bfs_distance(start: Cell, goals: set[Cell], w: int, h: int, blocked: set[Cell]) -> int | None:
    if start in goals:
        return 0
    seen = {start}
    q = deque([(start, 0)])
    while q:
        (x, y), d = q.popleft()
        for dx, dy in DIRS.values():
            n = (x + dx, y + dy)
            if n in goals:
                return d + 1
            if 0 <= n[0] < w and 0 <= n[1] < h and n not in blocked and n not in seen:
                seen.add(n)
                q.append((n, d + 1))
    return None


def reachable_area(start: Cell, w: int, h: int, blocked: set[Cell]) -> int:
    seen = {start}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in DIRS.values():
            n = (x + dx, y + dy)
            if 0 <= n[0] < w and 0 <= n[1] < h and n not in blocked and n not in seen:
                seen.add(n)
                q.append(n)
    return len(seen) - 1


def neighbours(c: Cell) -> list[Cell]:
    return [(c[0] + dx, c[1] + dy) for dx, dy in DIRS.values()]


def grid_facts(v: GridView) -> dict[str, DirFact]:
    """One DirFact per direction: decisive consequence first, then distance trend, then space."""
    blocked_now = v.walls | v.hazards
    d_before = bfs_distance(v.player, v.targets, v.width, v.height, blocked_now) if v.targets else None
    out: dict[str, DirFact] = {}
    for d in DIRECTIONS:
        if d in v.blocked_dirs:
            out[d] = DirFact(d, "blocked", f"move {d}: {v.blocked_reason}, not allowed.", legal=False)
            continue
        dx, dy = DIRS[d]
        n = (v.player[0] + dx, v.player[1] + dy)
        if not (0 <= n[0] < v.width and 0 <= n[1] < v.height) or n in v.walls:
            out[d] = DirFact(d, "wall", f"move {d}: blocked by a wall, nothing happens.", legal=False)
            continue
        if n in v.hazards:
            out[d] = DirFact(d, "hazard", f"move {d}: steps into danger, game over.", legal=True, fatal=True)
            continue
        reaches = n in v.targets
        adjacent_threats = sum(1 for c in neighbours(n) if c in v.threats) + (1 if n in v.threats else 0)
        area = reachable_area(n, v.width, v.height, blocked_now)
        trapped = area < v.body_size
        data = {"to": list(n), "area": area, "adjacent_threats": adjacent_threats}
        parts = []
        if reaches:
            parts.append(f"reaches {v.target_name} now")
            kind = "reach"
        else:
            kind = "move"
            d_after = bfs_distance(n, v.targets, v.width, v.height, blocked_now) if v.targets else None
            data.update(dist_before=d_before, dist_after=d_after)
            if d_before is None or d_after is None:
                parts.append(f"{v.target_name} is not reachable")
            elif d_after < d_before:
                parts.append(f"closer to {v.target_name} ({d_before} to {d_after} steps)")
            elif d_after > d_before:
                parts.append(f"farther from {v.target_name} ({d_before} to {d_after} steps)")
            else:
                parts.append(f"same distance to {v.target_name} ({d_before} steps)")
        if adjacent_threats:
            parts.append(f"next to {adjacent_threats} enemy" + ("ies" if adjacent_threats > 1 else ""))
            data["danger"] = True
        if trapped:
            parts.append(f"enters a closed pocket of {area} cells")
        else:
            parts.append(f"open space {area} cells")
        safe = "safe, " if not adjacent_threats and not trapped else ""
        out[d] = DirFact(d, kind, f"move {d}: {safe}" + ", ".join(parts) + ".", legal=True, data=data)
    return out


def grid_state_text(name: str, v: GridView, extra: str = "") -> str:
    tx = ", ".join(f"x={x}, y={y}" for x, y in sorted(v.targets)[:3]) or "none"
    text = (f"{name} on a {v.width}x{v.height} grid. Player at x={v.player[0]}, y={v.player[1]}. "
            f"{v.target_name.capitalize()} at {tx}.")
    if v.threats:
        text += f" Enemies: {len(v.threats)}."
    return text + (" " + extra if extra else "")
