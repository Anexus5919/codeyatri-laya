"""Facts about each direction for Snake and 2048. Facts only: Python never says which move is best.

Every fact is the immediate, one-move consequence (no search over future moves). Each direction is
labelled with a kind so the runner knows what is illegal (rejected by the server) or fatal.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

from .sims import DIRS, OPPOSITE, slide_board

DIRECTIONS = ("up", "down", "left", "right")


@dataclass
class DirFact:
    direction: str
    kind: str          # snake: reverse|wall|body|eat|move ; 2048: noop|move
    text: str          # the fact sentence given to Laya, decisive part first
    legal: bool        # False: the server rejects it
    fatal: bool = False  # True: legal but ends the game at once (wall or body hit)
    data: dict = field(default_factory=dict)


# ---------------------------------------------------------------- Snake
SNAKE_PRIORITIES = (
    "Snake rules: hitting a wall or your own body ends the game. "
    "Priorities: stay alive, never enter a closed pocket smaller than the snake, eat the food, "
    "otherwise move closer to the food."
)


EAT_TEXT = {
    "words": "move {d}: safe, eats the food now (+60 points), open space {area} cells.",
    "numbers": "move {d}: safe, eats the food now (+60 points), open space {area} cells.",
    "eat_best": "move {d}: safe, eats the food now, the best result (+60 points), open space {area} cells.",
    "eat_reach": "move {d}: safe, reaches the food and eats it (+60 points), open space {area} cells.",
    "eat_goal": "move {d}: safe, eats the food now (+60 points, the goal of the game), open space {area} cells.",
}


def _bfs(start, goal, w, h, blocked) -> int | None:
    if start == goal:
        return 0
    seen = {start}
    q = deque([(start, 0)])
    while q:
        (x, y), d = q.popleft()
        for dx, dy in DIRS.values():
            n = (x + dx, y + dy)
            if n == goal:
                return d + 1
            if 0 <= n[0] < w and 0 <= n[1] < h and n not in blocked and n not in seen:
                seen.add(n)
                q.append((n, d + 1))
    return None


def _area(start, w, h, blocked) -> int:
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


def snake_facts(state: dict, style: str = "words") -> dict[str, DirFact]:
    w, h = state["width"], state["height"]
    body = [(p["x"], p["y"]) for p in state["snake"]]
    head = body[0]
    food = (state["food"]["x"], state["food"]["y"]) if state.get("food") else None
    length = len(body)
    d_before = _bfs(head, food, w, h, set(body[1:-1])) if food else None
    out: dict[str, DirFact] = {}
    for d in DIRECTIONS:
        dx, dy = DIRS[d]
        nx, ny = head[0] + dx, head[1] + dy
        if length > 1 and d == OPPOSITE.get(state.get("direction", ""), ""):
            out[d] = DirFact(d, "reverse", f"move {d}: turns back into your own neck, not allowed.", legal=False)
            continue
        if not (0 <= nx < w and 0 <= ny < h):
            out[d] = DirFact(d, "wall", f"move {d}: hits the wall, game over.", legal=True, fatal=True)
            continue
        eats = (nx, ny) == food
        new_body = [(nx, ny)] + (body if eats else body[:-1])
        # Conservative: the arena may test collisions before the tail moves, so the tail cell counts as body
        if (nx, ny) in new_body[1:] or (nx, ny) in body[1:]:
            out[d] = DirFact(d, "body", f"move {d}: hits your own body, game over.", legal=True, fatal=True)
            continue
        area = _area((nx, ny), w, h, set(new_body[1:]))
        new_len = length + (1 if eats else 0)
        trapped = area < new_len
        data = {"area": area, "length": new_len}
        if eats:
            text = EAT_TEXT.get(style, EAT_TEXT["words"]).format(d=d, area=area)
            if trapped:
                text = f"move {d}: eats the food but enters a closed pocket of {area} cells, smaller than the snake ({new_len})."
            out[d] = DirFact(d, "eat", text, legal=True, data=data)
            continue
        d_after = _bfs((nx, ny), food, w, h, set(new_body[1:-1])) if food else None
        data.update(dist_before=d_before, dist_after=d_after)
        if d_after is None or d_before is None:
            trend = "the food is not reachable"
        elif style == "numbers":
            trend = f"food distance {d_before} to {d_after}"
        elif d_after < d_before:
            trend = f"closer to the food ({d_before} to {d_after} steps)"
        elif d_after > d_before:
            trend = f"farther from the food ({d_before} to {d_after} steps)"
        else:
            trend = f"same distance to the food ({d_before} steps)"
        if trapped:
            text = f"move {d}: enters a closed pocket of {area} cells, smaller than the snake ({new_len}); {trend}."
        else:
            text = f"move {d}: safe, {trend}, open space {area} cells."
        out[d] = DirFact(d, "move", text, legal=True, data=data)
    return out


def snake_state_text(state: dict, since_food: int | None = None) -> str:
    hx, hy = state["snake"][0]["x"], state["snake"][0]["y"]
    f = state.get("food") or {}
    text = (
        f"Snake game on a {state['width']}x{state['height']} board. Head at x={hx}, y={hy}, moving {state.get('direction')}. "
        f"Snake length {len(state['snake'])}. Food at x={f.get('x')}, y={f.get('y')}. "
        f"Foods eaten {state.get('foodEaten', 0)} of 15."
    )
    if since_food is not None:
        text += f" Moves since the last food: {since_food}."
    return text


def snake_points(resp: dict) -> int:
    st = resp.get("state") or {}
    return min(1000, int(st.get("foodEaten", 0)) * 60 + (100 if resp.get("won") else 0))


# ---------------------------------------------------------------- 2048
G2048_PRIORITIES = (
    "2048 rules: tiles slide and equal tiles merge. "
    "Priorities: keep the largest tile in the bottom-left corner, keep the board in order with bigger tiles "
    "toward the bottom-left, keep many empty cells, never move the largest tile out of the corner."
)

CORNERS = ((0, 0), (0, 3), (3, 0), (3, 3))


def _max_pos(grid):
    best = max(max(r) for r in grid)
    return best, [(r, c) for r in range(4) for c in range(4) if grid[r][c] == best]


def _in_corner(grid) -> bool:
    _, pos = _max_pos(grid)
    return any(p in CORNERS for p in pos)


CORNER_NAMES = {(0, 0): "top-left", (0, 3): "top-right", (3, 0): "bottom-left", (3, 3): "bottom-right"}


def _corner_of_max(grid) -> tuple[int, int] | None:
    _, pos = _max_pos(grid)
    for p in pos:
        if p in CORNERS:
            return p
    return None


def _edge_disorder(grid, corner) -> int:
    """How many neighbouring pairs break the descending order along the two edges at the corner."""
    r0, c0 = corner
    row = grid[r0][:] if c0 == 0 else grid[r0][::-1]
    col = [grid[r][c0] for r in range(4)]
    col = col if r0 == 0 else col[::-1]
    bad = 0
    for line in (row, col):
        vals = [v for v in line]
        for a, b in zip(vals, vals[1:]):
            if b > a:
                bad += 1
    return bad


def _merge_words(grid, d) -> str:
    """Names the merges a move makes, e.g. 'merges two 64s into 128'."""
    names = []
    n = 4
    for i in range(n):
        if d in ("left", "right"):
            line = grid[i][:] if d == "left" else grid[i][::-1]
        else:
            col = [grid[r][i] for r in range(n)]
            line = col if d == "up" else col[::-1]
        tiles = [v for v in line if v]
        j = 0
        while j < len(tiles):
            if j + 1 < len(tiles) and tiles[j] == tiles[j + 1]:
                names.append(tiles[j])
                j += 2
            else:
                j += 1
    if not names:
        return "no merges"
    names.sort(reverse=True)
    parts = [f"two {v}s into {v * 2}" for v in names[:3]]
    return "merges " + ", ".join(parts) + (" and more" if len(names) > 3 else "")


def g2048_facts_v2(state: dict) -> dict[str, DirFact]:
    grid = state["grid"]
    best = max(max(r) for r in grid)
    corner_before = _corner_of_max(grid)
    empty_before = sum(v == 0 for row in grid for v in row)
    out: dict[str, DirFact] = {}
    for d in DIRECTIONS:
        new, pts, merges = slide_board(grid, d)
        if new == grid:
            out[d] = DirFact(d, "noop", f"move {d}: does not move any tile, not allowed.", legal=False)
            continue
        corner_after = _corner_of_max(new)
        new_best = max(max(r) for r in new)
        empty_after = sum(v == 0 for row in new for v in row)
        if corner_after is None and corner_before is not None:
            corner = f"moves the largest tile ({best}) out of the {CORNER_NAMES[corner_before]} corner"
        elif corner_after is not None:
            corner = f"keeps the largest tile ({new_best}) in the {CORNER_NAMES[corner_after]} corner"
            if corner_before is not None and corner_after != corner_before:
                corner = f"moves the largest tile ({new_best}) to another corner ({CORNER_NAMES[corner_after]})"
        else:
            corner = f"the largest tile ({new_best}) is not in a corner"
        order = ""
        if corner_after is not None:
            order = ", tiles along its edges stay in order" if _edge_disorder(new, corner_after) == 0 else                 ", tiles along its edges are out of order"
        text = f"move {d}: {corner}{order}, {_merge_words(grid, d)}, {empty_after} empty cells (now {empty_before})."
        out[d] = DirFact(d, "move", text, legal=True,
                         data={"points": pts, "merges": merges, "empty_after": empty_after,
                               "corner_after": CORNER_NAMES.get(corner_after), "corner_lost": corner_before and not corner_after,
                               "edge_disorder": _edge_disorder(new, corner_after) if corner_after else None})
    return out


ANCHOR = (3, 0)  # bottom-left; the priorities name this corner, so the facts report against it


def _disorder(grid) -> int:
    """Tiles out of order for a bottom-left anchor: a row should not grow to the right, a column should not shrink downwards."""
    bad = sum(1 for r in range(4) for c in range(3) if grid[r][c + 1] and grid[r][c + 1] > grid[r][c])
    bad += sum(1 for c in range(4) for r in range(3) if grid[r + 1][c] and grid[r][c] > grid[r + 1][c])
    return bad


def _trend(before: int, after: int, more: str, less: str, same: str, unit: str) -> str:
    if after == before:
        return f"{same} ({before} {unit})"
    return f"{more if after < before else less} ({before} to {after} {unit})"


def g2048_facts_v3(state: dict) -> dict[str, DirFact]:
    grid = state["grid"]
    best = max(max(r) for r in grid)
    anchored = grid[ANCHOR[0]][ANCHOR[1]] == best
    dis0 = _disorder(grid)
    empty0 = sum(v == 0 for row in grid for v in row)
    out: dict[str, DirFact] = {}
    for d in DIRECTIONS:
        new, pts, merges = slide_board(grid, d)
        if new == grid:
            out[d] = DirFact(d, "noop", f"move {d}: does not move any tile, not allowed.", legal=False)
            continue
        nbest = max(max(r) for r in new)
        in_corner = new[ANCHOR[0]][ANCHOR[1]] == nbest
        if anchored and not in_corner:
            corner = f"moves the largest tile ({best}) out of the bottom-left corner"
        elif in_corner and not anchored:
            corner = f"moves the largest tile ({nbest}) into the bottom-left corner"
        elif in_corner:
            corner = f"keeps the largest tile ({nbest}) in the bottom-left corner"
        else:
            corner = f"the largest tile ({nbest}) is not in the bottom-left corner"
        dis1 = _disorder(new)
        empty1 = sum(v == 0 for row in new for v in row)
        order = _trend(dis0, dis1, "more in order", "less in order", "same order", "tiles out of order")
        # for empty cells, more is better, so swap the comparison
        if empty1 == empty0:
            space = f"same empty cells ({empty0})"
        elif empty1 > empty0:
            space = f"more empty cells ({empty0} to {empty1})"
        else:
            space = f"fewer empty cells ({empty0} to {empty1})"
        text = f"move {d}: {corner}, {order}, {space}, {_merge_words(grid, d)}."
        out[d] = DirFact(d, "move", text, legal=True,
                         data={"in_corner": in_corner, "corner_lost": anchored and not in_corner, "disorder": dis1,
                               "empty_after": empty1, "merges": merges, "points": pts})
    return out


def g2048_facts_v3s(state: dict, variant: str = "v3s") -> dict[str, DirFact]:
    """Same measurements as v3, worded as short clauses that repeat the priorities' own words."""
    base = g2048_facts_v3(state)
    grid = state["grid"]
    dis0 = _disorder(grid)
    empty0 = sum(v == 0 for row in grid for v in row)
    for d, f in base.items():
        if not f.legal:
            continue
        x = f.data
        if x["corner_lost"]:
            c = "moves the largest tile out of the corner"
        elif x["in_corner"]:
            c = "keeps the largest tile in the bottom-left corner"
        else:
            c = "largest tile not in the bottom-left corner"
        o = "board more in order" if x["disorder"] < dis0 else ("board less in order" if x["disorder"] > dis0 else "board order unchanged")
        e = "more empty cells" if x["empty_after"] > empty0 else ("fewer empty cells" if x["empty_after"] < empty0 else "same empty cells")
        if variant == "v3n":
            f.text = f"move {d}: {c}; board order {dis0} to {x['disorder']} tiles out of place; empty cells {empty0} to {x['empty_after']}."
        elif variant == "v3c":
            f.text = f"move {d}: {c}."
        else:
            f.text = f"move {d}: {c}, {o}, {e}."
    return base


def g2048_facts(state: dict, style: str = "words") -> dict[str, DirFact]:
    if style in ("v3s", "v3n", "v3c"):
        return g2048_facts_v3s(state, style)
    if style == "v3":
        return g2048_facts_v3(state)
    if style == "v2":
        return g2048_facts_v2(state)
    grid = state["grid"]
    empty_before = sum(v == 0 for row in grid for v in row)
    corner_before = _in_corner(grid)
    best = max(max(r) for r in grid)
    out: dict[str, DirFact] = {}
    for d in DIRECTIONS:
        new, pts, merges = slide_board(grid, d)
        if new == grid:
            out[d] = DirFact(d, "noop", f"move {d}: does not move any tile, not allowed.", legal=False)
            continue
        empty_after = sum(v == 0 for row in new for v in row)
        corner_after = _in_corner(new)
        if corner_before and not corner_after:
            corner = f"moves the largest tile ({best}) out of its corner"
        elif corner_after:
            corner = f"keeps the largest tile ({best}) in a corner"
        else:
            corner = f"the largest tile ({best}) is not in a corner"
        merge = f"merges {merges} pair{'s' if merges != 1 else ''} (+{pts} points)" if merges else "no merges"
        text = f"move {d}: {corner}, {merge}, {empty_after} empty cells (now {empty_before})."
        out[d] = DirFact(d, "move", text, legal=True,
                         data={"points": pts, "merges": merges, "empty_after": empty_after, "corner_after": corner_after,
                               "corner_lost": corner_before and not corner_after})
    return out


def g2048_state_text(state: dict) -> str:
    rows = " / ".join(" ".join(str(v) for v in row) for row in state["grid"])
    return f"2048 game, 4x4 board (rows top to bottom): {rows}. Score {state.get('score', 0)}, largest tile {state.get('best')}."


def g2048_points(resp: dict) -> int:
    st = resp.get("state") or {}
    best = max(int(st.get("best") or 2), 2)
    return min(1000, int(max(0, math.log2(best) - 6) * 143 + int(st.get("score", 0)) // 1000))


GAMES = {
    "snake": {"facts": snake_facts, "state_text": snake_state_text, "priorities": SNAKE_PRIORITIES, "points": snake_points},
    "2048": {"facts": g2048_facts, "state_text": g2048_state_text, "priorities": G2048_PRIORITIES, "points": g2048_points},
}
