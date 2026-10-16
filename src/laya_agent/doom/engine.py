"""The Doom engine (ViZDoom, free Freedoom game data) behind a small interface.

One decision picks one of a fixed set of actions; the action's buttons are held for HOLD_TICS game tics. In
real-time mode (async) the game keeps running at 35 tics a second while Laya thinks, and the buttons are released
after each action so an old action never keeps running. Every episode can be recorded as a Doom demo (.lmp), which
the engine replays exactly; that recording is the proof of what was played.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import vizdoom as vzd

B = vzd.Button
GV = vzd.GameVariable

ACTIONS = ("shoot", "turn_left", "turn_right", "turn_left_big", "turn_right_big",
           "forward", "backward", "strafe_left", "strafe_right", "use")
TURN_SMALL = 5.0   # fine aim: an enemy 400 units away is about 5 degrees wide
TURN_BIG = 30.0
HOLD_TICS = 4
START_TICS = 6  # the engine ignores input for the first few tics of an episode

BUTTONS = [B.ATTACK, B.USE, B.MOVE_FORWARD, B.MOVE_BACKWARD, B.MOVE_LEFT, B.MOVE_RIGHT, B.SPEED,
           B.TURN_LEFT_RIGHT_DELTA]
_IDX = {b: i for i, b in enumerate(BUTTONS)}


def _vec(**pressed) -> list[float]:
    v = [0.0] * len(BUTTONS)
    for name, value in pressed.items():
        v[_IDX[getattr(B, name)]] = float(value)
    return v


# A positive TURN_LEFT_RIGHT_DELTA turns right, applied once per tic
ACTION_BUTTONS = {
    "shoot": _vec(ATTACK=1),
    "turn_left": _vec(TURN_LEFT_RIGHT_DELTA=-TURN_SMALL / HOLD_TICS),
    "turn_right": _vec(TURN_LEFT_RIGHT_DELTA=TURN_SMALL / HOLD_TICS),
    "turn_left_big": _vec(TURN_LEFT_RIGHT_DELTA=-TURN_BIG / HOLD_TICS),
    "turn_right_big": _vec(TURN_LEFT_RIGHT_DELTA=TURN_BIG / HOLD_TICS),
    "forward": _vec(MOVE_FORWARD=1, SPEED=1),
    "backward": _vec(MOVE_BACKWARD=1, SPEED=1),
    "strafe_left": _vec(MOVE_LEFT=1, SPEED=1),
    "strafe_right": _vec(MOVE_RIGHT=1, SPEED=1),
    "use": _vec(USE=1),
}
RELEASE = [0.0] * len(BUTTONS)

VARIABLES = [GV.HEALTH, GV.ARMOR, GV.SELECTED_WEAPON, GV.SELECTED_WEAPON_AMMO, GV.KILLCOUNT, GV.ITEMCOUNT,
             GV.SECRETCOUNT, GV.DAMAGECOUNT, GV.DAMAGE_TAKEN, GV.HITCOUNT, GV.DEAD, GV.POSITION_X, GV.POSITION_Y,
             GV.POSITION_Z, GV.ANGLE]

# Scenario names are either a ViZDoom scenario (defend_the_center, deathmatch, ...) or "<iwad>:<map>",
# for example "freedoom1:E1M1" (Doom 1 compatible) or "freedoom2:MAP01" (Doom II compatible)
WADS = {"freedoom1": ("freedoom1.cfg", "freedoom1.wad"), "freedoom2": ("freedoom2.cfg", "freedoom2.wad")}
RESOLUTIONS = {"160x120": vzd.ScreenResolution.RES_160X120, "320x240": vzd.ScreenResolution.RES_320X240,
               "640x480": vzd.ScreenResolution.RES_640X480, "800x600": vzd.ScreenResolution.RES_800X600}


@dataclass
class Observation:
    tic: int
    vars: dict[str, float]
    labels: list = field(default_factory=list)
    objects: list = field(default_factory=list)
    sectors: list = field(default_factory=list)
    screen: object = None   # H x W x 3 uint8, only when frames are kept
    width: int = 320


class DoomEnv:
    def __init__(self, scenario: str = "freedoom1:E1M1", skill: int = 3, seed: int = 0, realtime: bool = False,
                 visible: bool = False, resolution: str = "320x240", timeout_tics: int | None = None,
                 keep_screen: bool = False):
        self.scenario, self.skill, self.seed, self.realtime = scenario, skill, seed, realtime
        self.keep_screen = keep_screen
        g = vzd.DoomGame()
        if ":" in scenario:
            iwad, mp = scenario.split(":", 1)
            cfg, wad = WADS[iwad]
            g.load_config(os.path.join(vzd.scenarios_path, cfg))
            g.set_doom_game_path(os.path.join(os.path.dirname(vzd.__file__), wad))
            g.set_doom_map(mp)
        else:
            g.load_config(os.path.join(vzd.scenarios_path, f"{scenario}.cfg"))
        g.set_available_buttons(BUTTONS)
        g.set_available_game_variables(VARIABLES)
        g.set_doom_skill(skill)
        g.set_screen_resolution(RESOLUTIONS[resolution])
        g.set_screen_format(vzd.ScreenFormat.RGB24)
        g.set_render_crosshair(True)
        g.set_labels_buffer_enabled(True)
        g.set_objects_info_enabled(True)
        g.set_sectors_info_enabled(True)
        g.set_window_visible(visible)
        g.set_mode(vzd.Mode.ASYNC_PLAYER if realtime else vzd.Mode.PLAYER)
        if timeout_tics:
            g.set_episode_timeout(timeout_tics)
        g.set_seed(seed)
        g.init()
        self.game = g

    def start(self, record_path: str | None = None) -> None:
        self.game.new_episode(record_path or "")
        self.game.make_action(RELEASE, START_TICS)

    def observe(self) -> Observation | None:
        st = self.game.get_state()
        if st is None:
            return None
        names = [v.name for v in VARIABLES]
        vals = dict(zip(names, (float(x) for x in st.game_variables)))
        screen = st.screen_buffer if self.keep_screen else None
        width = st.screen_buffer.shape[1] if st.screen_buffer is not None else 320
        return Observation(st.tic, vals, list(st.labels), list(st.objects), list(st.sectors), screen, width)

    def act(self, action: str) -> float:
        reward = self.game.make_action(ACTION_BUTTONS[action], HOLD_TICS)
        if self.realtime:
            self.game.set_action(RELEASE)
        return reward

    @property
    def done(self) -> bool:
        return self.game.is_episode_finished()

    def outcome(self) -> dict:
        g = self.game
        dead = bool(g.is_player_dead())
        timeout = bool(g.is_episode_timeout_reached())
        return {"dead": dead, "timeout": timeout, "exited": bool(g.is_episode_finished() and not dead and not timeout),
                "total_reward": round(float(g.get_total_reward()), 3), "tic": int(g.get_episode_time()),
                "kills": int(g.get_game_variable(GV.KILLCOUNT)), "items": int(g.get_game_variable(GV.ITEMCOUNT)),
                "secrets": int(g.get_game_variable(GV.SECRETCOUNT)), "health": int(g.get_game_variable(GV.HEALTH))}

    def close(self) -> None:
        self.game.close()


def replay(scenario: str, record_path: str, skill: int = 3, seed: int = 0) -> dict:
    """Plays a recorded demo back in the engine and returns how the episode ended, for proof checks."""
    env = DoomEnv(scenario, skill=skill, seed=seed)
    g = env.game
    g.replay_episode(record_path)

    def sample() -> dict:
        return {"tic": int(g.get_episode_time()), "kills": int(g.get_game_variable(GV.KILLCOUNT)),
                "items": int(g.get_game_variable(GV.ITEMCOUNT)), "secrets": int(g.get_game_variable(GV.SECRETCOUNT)),
                "health": int(g.get_game_variable(GV.HEALTH))}

    prev, cur = None, sample()
    while not g.is_episode_finished():
        g.advance_action()
        prev, cur = cur, sample()
    out = env.outcome()
    env.close()
    # A demo that ends without a death or an exit makes the engine reset its counters on the same final tic;
    # that reset is not part of the game, so the values from just before it are the result
    if prev and cur["tic"] == prev["tic"] and (cur["kills"] < prev["kills"] or (cur["health"] == 0 < prev["health"])):
        out.update({k: prev[k] for k in ("kills", "items", "secrets", "health")})
        out["dead"] = prev["health"] <= 0
        out["exited"] = False
    return out
