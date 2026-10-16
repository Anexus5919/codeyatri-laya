from laya_agent.arena.grid_facts import GridView, grid_facts, grid_state_text


def view(**kw):
    base = dict(width=5, height=5, player=(2, 2), targets={(4, 4)}, target_name="the exit")
    base.update(kw)
    return GridView(**base)


def test_walls_and_edges_are_illegal_not_fatal():
    f = grid_facts(view(player=(0, 0), walls={(1, 0)}))
    assert f["up"].kind == "wall" and not f["up"].legal and not f["up"].fatal
    assert f["right"].kind == "wall" and not f["right"].legal


def test_hazard_is_legal_but_fatal_and_threats_are_flagged():
    f = grid_facts(view(hazards={(2, 1)}, threats={(4, 2)}))
    assert f["up"].kind == "hazard" and f["up"].fatal
    assert f["right"].data["adjacent_threats"] == 1 and "enemy" in f["right"].text
    assert "safe" not in f["right"].text and f["down"].text.startswith("move down: safe")


def test_distance_trend_and_reach():
    f = grid_facts(view(player=(3, 4)))
    assert f["right"].kind == "reach" and "reaches the exit now" in f["right"].text
    assert "closer" not in f["left"].text and "farther" in f["left"].text


def test_pocket_detection_uses_body_size():
    walls = {(1, 0), (1, 1), (0, 2), (1, 2)}  # cell (0,0),(0,1) form a 2-cell pocket
    f = grid_facts(view(player=(0, 1), walls=walls, body_size=5))
    assert "closed pocket" in f["up"].text


def test_blocked_direction_rule():
    f = grid_facts(view(blocked_dirs={"left"}, blocked_reason="reverses direction"))
    assert not f["left"].legal and "reverses direction" in f["left"].text


def test_state_text_mentions_player_target_and_enemies():
    t = grid_state_text("Maze", view(threats={(1, 1)}))
    assert "Player at x=2, y=2" in t and "exit at x=4, y=4" in t and "Enemies: 1" in t
