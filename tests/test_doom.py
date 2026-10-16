"""Doom stage: geometry, one-step facts, the priority reader, the log format and (if installed) the engine."""

import json
from types import SimpleNamespace as NS

import pytest

from laya_agent.arena.spec_log import SpecLog, verify_log
from laya_agent.doom.engine import ACTIONS
from laya_agent.doom.facts import Enemy, Item, Missile, Scene, facts, questions, reader_choice, reader_scores, state_text
from laya_agent.doom.geometry import Explored, Hit, LevelGeometry, bearing


def box_room(size=512.0, floor=0.0, ceiling=128.0, sid=0):
    s = size
    lines = [NS(x1=0, y1=0, x2=s, y2=0, is_blocking=False), NS(x1=s, y1=0, x2=s, y2=s, is_blocking=False),
             NS(x1=s, y1=s, x2=0, y2=s, is_blocking=False), NS(x1=0, y1=s, x2=0, y2=0, is_blocking=False)]
    return NS(id=sid, floor_height=floor, ceiling_height=ceiling, lines=lines)


def test_ray_stops_at_the_wall_and_doors_are_told_apart():
    geo = LevelGeometry.from_sectors([box_room()])
    hit = geo.cast(100, 256, 0.0)
    assert hit.kind == "wall" and abs(hit.dist - 412) < 1e-6
    # A closed door: a sector whose ceiling sits on its floor, sharing a line with the room
    door = NS(id=1, floor_height=0.0, ceiling_height=0.0, lines=[NS(x1=512, y1=0, x2=512, y2=512, is_blocking=False)])
    geo = LevelGeometry.from_sectors([box_room(), door])
    assert geo.cast(100, 256, 0.0).kind == "door"


def test_a_step_down_is_open_and_a_step_up_blocks():
    low = box_room(floor=0.0)
    high = NS(id=1, floor_height=64.0, ceiling_height=192.0, lines=[NS(x1=512, y1=0, x2=512, y2=512, is_blocking=False)])
    geo = LevelGeometry.from_sectors([low, high])
    assert geo.cast(100, 256, 0.0, z=0.0).kind == "ledge"        # 64 units up: cannot climb
    assert geo.cast(100, 256, 0.0, z=64.0).kind == "open"        # standing on the high side: can step down


def test_bearing_is_positive_to_the_left():
    assert round(bearing(0, 0, 0.0, 0, 100)) == 90
    assert round(bearing(0, 0, 90.0, 100, 0)) == -90


def test_explored_counts_only_new_ground_along_the_line():
    ex = Explored()
    assert ex.new_cells_along(0, 0, 0.0, 600) > 0
    for x in range(0, 600, 32):
        ex.mark(x, 0)
    assert ex.new_cells_along(0, 0, 0.0, 600) == 0


def scene(**kw):
    rays = {a: Hit(600.0, "wall") for a in ("forward", "backward", "strafe_left", "strafe_right", "turn_left_big",
                                            "turn_right_big", "turn_left", "turn_right")}
    base = dict(x=0.0, y=0.0, angle=0.0, health=100, armor=0, weapon=2, ammo=20, kills=0, rays=rays,
                new_cells={a: 0 for a in rays})
    base.update(kw)
    return Scene(**base)


def test_shooting_an_enemy_in_the_crosshair_is_the_reader_choice():
    s = scene(enemies=[Enemy(1, "Imp", 300.0, 1.0, True, True)])
    fs = facts(s)
    assert "hits it" in fs["shoot"].text
    assert reader_choice(reader_scores(s, fs)) == "shoot"


def test_firing_at_nothing_is_described_as_waste_and_never_chosen():
    s = scene(enemies=[Enemy(1, "Imp", 300.0, 20.0, True, False)])
    fs = facts(s)
    assert "hits nothing" in fs["shoot"].text
    choice = reader_choice(reader_scores(s, fs))
    assert choice in ("turn_left", "turn_left_big")  # the Imp is 20 degrees left


def test_turn_facts_say_where_the_enemy_ends_up():
    s = scene(enemies=[Enemy(1, "Imp", 400.0, 5.0, True, False)])
    fs = facts(s)
    assert "puts the Imp" in fs["turn_left"].text and "in the crosshair" in fs["turn_left"].text
    assert "further from the crosshair" in fs["turn_right"].text


def test_a_blocked_move_and_a_door_in_reach():
    rays = {a: Hit(600.0, "wall") for a in ("backward", "strafe_left", "strafe_right", "turn_left_big",
                                            "turn_right_big", "turn_left", "turn_right")}
    rays["forward"] = Hit(30.0, "door")
    s = scene(rays=rays)
    fs = facts(s)
    assert "blocked by a closed door" in fs["forward"].text
    assert fs["use"].offered and "opens the closed door" in fs["use"].text
    assert reader_choice(reader_scores(s, fs)) == "use"


def test_use_is_not_offered_without_a_door():
    fs = facts(scene())
    assert not fs["use"].offered
    assert "use" not in questions(fs)


def test_strafing_away_from_a_fireball_is_preferred():
    s = scene(missiles=[Missile("doom imp ball", 120.0, "strafe_left")])
    fs = facts(s)
    assert "steps out of the path" in fs["strafe_left"].text
    assert "stays in the path" in fs["strafe_right"].text
    assert reader_choice(reader_scores(s, fs)) == "strafe_left"


def test_undoing_the_last_move_is_stated_and_ranked_low():
    s = scene(last="forward", new_cells={"backward": 3, "forward": 0, "strafe_left": 0, "strafe_right": 0,
                                         "turn_left_big": 0, "turn_right_big": 0, "turn_left": 0, "turn_right": 0})
    fs = facts(s)
    assert "back where you just came from" in fs["backward"].text
    assert reader_scores(s, fs)["backward"] <= 3.0


def test_health_pickup_when_hurt():
    s = scene(health=30, items=[Item("medikit", "Health", 150.0, 2.0)])
    fs = facts(s)
    assert "toward the medikit" in fs["forward"].text
    assert reader_choice(reader_scores(s, fs)) == "forward"


def test_state_text_names_enemies_and_damage():
    s = scene(enemies=[Enemy(1, "Imp", 300.0, 12.0, True, False)], lost_health=10)
    t = state_text(s)
    assert "Imp 12 degrees left, 300 units" in t and "You just lost 10 health" in t


def test_doom_log_uses_the_same_hash_rule_with_doom_action_keys(tmp_path):
    log = SpecLog(tmp_path / "d.jsonl", "doom-x", "doom", keys=ACTIONS)
    probs = {a: 0.0 for a in ACTIONS}
    probs["shoot"], probs["forward"] = 0.6, 0.4
    decision = {"questions": ["q1", "q2"], "probabilities": probs, "chosen": "shoot", "confidence": 0.6, "source": "laya"}
    for step in (1, 2):
        log.write(step=step, state_before={"tic": step}, action="shoot", state_after={"tic": step + 4},
                  result="applied", decision=decision, timing={"decide_ms": 5, "api_ms": 2, "turn_ms": 8})
    log.close()
    assert verify_log(tmp_path / "d.jsonl", keys=ACTIONS)["ok"]
    assert not verify_log(tmp_path / "d.jsonl")["ok"]  # the up/down/left/right keys do not apply to Doom
    lines = (tmp_path / "d.jsonl").read_text().splitlines()
    first = json.loads(lines[0])
    assert first["prev_hash"] == "GENESIS-doom-x"


vizdoom = pytest.importorskip("vizdoom")


def test_engine_episode_replays_to_the_same_result(tmp_path):
    from laya_agent.doom.engine import DoomEnv, replay
    from laya_agent.doom.facts import Perceiver

    env = DoomEnv("defend_the_center", seed=3, timeout_tics=35 * 20)
    lmp = tmp_path / "ep.lmp"
    env.start(str(lmp))
    p = Perceiver()
    while not env.done:
        obs = env.observe()
        if obs is None:
            break
        s = p.scene(obs)
        a = reader_choice(reader_scores(s, facts(s)))
        env.act(a)
        p.note(a)
    out = env.outcome()
    env.close()
    again = replay("defend_the_center", str(lmp), seed=3)
    assert (again["kills"], again["health"], again["dead"]) == (out["kills"], out["health"], out["dead"])
    assert abs(again["tic"] - out["tic"]) <= 1
