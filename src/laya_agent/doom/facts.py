"""One-step facts for each Doom action, written from the engine's own state, and the fixed priority reader.

Laya gets one yes/no question per offered action: the shared priorities plus one sentence saying what that action
does right now (the shot hits the Imp or hits nothing, the turn brings the Imp into the crosshair, the move is
blocked by a wall or leads into unexplored ground, the strafe steps out of a fireball's path). Each fact is a
reading of the current state and one action: no path search, no lookahead over several actions.

The priority reader turns the same facts into training labels (and plays offline games to collect training
states). It is a fixed ranking of the facts, written down below; it never plays a counted game.
"""

from __future__ import annotations

import math
import re
from collections import deque
from dataclasses import dataclass, field

from .engine import ACTIONS, TURN_BIG, TURN_SMALL, Observation
from .geometry import USE_RANGE, Explored, Hit, LevelGeometry, bearing, unit

PRIORITIES = ("Doom priorities: shoot an enemy that is in the crosshair, turn to bring the nearest enemy into the "
              "crosshair, dodge incoming fireballs, never waste ammunition, open doors, explore new areas, pick up "
              "health when hurt.")
TEMPLATE = "{priorities} Is this a good action now? This action: {fact}"
CRITERIA = {"true": "a good action for these priorities", "false": "a poor action for these priorities"}

MOVE_STEP = 40.0          # about how far one running action carries the player
BLOCKED = 40.0            # a blocker closer than this means the move barely goes anywhere
NEAR_UNSEEN = 384.0       # enemies out of view are mentioned only this close and in a clear straight line
ITEM_RANGE = 640.0
LOW_HEALTH = 60
CLOSE = 160.0             # an enemy this close is shot while backing away
STILL_DIST = 24.0
STILL_WINDOW = 8

WEAPONS = {0: "fist", 1: "fist", 2: "pistol", 3: "shotgun", 4: "chaingun", 5: "rocket launcher",
           6: "plasma rifle", 7: "BFG"}
MONSTERS = {"ZombieMan": "Zombieman", "Zombieman": "Zombieman", "ShotgunGuy": "shotgun guy",
            "ChaingunGuy": "chaingun guy", "DoomImp": "Imp", "Demon": "Demon", "Spectre": "Spectre",
            "LostSoul": "lost soul", "Cacodemon": "Cacodemon", "HellKnight": "Hell knight",
            "BaronOfHell": "Baron of Hell", "Arachnotron": "Arachnotron", "PainElemental": "pain elemental",
            "Revenant": "Revenant", "Fatso": "Mancubus", "Archvile": "Arch-vile", "Cyberdemon": "Cyberdemon",
            "SpiderMastermind": "Spider Mastermind", "WolfensteinSS": "SS guard",
            "MarineChainsawVzd": "chainsaw marine"}
# Doom's collision radius per monster: a hitscan shot hits when it passes within this distance of the centre
RADIUS = {"ZombieMan": 20, "Zombieman": 20, "ShotgunGuy": 20, "ChaingunGuy": 20, "DoomImp": 20, "Demon": 30,
          "Spectre": 30, "LostSoul": 16, "Cacodemon": 31, "HellKnight": 24, "BaronOfHell": 24, "Arachnotron": 64,
          "PainElemental": 31, "Revenant": 20, "Fatso": 48, "Archvile": 20, "Cyberdemon": 40,
          "SpiderMastermind": 128, "WolfensteinSS": 20, "MarineChainsawVzd": 16}
ITEM_CATEGORIES = ("Health", "Armor", "Ammo", "Weapon", "Key", "Powerup")
MISSILE_IGNORE = ("BulletPuff",)
SIDE_ANGLE = {"forward": 0.0, "backward": 180.0, "strafe_left": 90.0, "strafe_right": -90.0}
TURNS = {"turn_left": TURN_SMALL, "turn_right": -TURN_SMALL, "turn_left_big": TURN_BIG, "turn_right_big": -TURN_BIG,
         "turn_around": 180.0}
SCAN = tuple(range(-150, 181, 30))  # straight lines every 30 degrees around the player, for unexplored ground


def pretty(name: str) -> str:
    if name in MONSTERS:
        return MONSTERS[name]
    return re.sub(r"(?<!^)(?=[A-Z])", " ", name).lower()


def where(b: float) -> str:
    if abs(b) <= 4:
        return "straight ahead"
    if abs(b) >= 135:
        return f"behind you on the {'left' if b > 0 else 'right'}"
    return f"{abs(round(b))} degrees {'left' if b > 0 else 'right'}"


@dataclass
class Enemy:
    id: int
    name: str
    dist: float
    bearing: float
    visible: bool
    in_crosshair: bool
    radius: float = 20.0

    @property
    def half(self) -> float:
        """Half the enemy's body as an angle: within this many degrees of the crosshair the shot hits."""
        return max(2.0, math.degrees(math.atan2(self.radius, max(self.dist, 1.0))))


@dataclass
class Item:
    name: str
    category: str
    dist: float
    bearing: float


@dataclass
class Missile:
    name: str
    dist: float
    dodge_side: str   # strafe_left | strafe_right: the side that moves away from its path


@dataclass
class Scene:
    x: float
    y: float
    angle: float
    health: int
    armor: int
    weapon: int
    ammo: int
    kills: int
    enemies: list[Enemy] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    missiles: list[Missile] = field(default_factory=list)
    rays: dict[str, Hit] = field(default_factory=dict)      # by action: what lies along its line
    new_cells: dict[str, int] = field(default_factory=dict)  # by action: unexplored cells along its line
    lost_health: int = 0
    still: bool = False
    last: str | None = None  # the action played just before this decision
    door_state: str = ""     # for the door straight ahead: "" | opening | stuck
    stalled: set = field(default_factory=set)  # moves tried just now that did not move the player
    frontier: float | None = None  # the direction (degrees, + is left) whose straight line holds the most new ground
    frontier_new: int = 0

    @property
    def target(self) -> Enemy | None:
        """The enemy closest to the crosshair: visible ones first, then near ones out of view."""
        seen = [e for e in self.enemies if e.visible]
        pool = seen or self.enemies
        return min(pool, key=lambda e: (abs(e.bearing), e.dist)) if pool else None

    @property
    def aimed(self) -> Enemy | None:
        hits = [e for e in self.enemies if e.in_crosshair]
        return min(hits, key=lambda e: e.dist) if hits else None

    @property
    def threat(self) -> Missile | None:
        return min(self.missiles, key=lambda m: m.dist) if self.missiles else None


@dataclass
class ActFact:
    action: str
    text: str
    offered: bool = True
    data: dict = field(default_factory=dict)


class Perceiver:
    """Builds a Scene from one observation, keeping the little memory the facts need (visited ground, last health,
    recent positions). Call reset() at the start of every episode."""

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.explored = Explored()
        self.last_health: float | None = None
        self.recent: deque = deque(maxlen=STILL_WINDOW)
        self.last_action: str | None = None
        self.tic = 0
        self.pos = (0.0, 0.0)
        self.door_ahead: tuple | None = None   # rounded point of the closed door straight ahead, if any
        self.opening: dict[tuple, int] = {}    # door point -> tic when use was pressed on it
        self.stuck_doors: set[tuple] = set()   # doors that stayed shut after use
        self.stalled: set[str] = set()
        self.stall_from = (0.0, 0.0)

    def note(self, action: str) -> None:
        """Records the action that was just played: the facts say when an action would undo it, when a door is
        already opening, and when a move just tried went nowhere."""
        self.last_action = action
        if action == "use" and self.door_ahead is not None:
            self.opening.setdefault(self.door_ahead, self.tic)
        self.stall_from = self.pos

    def scene(self, obs: Observation) -> Scene:
        v = obs.vars
        x, y, ang, z = v["POSITION_X"], v["POSITION_Y"], v["ANGLE"], v.get("POSITION_Z")
        geo = LevelGeometry.from_sectors(obs.sectors)
        self.explored.mark(x, y)
        lost = 0 if self.last_health is None else max(0, int(self.last_health - v["HEALTH"]))
        self.last_health = v["HEALTH"]
        self.recent.append((x, y))
        still = len(self.recent) == STILL_WINDOW and max(
            math.hypot(px - x, py - y) for px, py in self.recent) < STILL_DIST

        cx = obs.width / 2.0
        shown = {lb.object_id: lb for lb in obs.labels}
        enemies = []
        for o in obs.objects:
            if o.category != "Monster":
                continue
            d = math.hypot(o.position_x - x, o.position_y - y)
            b = bearing(x, y, ang, o.position_x, o.position_y)
            lb = shown.get(o.id)
            r = float(RADIUS.get(o.name, 20))
            if lb is not None:
                # On screen and covering the centre column, and close enough in angle for the body to be hit (a
                # monster right in front fills the screen even when the shot would pass beside it)
                on_body = abs(b) <= math.degrees(math.atan2(r, max(d, 1.0))) + 1.5
                enemies.append(Enemy(o.id, pretty(o.name), d, b, True, lb.x <= cx <= lb.x + lb.width and on_body, r))
            elif d <= NEAR_UNSEEN and geo.cast(x, y, ang + b, d, z).dist >= d - 24.0:
                enemies.append(Enemy(o.id, pretty(o.name), d, b, False, False, r))

        items = []
        for lb in obs.labels:
            if lb.object_category in ITEM_CATEGORIES:
                d = math.hypot(lb.object_position_x - x, lb.object_position_y - y)
                if d <= ITEM_RANGE:
                    items.append(Item(pretty(lb.object_name), lb.object_category, d,
                                      bearing(x, y, ang, lb.object_position_x, lb.object_position_y)))

        missiles = []
        lx, ly = unit(ang + 90.0)
        for o in obs.objects:
            if o.category != "Explosive" or o.name in MISSILE_IGNORE:
                continue
            vx, vy = o.velocity_x, o.velocity_y
            speed2 = vx * vx + vy * vy
            if speed2 < 4.0:
                continue
            wx, wy = x - o.position_x, y - o.position_y
            t = (wx * vx + wy * vy) / speed2
            if t <= 0:
                continue  # moving away from the player
            ox, oy = wx - t * vx, wy - t * vy  # from the closest point of its path to the player
            if math.hypot(ox, oy) > 48.0:
                continue  # it will miss anyway
            side = "strafe_left" if ox * lx + oy * ly >= 0 else "strafe_right"
            missiles.append(Missile(pretty(o.name), math.hypot(wx, wy), side))

        rays, new = {}, {}
        for act, off in list(SIDE_ANGLE.items()) + [("turn_left_big", TURN_BIG), ("turn_right_big", -TURN_BIG),
                                                    ("turn_left", TURN_SMALL), ("turn_right", -TURN_SMALL),
                                                    ("turn_around", 180.0)]:
            hit = geo.cast(x, y, ang + off, z=z)
            rays[act] = hit
            new[act] = self.explored.new_cells_along(x, y, ang + off, hit.dist)
        # Where the most unexplored ground lies along one straight line, looking all around (no path search)
        frontier, frontier_new = None, 0
        for off in SCAN:
            hit = geo.cast(x, y, ang + off, z=z)
            n = self.explored.new_cells_along(x, y, ang + off, hit.dist)
            if n > frontier_new or (n == frontier_new and n and abs(off) < abs(frontier)):
                frontier, frontier_new = float(off), n

        # Door memory: a door is "opening" for a while after use, and "stuck" if it is still shut after that
        fwd = rays["forward"]
        door_state = ""
        self.door_ahead = None
        if fwd.kind == "door" and fwd.dist <= USE_RANGE + 8:
            dx, dy = unit(ang)
            self.door_ahead = (round((x + dx * fwd.dist) / 32), round((y + dy * fwd.dist) / 32))
            pressed = self.opening.get(self.door_ahead)
            if self.door_ahead in self.stuck_doors:
                door_state = "stuck"
            elif pressed is not None and obs.tic - pressed < 105:
                door_state = "opening"
            elif pressed is not None:
                self.stuck_doors.add(self.door_ahead)
                door_state = "stuck"
        # A move just tried that left the player where they were is blocked by something the map lines miss
        moved = math.hypot(x - self.stall_from[0], y - self.stall_from[1])
        if self.last_action in SIDE_ANGLE and moved < 6.0:
            self.stalled.add(self.last_action)
        elif moved >= 16.0 or (self.last_action or "").startswith("turn"):
            self.stalled = set()
        self.tic, self.pos = obs.tic, (x, y)

        return Scene(x, y, ang, int(v["HEALTH"]), int(v["ARMOR"]), int(v["SELECTED_WEAPON"]),
                     int(v["SELECTED_WEAPON_AMMO"]), int(v["KILLCOUNT"]), enemies, items, missiles, rays, new,
                     lost, still, self.last_action, door_state, set(self.stalled), frontier, frontier_new)


OPPOSITE = {"turn_left": "turn_right", "turn_right": "turn_left", "turn_left_big": "turn_right_big",
            "turn_right_big": "turn_left_big", "turn_around": "turn_around", "forward": "backward", "backward": "forward",
            "strafe_left": "strafe_right", "strafe_right": "strafe_left"}


def state_text(s: Scene) -> str:
    gun = "no weapon" if s.weapon < 0 else WEAPONS.get(s.weapon, "weapon") + ("" if s.weapon <= 1 else f" with {s.ammo} rounds")
    parts = [f"Doom. Health {s.health}, armor {s.armor}, {gun}, {s.kills} kills."]
    seen = sorted((e for e in s.enemies if e.visible), key=lambda e: abs(e.bearing))[:3]
    unseen = sorted((e for e in s.enemies if not e.visible), key=lambda e: e.dist)[:2]
    parts.append("Enemies in view: " + ("; ".join(f"{e.name} {where(e.bearing)}, {round(e.dist)} units" for e in seen)
                                       if seen else "none") + ".")
    if unseen:
        parts.append("Near but out of view: " + "; ".join(f"{e.name} {where(e.bearing)}, {round(e.dist)} units"
                                                         for e in unseen) + ".")
    if s.threat:
        parts.append(f"A {s.threat.name} is flying at you, {round(s.threat.dist)} units away.")
    if s.lost_health:
        parts.append(f"You just lost {s.lost_health} health.")
    if s.still:
        parts.append(f"You have barely moved during the last {STILL_WINDOW} actions.")
    if s.frontier is not None and abs(s.frontier) > 30.0 and not seen:
        parts.append(f"Most unexplored ground: {where(s.frontier)}.")
    return " ".join(parts)


def _blocker(hit: Hit) -> str:
    return {"wall": "a wall", "door": "a closed door", "ledge": "a high step"}.get(hit.kind, "something")


def _faces(s: Scene, act: str) -> str:
    hit = s.rays[act]
    if hit.dist < BLOCKED * 2:
        return f"{_blocker(hit)} {round(hit.dist)} units away"
    room = f"open space {round(hit.dist)} units deep" if hit.kind != "open" else "open space more than 1000 units deep"
    n = s.new_cells.get(act, 0)
    return room + (f" leading into {n} unexplored areas" if n else ", already explored")


def _shoot(s: Scene) -> ActFact:
    w = WEAPONS.get(s.weapon, "weapon")
    e = s.aimed
    if s.weapon < 0:
        return ActFact("shoot", "pulls the trigger, but you carry no weapon here: nothing happens.", data={"hits": False})
    if s.weapon <= 1:
        if e and e.dist <= 64:
            return ActFact("shoot", f"swings the {w} at the {e.name} in the crosshair, {round(e.dist)} units away: it hits.",
                           data={"hits": True})
        why = f"the {e.name} in the crosshair is {round(e.dist)} units away, out of reach" if e else "no enemy is in reach"
        return ActFact("shoot", f"swings the {w}: {why}, so it hits nothing.", data={"hits": False})
    if s.ammo <= 0:
        return ActFact("shoot", f"pulls the trigger of the empty {w}: nothing fires.", data={"hits": False})
    if e:
        step = _step_away(s, e)
        how = {"backward": ", and you back away from it as you fire",
               "strafe_left": ", and with a wall behind you, you step left as you fire",
               "strafe_right": ", and with a wall behind you, you step right as you fire"}.get(step or "", "")
        return ActFact("shoot", f"fires the {w} at the {e.name} in the crosshair, {round(e.dist)} units away: the shot "
                                f"hits it{how}. {s.ammo} rounds left.", data={"hits": True, "back": step})
    return ActFact("shoot", f"fires the {w} with no enemy in the crosshair: the shot hits nothing and wastes a round. "
                            f"{s.ammo} rounds left.", data={"hits": False})


def _step_away(s: Scene, e: Enemy) -> str | None:
    """Where a shot at a close enemy steps while it fires: straight back, or with a wall behind, sideways onto open
    ground that holds no other enemy (a side-step keeps the crosshair on the target, a turn would not)."""
    if e.dist >= CLOSE:
        return None
    if s.rays["backward"].dist >= BLOCKED * 2:
        return "backward"

    def clear(act: str) -> bool:
        return s.rays[act].dist >= BLOCKED * 2 and not any(
            o is not e and o.dist < 300 and abs((o.bearing - SIDE_ANGLE[act] + 540.0) % 360.0 - 180.0) < 60.0
            for o in s.enemies)

    sides = [a for a in ("strafe_left", "strafe_right") if clear(a)]
    return max(sides, key=lambda a: s.rays[a].dist) if sides else None


def _toward_frontier(s: Scene, act: str) -> bool:
    """Whether this turn swings toward the most unexplored ground the all-round scan found."""
    f = s.frontier
    if f is None or abs(f) <= 30.0:
        return False
    return act in ("turn_left_big", "turn_right_big") and (f > 0) == (TURNS[act] > 0) and abs(f) < 135.0


def _turn(s: Scene, act: str) -> ActFact:
    deg = TURNS[act]
    side, size = ("left" if deg > 0 else "right"), abs(round(deg))
    head = "turns around" if abs(deg) >= 180 else f"turns {side} {size} degrees"
    e = s.target
    if e is None:
        if s.last == OPPOSITE.get(act):
            return ActFact(act, f"{head}, straight back to where you faced a moment ago, to face {_faces(s, act)}.",
                           data={"aim": None, "undo": True})
        if _toward_frontier(s, act):
            return ActFact(act, f"{head} to face {_faces(s, act)}, toward the most unexplored ground "
                                f"({where(s.frontier)}).", data={"aim": None, "frontier": True})
        return ActFact(act, f"{head} to face {_faces(s, act)}.", data={"aim": None})
    new = (e.bearing - deg + 540.0) % 360.0 - 180.0
    what = f"the {e.name}" + ("" if e.visible else " out of view")
    if abs(e.bearing) <= e.half:
        return ActFact(act, f"{head}: {what} now in the crosshair moves out of it, {abs(round(new))} degrees off.",
                       data={"aim": "loses", "new": abs(new)})
    if abs(new) <= e.half:
        return ActFact(act, f"{head}: puts {what}, {round(e.dist)} units away, in the crosshair.",
                       data={"aim": "on", "new": abs(new)})
    if abs(new) < abs(e.bearing):
        return ActFact(act, f"{head}: {what} comes closer to the crosshair, from {abs(round(e.bearing))} to "
                            f"{abs(round(new))} degrees off.", data={"aim": "closer", "new": abs(new)})
    return ActFact(act, f"{head}: {what} moves further from the crosshair, from {abs(round(e.bearing))} to "
                        f"{abs(round(new))} degrees off.", data={"aim": "further", "new": abs(new)})


def _move(s: Scene, act: str) -> ActFact:
    word = {"forward": "moves forward", "backward": "moves backward", "strafe_left": "steps left",
            "strafe_right": "steps right"}[act]
    hit = s.rays[act]
    if act == "forward" and s.door_state == "opening":
        return ActFact(act, f"{word}: walks up to the door ahead, which is opening and will be clear in a moment.",
                       data={"blocked": False, "new": 0, "door_wait": True})
    if act in s.stalled:
        return ActFact(act, f"{word}: you just tried this and did not move, something is in the way.",
                       data={"blocked": True, "new": 0})
    if hit.dist < BLOCKED:
        return ActFact(act, f"{word}: blocked by {_blocker(hit)} {round(hit.dist)} units away, so you barely move.",
                       data={"blocked": True, "new": 0})
    n = s.new_cells.get(act, 0)
    room = "more than 1000" if hit.kind == "open" else str(round(hit.dist))
    bits = [f"open for {room} units" + (f", into {n} unexplored areas" if n else ", over ground already explored")]
    data = {"blocked": False, "new": n}
    if s.last == OPPOSITE.get(act):
        bits.append("back where you just came from")
        data["undo"] = True
    m = s.threat
    if m and act in ("strafe_left", "strafe_right"):
        dodges = act == m.dodge_side
        bits.append(f"{'steps out of' if dodges else 'stays in'} the path of the incoming {m.name}")
        data["dodges"] = dodges
    e = s.target
    if e is not None:
        dx, dy = unit(s.angle + SIDE_ANGLE[act])
        ex = s.x + e.dist * math.cos(math.radians(s.angle + e.bearing))
        ey = s.y + e.dist * math.sin(math.radians(s.angle + e.bearing))
        after = math.hypot(ex - (s.x + dx * MOVE_STEP), ey - (s.y + dy * MOVE_STEP))
        bits.append(f"{'closer to' if after < e.dist else 'away from'} the {e.name} ({round(e.dist)} to {round(after)} units)")
        data["enemy_after"] = after
    for it in sorted(s.items, key=lambda i: i.dist):
        off = (it.bearing - SIDE_ANGLE[act] + 540.0) % 360.0 - 180.0
        if abs(off) <= 20 and it.dist < hit.dist:
            bits.append(f"toward the {it.name} {round(it.dist)} units away")
            data["item"] = it.category
            break
    return ActFact(act, f"{word}: " + ", ".join(bits) + ".", data=data)


def _use(s: Scene) -> ActFact:
    hit = s.rays["forward"]
    if hit.kind == "door" and hit.dist <= USE_RANGE + 8:
        if s.door_state == "opening":
            return ActFact("use", "presses use on the door ahead that is already opening, which would close it again.",
                           data={"door": False})
        if s.door_state == "stuck":
            return ActFact("use", "presses use on the door ahead, which stayed shut when you tried before; it may need "
                                  "a key or a switch.", data={"door": False})
        return ActFact("use", f"opens the closed door directly ahead, {round(hit.dist)} units away.", data={"door": True})
    return ActFact("use", "presses use, but nothing usable is within reach.", offered=False, data={"door": False})


def backs(fs: dict[str, ActFact], action: str) -> str | None:
    """The move a shot makes while it fires (an enemy close in front): backward, strafe_left, strafe_right or None."""
    return fs["shoot"].data.get("back") if action == "shoot" else None


def facts(s: Scene) -> dict[str, ActFact]:
    out = {"shoot": _shoot(s)}
    for act in TURNS:
        out[act] = _turn(s, act)
    for act in SIDE_ANGLE:
        out[act] = _move(s, act)
    out["use"] = _use(s)
    return {a: out[a] for a in ACTIONS}


def reader_scores(s: Scene, fs: dict[str, ActFact]) -> dict[str, float]:
    """The fixed priority reading of the facts that labels training data. Higher is better; it reads only the
    facts above (one action, one step), in the order the priorities state them."""
    sc = {a: 0.0 for a in fs if fs[a].offered}
    m, e = s.threat, s.target
    if fs["shoot"].data.get("hits"):
        sc["shoot"] = 90.0
    if m is not None and m.dist < 256:
        sc[m.dodge_side] = max(sc.get(m.dodge_side, 0.0), 95.0 if not fs[m.dodge_side].data.get("blocked") else 0.0)
    if e is not None and not fs["shoot"].data.get("hits"):
        for act in TURNS:
            d = fs[act].data
            if d.get("aim") == "on":
                sc[act] = max(sc[act], 80.0 - d["new"] * 0.1)
            elif d.get("aim") == "closer":
                sc[act] = max(sc[act], 70.0 - d["new"] * 0.1)
    if "use" in sc and fs["use"].data.get("door"):
        sc["use"] = max(sc["use"], 60.0)
    if fs["forward"].data.get("door_wait"):
        sc["forward"] = max(sc["forward"], 58.0)
    for act in SIDE_ANGLE:
        d = fs[act].data
        if d.get("item") and not d.get("blocked"):
            if d["item"] == "Health" and s.health < LOW_HEALTH:
                sc[act] = max(sc[act], 55.0)
            elif e is None or not e.visible:
                sc[act] = max(sc[act], 50.0 if d["item"] != "Health" or s.health < 100 else 0.0)
    if e is not None and e.visible and not fs["forward"].data.get("blocked"):
        sc["forward"] = max(sc["forward"], 15.0)  # close in on a visible enemy that the turns cannot line up yet
    if e is None or not e.visible:
        # Exploring: forward into new ground first, then turning toward new ground; backing up comes last
        first = {"forward": (40.0, 20.0), "strafe_left": (25.0, 4.0), "strafe_right": (25.0, 4.0),
                 "backward": (12.0, 2.0)}
        for act, (new_base, old_base) in first.items():
            d = fs[act].data
            if not d.get("blocked"):
                sc[act] = max(sc[act], new_base + min(d["new"], 9) * (1.0 if act != "backward" else 0.5)
                              if d["new"] else old_base)
        # Turning around is for facing an enemy behind; exploring sweeps 30 degrees at a time, because walking back
        # the way you came (turn around, forward, turn around) goes nowhere
        for act in ("turn_left_big", "turn_right_big"):
            hit, n = s.rays[act], s.new_cells.get(act, 0)
            if hit.dist >= BLOCKED * 2 and n:
                sc[act] = max(sc[act], 35.0 + min(n, 9) + (30.0 if s.still else 0.0))
            elif fs[act].data.get("frontier"):  # nothing new within 30 degrees: swing toward the new ground
                sc[act] = max(sc[act], 33.0)
            else:  # nothing new in reach: look around, preferring the longest open line
                sc[act] = max(sc[act], 5.0 + min(hit.dist, 1000.0) / 200.0)
        if s.still and not fs["forward"].data.get("blocked"):
            sc["forward"] = max(sc["forward"], 50.0 + min(fs["forward"].data.get("new", 0), 9))  # stuck: get moving
        if fs["forward"].data.get("blocked") and max(sc.values()) <= 0.0:
            sc["turn_left_big"] = 1.0  # boxed in: turn and look again
    for act, f in fs.items():
        if f.data.get("undo") and act in sc and not f.data.get("dodges"):
            sc[act] = min(sc[act], 3.0)  # undoing the last action goes nowhere
    return sc


TIE_ORDER = ("forward", "turn_left_big", "turn_right_big", "turn_left", "turn_right", "turn_around", "strafe_left",
             "strafe_right", "use", "backward", "shoot")  # on a tie, never fire blind


def reader_choice(sc: dict[str, float]) -> str:
    return max(sc, key=lambda a: (sc[a], -TIE_ORDER.index(a)))


def questions(fs: dict[str, ActFact]) -> dict[str, str]:
    return {a: TEMPLATE.format(priorities=PRIORITIES, fact=f.text) for a, f in fs.items() if f.offered}
