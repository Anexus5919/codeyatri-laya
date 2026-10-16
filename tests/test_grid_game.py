import json

from laya_agent.arena.games import GAMES
from laya_agent.arena.grid_game import GridSpec, build_view, register, register_from_file

# A made-up stage-3 state shape, to prove a new grid game needs only a mapping
STATE = {
    "width": 6, "height": 4,
    "player": {"x": 1, "y": 1},
    "grid": [
        [0, 0, 0, 0, 0, 0],
        [0, 0, 1, 0, 3, 0],
        [0, 0, 1, 0, 0, 0],
        [4, 0, 0, 0, 0, 2],
    ],
    "health": 80,
    "score": 120,
}
SPEC = dict(name="testdoom", title="Doom-style arena", grid_codes={"wall": [1], "target": [2], "enemy": [3], "hazard": [4]},
            target_name="the exit", priorities="Priorities: stay alive, avoid enemies, reach the exit.",
            points={"field": "score", "cap": 1000}, extra_state_fields=["health"])


def test_view_reads_codes_from_the_grid():
    v = build_view(GridSpec(**SPEC), STATE)
    assert v.walls == {(2, 1), (2, 2)} and v.targets == {(5, 3)} and v.threats == {(4, 1)} and v.hazards == {(0, 3)}
    assert v.player == (1, 1)


def test_registered_game_produces_facts_state_text_and_points():
    name = register(GridSpec(**SPEC))
    g = GAMES[name]
    facts = g["facts"](STATE)
    assert not facts["right"].legal and facts["right"].kind == "wall"
    assert facts["down"].legal and "closer to the exit" in facts["down"].text
    text = g["state_text"](STATE)
    assert "Doom-style arena on a 6x4 grid" in text and "health: 80." in text
    assert g["points"]({"state": STATE}) == 120
    assert g["priorities"].startswith("Priorities")


def test_register_from_json_file(tmp_path):
    p = tmp_path / "doom.json"
    p.write_text(json.dumps(SPEC), encoding="utf-8")
    assert register_from_file(p) == "testdoom"


def test_lists_of_cells_and_no_reverse_rule():
    spec = GridSpec(name="t2", title="T", grid=None, enemies="enemies", targets="goal", blocked_from_direction="heading")
    state = {"width": 4, "height": 4, "player": [1, 1], "enemies": [{"x": 3, "y": 1}], "goal": {"x": 3, "y": 3}, "heading": "up"}
    v = build_view(spec, state)
    assert v.threats == {(3, 1)} and v.targets == {(3, 3)} and v.blocked_dirs == {"down"}
