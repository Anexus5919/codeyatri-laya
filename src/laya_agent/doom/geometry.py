"""Map geometry for the Doom facts: straight-line rays against the level's walls, and a memory of visited ground.

Everything here reads the engine's own map data one step at a time. A ray goes in one straight line and stops at
the first thing that blocks a player; nothing searches for a path or looks ahead in time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

PLAYER_HEIGHT = 56.0  # Doom: an opening must be at least this tall to walk through
MAX_STEP = 24.0       # Doom: the highest step a player can climb
USE_RANGE = 64.0      # Doom: how far the use key reaches
PLAYER_RADIUS = 16.0

WALL, DOOR, LEDGE = 0, 1, 2
KIND_NAMES = {WALL: "wall", DOOR: "door", LEDGE: "ledge"}


@dataclass(frozen=True)
class Hit:
    dist: float  # distance to the first blocking line, capped at the ray length
    kind: str    # wall | door | ledge | open (nothing within the ray length)


def unit(angle_deg: float) -> tuple[float, float]:
    a = math.radians(angle_deg)
    return math.cos(a), math.sin(a)


def bearing(px: float, py: float, angle_deg: float, x: float, y: float) -> float:
    """Degrees from the facing direction to a point; positive is to the left (Doom angles turn anticlockwise)."""
    return (math.degrees(math.atan2(y - py, x - px)) - angle_deg + 540.0) % 360.0 - 180.0


class LevelGeometry:
    """The blocking lines of the level as it is now (doors open and close, so it is rebuilt from each state)."""

    def __init__(self, segments: np.ndarray, kinds: np.ndarray, high: np.ndarray | None = None):
        self.seg = segments  # (n, 4): x1, y1, x2, y2
        self.kinds = kinds   # (n,): WALL | DOOR | LEDGE
        self.high = high if high is not None else np.zeros(len(kinds))  # LEDGE: the higher floor of the two sides

    @classmethod
    def from_sectors(cls, sectors) -> "LevelGeometry":
        sides: dict[tuple, list] = {}
        for s in sectors:
            for ln in s.lines:
                a, b = (round(ln.x1, 1), round(ln.y1, 1)), (round(ln.x2, 1), round(ln.y2, 1))
                key = (a, b) if a <= b else (b, a)
                sides.setdefault(key, []).append((s.floor_height, s.ceiling_height, bool(ln.is_blocking)))
        segs, kinds, high = [], [], []
        for (a, b), owners in sides.items():
            kind, top = None, 0.0
            if len(owners) == 1 or any(o[2] for o in owners):
                kind = WALL
            else:
                (f1, c1, _), (f2, c2, _) = owners[0], owners[1]
                if min(c1, c2) - max(f1, f2) < PLAYER_HEIGHT:
                    kind = DOOR if (c1 - f1 < 1.0 or c2 - f2 < 1.0) else WALL
                elif abs(f1 - f2) > MAX_STEP:
                    kind, top = LEDGE, max(f1, f2)
            if kind is not None:
                segs.append((a[0], a[1], b[0], b[1]))
                kinds.append(kind)
                high.append(top)
        if not segs:
            return cls(np.zeros((0, 4)), np.zeros(0, dtype=int))
        return cls(np.asarray(segs, dtype=float), np.asarray(kinds, dtype=int), np.asarray(high, dtype=float))

    def cast(self, x: float, y: float, angle_deg: float, length: float = 1024.0, z: float | None = None) -> Hit:
        """Distance along one straight line to the first line a player cannot cross. With the player's floor
        height z, a step blocks only when it rises more than MAX_STEP above it (stepping down is always allowed)."""
        if not len(self.seg):
            return Hit(length, "open")
        dx, dy = unit(angle_deg)
        ax, ay, bx, by = self.seg[:, 0], self.seg[:, 1], self.seg[:, 2], self.seg[:, 3]
        sx, sy = bx - ax, by - ay
        denom = dx * sy - dy * sx
        qx, qy = ax - x, ay - y
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (qx * sy - qy * sx) / denom
            u = (qx * dy - qy * dx) / denom
        ok = (np.abs(denom) > 1e-9) & (t > 1e-6) & (u >= 0.0) & (u <= 1.0) & (t <= length)
        if z is not None:
            ok &= ~((self.kinds == LEDGE) & (self.high <= z + MAX_STEP))
        if not ok.any():
            return Hit(length, "open")
        i = int(np.argmin(np.where(ok, t, np.inf)))
        return Hit(float(t[i]), KIND_NAMES[int(self.kinds[i])])


class Explored:
    """Which parts of the map the player has stood in, on a coarse grid. A memory, not a plan."""

    def __init__(self, cell: float = 128.0):
        self.cell = cell
        self.seen: set[tuple[int, int]] = set()

    def _cell(self, x: float, y: float) -> tuple[int, int]:
        return int(math.floor(x / self.cell)), int(math.floor(y / self.cell))

    def mark(self, x: float, y: float, around: float = 48.0) -> None:
        """Marks the ground the player stands on (and sees at arm's length) as visited."""
        for ox in (-around, 0.0, around):
            for oy in (-around, 0.0, around):
                self.seen.add(self._cell(x + ox, y + oy))

    def new_cells_along(self, x: float, y: float, angle_deg: float, open_dist: float,
                        step: float = 48.0, reach: float = 512.0, start: float = 96.0) -> int:
        """How many not-yet-visited cells lie on the open part of one straight line from the player."""
        dx, dy = unit(angle_deg)
        stop = min(open_dist - PLAYER_RADIUS, reach)
        cells, d = set(), start
        while d <= stop:
            c = self._cell(x + dx * d, y + dy * d)
            if c not in self.seen:
                cells.add(c)
            d += step
        return len(cells)
