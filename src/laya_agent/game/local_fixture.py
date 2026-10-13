"""LOCAL TEST FIXTURE ONLY. A tiny coin-collecting grid game for offline testing.

This is not one of the hosted hackathon games and its scores are never verified results.
Every log event from it carries env=LOCAL_FIXTURE. It exists so the loop, logging, viewer
and question designs can be exercised against real Laya before the official APIs exist.
"""

from __future__ import annotations

import random
from collections import deque
from typing import Any

from ..contracts import Candidate, Decision, Observation, StateValidationError, SubmitResult
from ..telemetry.events import ENV_LOCAL_FIXTURE
from .base import GameAdapter, GameClient

MOVES = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


class CoinGrid:
    """Deterministic for a given seed. Walls block movement; reaching the coin scores 1."""

    def __init__(self, width: int = 7, height: int = 7, walls: int = 6, max_steps: int = 40, seed: int = 0) -> None:
        self.w, self.h, self.max_steps = width, height, max_steps
        self.rng = random.Random(seed)
        self.seed = seed
        cells = [(x, y) for x in range(width) for y in range(height)]
        self.rng.shuffle(cells)
        self.player = cells.pop()
        self.walls = set(cells[:walls])
        self.free = [c for c in cells[walls:]]
        self.coin = self._new_coin()
        self.turn = 0
        self.score = 0

    def _new_coin(self) -> tuple[int, int]:
        options = [c for c in self.free if c != self.player and self._reachable(self.player, c)]
        return self.rng.choice(options)

    def _reachable(self, a: tuple[int, int], b: tuple[int, int]) -> bool:
        return bfs_distance(a, b, self.w, self.h, self.walls) is not None

    def legal(self) -> list[str]:
        out = []
        for name, (dx, dy) in MOVES.items():
            nx, ny = self.player[0] + dx, self.player[1] + dy
            if 0 <= nx < self.w and 0 <= ny < self.h and (nx, ny) not in self.walls:
                out.append(name)
        return out

    @property
    def done(self) -> bool:
        return self.turn >= self.max_steps

    def state(self) -> dict[str, Any]:
        return {
            "fixture": "coin-grid",
            "seed": self.seed,
            "turn": self.turn,
            "done": self.done,
            "score": self.score,
            "width": self.w,
            "height": self.h,
            "player": list(self.player),
            "coin": list(self.coin),
            "walls": sorted(list(w) for w in self.walls),
            "steps_left": self.max_steps - self.turn,
            "legal_actions": [] if self.done else self.legal(),
        }

    def step(self, action: str, turn: int) -> dict[str, Any]:
        if self.done:
            return {"ok": False, "error": "game over"}
        if turn != self.turn:
            return {"ok": False, "error": f"stale turn {turn}, current {self.turn}"}
        if action not in self.legal():
            return {"ok": False, "error": f"illegal action {action}"}
        dx, dy = MOVES[action]
        self.player = (self.player[0] + dx, self.player[1] + dy)
        self.turn += 1
        if self.player == self.coin:
            self.score += 1
            self.free = [c for c in self.free]
            self.coin = self._new_coin()
        return {"ok": True, "state": self.state()}


def bfs_distance(a, b, w, h, walls) -> int | None:
    a, b = tuple(a), tuple(b)
    if a == b:
        return 0
    seen = {a}
    q = deque([(a, 0)])
    while q:
        (x, y), d = q.popleft()
        for dx, dy in MOVES.values():
            n = (x + dx, y + dy)
            if n == b:
                return d + 1
            if 0 <= n[0] < w and 0 <= n[1] < h and n not in walls and n not in seen:
                seen.add(n)
                q.append((n, d + 1))
    return None


class LocalFixtureClient(GameClient):
    env = ENV_LOCAL_FIXTURE

    def __init__(self, seed: int = 0, **kwargs: Any) -> None:
        self.seed = seed
        self.kwargs = kwargs
        self.game = CoinGrid(seed=seed, **kwargs)

    def start(self) -> Any:
        self.game = CoinGrid(seed=self.seed, **self.kwargs)
        return self.game.state()

    def get_state(self) -> Any:
        return self.game.state()

    def submit(self, candidate: Candidate, decision: Decision, observation: Observation) -> SubmitResult:
        result = self.game.step(candidate.payload["action"], candidate.payload["turn"])
        if result["ok"]:
            return SubmitResult("accepted", response={"ok": True}, new_raw_state=result["state"])
        return SubmitResult("rejected", response=result, detail=result["error"])

    def reconcile(self, observation: Observation, decision: Decision) -> str:
        return "applied" if self.game.turn != observation.turn_id else "not_applied"

    def session_info(self) -> dict[str, Any]:
        return {"session_id": f"fixture-seed-{self.seed}", "verified": False}


class CoinGridAdapter(GameAdapter):
    game_id = "fixture-coin-grid"
    objective = "Collect as many coins as possible before the steps run out."
    priorities = (
        "Collecting the coin is best; otherwise prefer a move that gets closer to the coin "
        "and avoid a move that gets farther from it."
    )

    REQUIRED = ("turn", "done", "score", "width", "height", "player", "coin", "walls", "legal_actions", "steps_left")

    def __init__(self, style: str = "words") -> None:
        # "words" states the effect ("closer to the coin"); "numeric" gives only the distances.
        if style not in ("words", "numeric"):
            raise ValueError(f"unknown description style {style!r}")
        self.style = style

    def observe(self, raw: Any) -> Observation:
        if not isinstance(raw, dict):
            raise StateValidationError("state is not an object")
        missing = [k for k in self.REQUIRED if k not in raw]
        if missing:
            raise StateValidationError(f"missing fields: {missing}")
        w, h = raw["width"], raw["height"]
        px, py = raw["player"]
        walls = {tuple(x) for x in raw["walls"]}
        if not (0 <= px < w and 0 <= py < h):
            raise StateValidationError("player outside the board")
        for a in raw["legal_actions"]:
            if a not in MOVES:
                raise StateValidationError(f"unknown action {a!r}")

        coin = tuple(raw["coin"])
        here = bfs_distance((px, py), coin, w, h, walls)
        candidates = []
        for action in raw["legal_actions"]:
            dx, dy = MOVES[action]
            nxt = (px + dx, py + dy)
            after = bfs_distance(nxt, coin, w, h, walls)
            facts = {"to": list(nxt), "coin_distance_before": here, "coin_distance_after": after}
            if after == 0:
                trend = "collects the coin"
            elif here is None or after is None:
                trend = "coin not reachable"
            elif after < here:
                trend = f"closer to the coin ({here} to {after} steps)"
            elif after > here:
                trend = f"farther from the coin ({here} to {after} steps)"
            else:
                trend = f"same distance to the coin ({here} steps)"
            facts["trend"] = trend
            candidates.append(
                Candidate(
                    action_id=action,
                    payload={"action": action, "turn": raw["turn"]},
                    description=f"move {action}: {trend}" if self.style == "words" else f"move {action}: coin distance {here} to {after} steps",
                    facts=facts,
                )
            )

        state_text = (
            f"Coin grid {w}x{h}. Player at {px},{py}. Coin at {coin[0]},{coin[1]}. "
            f"Shortest path to coin: {here} steps. Score {raw['score']}. Steps left {raw['steps_left']}."
        )
        obs = Observation(
            game_id=self.game_id,
            session_id=None,
            turn_id=raw["turn"],
            terminal=bool(raw["done"]),
            score=float(raw["score"]),
            objective=self.objective,
            state_text=state_text,
            candidates=tuple(candidates),
            raw=raw,
            priorities=self.priorities,
        )
        obs.check_candidates()
        return obs
