"""LOCAL TEST SIMULATORS of the topgameai arena (Snake and 2048), never used for real runs.

They return the same JSON shapes as the real API (captured 2026-10-16), so the runner, facts,
logging and viewer can be tested offline. Scores here are never reported as results.
"""

from __future__ import annotations

import copy
from collections import deque
import math
import random
import uuid
from typing import Any

DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}


class SnakeSim:
    """Arena rules: 12x12, start length 3 heading right, win at 15 foods, cap 300 moves."""

    WIN_FOODS, MAX_STEPS = 15, 300

    def __init__(self, seed: int | None = None, width: int = 12, height: int = 12, tail_moves_first: bool = True) -> None:
        self.rng = random.Random(seed)
        self.w, self.h = width, height
        self.tail_moves_first = tail_moves_first
        self.snake = [(6, 6), (5, 6), (4, 6)]
        self.direction = "right"
        self.food_eaten = 0
        self.steps = 0
        self.done = False
        self.won = False
        self.food = self._place_food()

    def _place_food(self) -> tuple[int, int] | None:
        free = [(x, y) for y in range(self.h) for x in range(self.w) if (x, y) not in self.snake]
        return self.rng.choice(free) if free else None

    def state(self) -> dict:
        grid = [[0] * self.w for _ in range(self.h)]
        for x, y in self.snake[1:]:
            grid[y][x] = 1
        if self.food:
            grid[self.food[1]][self.food[0]] = 2
        hx, hy = self.snake[0]
        if 0 <= hx < self.w and 0 <= hy < self.h:
            grid[hy][hx] = 3
        return {
            "grid": grid,
            "snake": [{"x": x, "y": y} for x, y in self.snake],
            "food": {"x": self.food[0], "y": self.food[1]} if self.food else None,
            "direction": self.direction,
            "foodEaten": self.food_eaten,
            "width": self.w,
            "height": self.h,
        }

    def score(self) -> int:
        return min(1000, self.food_eaten * 60 + (100 if self.won else 0))

    def act(self, action: str) -> dict | None:
        """Returns an error dict for a rejected move, else None."""
        if self.done:
            return {"error": "Game is over"}
        if action not in DIRS:
            return {"error": f"Invalid action: {action}"}
        if action == OPPOSITE[self.direction]:
            return {"error": "Cannot reverse direction"}
        dx, dy = DIRS[action]
        hx, hy = self.snake[0]
        nx, ny = hx + dx, hy + dy
        self.direction = action
        self.steps += 1
        eats = (nx, ny) == self.food
        body = self.snake if (eats or not self.tail_moves_first) else self.snake[:-1]
        if not (0 <= nx < self.w and 0 <= ny < self.h) or (nx, ny) in body:
            self.snake = [(nx, ny)] + self.snake[:-1]
            self.done = True
            return None
        self.snake = [(nx, ny)] + (self.snake if eats else self.snake[:-1])
        if eats:
            self.food_eaten += 1
            if self.food_eaten >= self.WIN_FOODS:
                self.done = self.won = True
            else:
                self.food = self._place_food()
        if self.steps >= self.MAX_STEPS:
            self.done = True
        return None


def slide_line(line: list[int]) -> tuple[list[int], int, int]:
    """Slides one row towards index 0. Returns (new_line, points, merges)."""
    tiles = [v for v in line if v]
    out, pts, merges, i = [], 0, 0, 0
    while i < len(tiles):
        if i + 1 < len(tiles) and tiles[i] == tiles[i + 1]:
            out.append(tiles[i] * 2)
            pts += tiles[i] * 2
            merges += 1
            i += 2
        else:
            out.append(tiles[i])
            i += 1
    return out + [0] * (len(line) - len(out)), pts, merges


def slide_board(grid: list[list[int]], action: str) -> tuple[list[list[int]], int, int]:
    """Applies one 2048 move without spawning. Returns (new_grid, points, merges)."""
    n = len(grid)
    g = [row[:] for row in grid]
    pts = merges = 0
    for i in range(n):
        if action in ("left", "right"):
            line = g[i][:] if action == "left" else g[i][::-1]
        else:
            col = [g[r][i] for r in range(n)]
            line = col if action == "up" else col[::-1]
        new, p, m = slide_line(line)
        pts, merges = pts + p, merges + m
        if action == "right" or action == "down":
            new = new[::-1]
        if action in ("left", "right"):
            g[i] = new
        else:
            for r in range(n):
                g[r][i] = new[r]
    return g, pts, merges


class Sim2048:
    MAX_STEPS = 2000

    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)
        self.grid = [[0] * 4 for _ in range(4)]
        self.score_in_game = 0
        self.steps = 0
        self.done = False
        self.won = False
        self._spawn()
        self._spawn()

    def _spawn(self) -> None:
        free = [(r, c) for r in range(4) for c in range(4) if not self.grid[r][c]]
        if free:
            r, c = self.rng.choice(free)
            self.grid[r][c] = 4 if self.rng.random() < 0.1 else 2

    @property
    def best(self) -> int:
        return max(max(row) for row in self.grid)

    def state(self) -> dict:
        return {"grid": copy.deepcopy(self.grid), "score": self.score_in_game, "best": self.best}

    def score(self) -> int:
        return min(1000, int(max(0, math.log2(self.best) - 6) * 143 + self.score_in_game // 1000))

    def _any_move(self) -> bool:
        return any(slide_board(self.grid, a)[0] != self.grid for a in DIRS)

    def act(self, action: str) -> dict | None:
        if self.done:
            return {"error": "Game is over"}
        if action not in DIRS:
            return {"error": f"Invalid action: {action}"}
        new, pts, _ = slide_board(self.grid, action)
        if new == self.grid:
            return {"error": "Move does not change the board"}
        self.grid = new
        self.score_in_game += pts
        self.steps += 1
        if self.best >= 2048:
            self.won = True
        self._spawn()
        if self.steps >= self.MAX_STEPS or not self._any_move():
            self.done = True
        return None


class GridSim:
    """LOCAL TEST SIMULATOR of an unseen grid game (stage-3 rehearsal): walls, static enemies, hazards, one exit.
    Entering a wall is rejected; entering a hazard or an enemy cell ends the game; reaching the exit wins.
    State uses field names the bot has never seen, so only a JSON mapping can describe it."""

    MAX_STEPS = 200

    def __init__(self, seed: int | None = None, width: int = 10, height: int = 8) -> None:
        self.rng = random.Random(seed)
        self.w, self.h = width, height
        cells = [(x, y) for x in range(width) for y in range(height)]
        self.rng.shuffle(cells)
        self.player = cells.pop()
        self.exit = cells.pop()
        self.walls = set(cells[:14])
        self.enemies = set(cells[14:18])
        self.pits = set(cells[18:21])
        self.steps = 0
        self.done = self.won = False
        self.health = 100
        if self._dist(self.player, self.exit) is None:
            self.walls = set()

    def _dist(self, a, b):
        blocked = self.walls | self.enemies | self.pits
        seen, q = {a}, deque([(a, 0)])
        while q:
            (x, y), d = q.popleft()
            if (x, y) == b:
                return d
            for dx, dy in DIRS.values():
                n = (x + dx, y + dy)
                if 0 <= n[0] < self.w and 0 <= n[1] < self.h and n not in blocked and n not in seen:
                    seen.add(n)
                    q.append((n, d + 1))
        return None

    def state(self) -> dict:
        tiles = [[0] * self.w for _ in range(self.h)]
        for x, y in self.walls:
            tiles[y][x] = 1
        for x, y in self.pits:
            tiles[y][x] = 4
        for x, y in self.enemies:
            tiles[y][x] = 3
        tiles[self.exit[1]][self.exit[0]] = 2
        return {"tiles": tiles, "hero": {"col": self.player[0], "row": self.player[1]}, "hp": self.health,
                "monsters": [{"col": x, "row": y} for x, y in sorted(self.enemies)],
                "exit": {"col": self.exit[0], "row": self.exit[1]}, "cols": self.w, "rows": self.h, "turn": self.steps}

    def score(self) -> int:
        return (1000 - 5 * self.steps) if self.won else 0

    def act(self, action: str) -> dict | None:
        if self.done:
            return {"error": "Game is over"}
        if action not in DIRS:
            return {"error": f"Invalid action: {action}"}
        dx, dy = DIRS[action]
        n = (self.player[0] + dx, self.player[1] + dy)
        if not (0 <= n[0] < self.w and 0 <= n[1] < self.h) or n in self.walls:
            return {"error": "Blocked"}
        self.steps += 1
        self.player = n
        if n in self.pits or n in self.enemies:
            self.health = 0
            self.done = True
        elif n == self.exit:
            self.done = self.won = True
        elif self.steps >= self.MAX_STEPS:
            self.done = True
        return None


class FakeArena:
    """In-process stand-in for https://topgameai.com/api/arena with the same request/response shapes."""

    env = "LOCAL_SIM"

    def __init__(self, seed: int | None = None, **snake_kwargs: Any) -> None:
        self.seed = seed
        self.snake_kwargs = snake_kwargs
        self.sessions: dict[str, Any] = {}

    def _response(self, sid: str, game: str, sim: Any, message: str | None = None) -> dict:
        out = {"session_id": sid, "game": game, "state": sim.state(), "done": sim.done, "won": sim.won,
               "score": sim.score(), "steps": sim.steps}
        if message:
            out["message"] = message
        return out

    def create(self, game: str, agent_name: str) -> tuple[int, dict]:
        sid = str(uuid.uuid4())  # unique per run even for a fixed seed: a session log is never rewritten
        sims = {"snake": lambda: SnakeSim(self.seed, **self.snake_kwargs), "2048": lambda: Sim2048(self.seed)}
        sim = sims[game]() if game in sims else GridSim(self.seed)
        self.sessions[sid] = (game, sim)
        msg = "Eat 15 foods. Actions: up | down | left | right" if game == "snake" else None
        return 201, self._response(sid, game, sim, msg)

    def act(self, sid: str, action: str) -> tuple[int, dict]:
        game, sim = self.sessions[sid]
        err = sim.act(action)
        if err:
            return 400, err
        return 200, self._response(sid, game, sim)

    def get(self, sid: str) -> tuple[int, dict]:
        game, sim = self.sessions[sid]
        return 200, self._response(sid, game, sim)
