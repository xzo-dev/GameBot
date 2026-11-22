from __future__ import annotations

import chess as pychess

from app.games.base import GameError, Player
from app.games.chess.module import MODULE as CHESS
from app.games.fighting.module import MODULE as FIGHT
from app.games.football.module import MODULE as FOOT
from app.games.jumanji.module import MODULE as JUMANJI
from app.games.uno.module import MODULE as UNO, build_deck, playable


def players(n: int, bot_from: int | None = None):
    return [Player(slot=i, id=i + 1, name=f"P{i}", bot=bot_from is not None and i >= bot_from) for i in range(n)]


def test_chess_legal_flow():
    state = CHESS.create_state(players(2), {"time_minutes": 5})
    events = CHESS.on_action(state, 0, {"type": "move", "uci": "e2e4"})
    assert events[0]["san"] == "e4"
    assert state["turn"] == 1
    with_illegal = CHESS.create_state(players(2), {})
    try:
        CHESS.on_action(with_illegal, 0, {"type": "move", "uci": "e2e5"})
        raise AssertionError("illegal move accepted")
    except GameError:
        pass
    board = pychess.Board()
    board.push_san("f3")
    board.push_san("e5")
    board.push_san("g4")
    board.push_san("Qh4#")
    assert board.is_checkmate()
    state = CHESS.create_state(players(2), {})
    for uci in ("f2f3", "e7e5", "g2g4", "d8h4"):
        slot = 0 if state["turn"] == 0 else 1
        CHESS.on_action(state, slot, {"type": "move", "uci": uci})
    assert state["finished"] and state["winners"] == [1] and state["reason"] == "checkmate"


def test_chess_bot_and_clock():
    state = CHESS.create_state(players(2, bot_from=1), {"time_minutes": 1})
    CHESS.on_action(state, 0, {"type": "move", "uci": "e2e4"})
    events = CHESS.bot_move(state)
    assert events and state["turn"] == 0
    before = state["clocks"][0]
    CHESS.on_tick(state, 0.5)
    assert state["clocks"][0] < before


def test_uno_deck_and_play():
    deck = build_deck()
    assert len(deck) == 108
    assert playable({"color": "R", "value": "5"}, {"color": "B", "value": "5"}, "B")
    state = UNO.create_state(players(2), {})
    assert len(state["hands"][0]) == 7 and len(state["hands"][1]) == 7
    slot = state["turn"]
    hand = state["hands"][slot]
    top = state["discard"][-1]
    legal = [(i, c) for i, c in enumerate(hand) if playable(c, top, state["current_color"])]
    legal = [
        (i, c) for i, c in legal
        if not (c["value"] == "wild4" and any(x["color"] == state["current_color"] for x in hand))
    ]
    if legal:
        idx, card = legal[0]
        UNO.on_action(state, slot, {"type": "play", "index": idx, "color": "R"})
        assert state["discard"][-1] == card
    else:
        UNO.on_action(state, slot, {"type": "draw"})
    assert state["turn"] != slot or state["drawn_card"] is not None


def test_uno_bot_turn():
    state = UNO.create_state(players(2, bot_from=1), {})
    state["turn"] = 1
    state["current_color"] = state["discard"][-1]["color"] if state["discard"][-1]["color"] != "W" else "R"
    events = UNO.bot_move(state)
    assert events is not None


def test_football_tick_and_goal():
    state = FOOT.create_state(players(2), {"seconds": 120})
    state["freeze"] = 0
    start_time = state["time_left"]
    for _ in range(20):
        FOOT.on_tick(state, 0.05)
    assert state["time_left"] < start_time
    state["freeze"] = 0
    state["ball"] = {"x": 99.5, "y": 32.0, "vx": 40.0, "vy": 0.0}
    events = []
    for _ in range(10):
        events += FOOT.on_tick(state, 0.05)
        if state["score"][0] == 1:
            break
    assert state["score"][0] == 1
    assert any(e["type"] == "goal" for e in events)
    assert FOOT.view(state, 0)["score"] == [1, 0]


def test_football_input_moves_entity():
    state = FOOT.create_state(players(2), {"seconds": 120})
    state["freeze"] = 0
    ent = next(e for e in state["entities"] if e.get("human") and e["t"] == 0)
    x = ent["x"]
    FOOT.on_action(state, 0, {"type": "move", "x": 1, "y": 0, "sprint": True})
    for _ in range(10):
        FOOT.on_tick(state, 0.05)
    assert ent["x"] > x


def test_fighting_hit_and_rounds():
    state = FIGHT.create_state(players(2), {})
    state["fighters"][0]["x"] = 45.0
    state["fighters"][1]["x"] = 50.0
    FIGHT.on_action(state, 0, {"type": "attack", "kind": "heavy"})
    for _ in range(10):
        FIGHT.on_tick(state, 0.05)
        if state["fighters"][1]["hp"] < 100:
            break
    assert state["fighters"][1]["hp"] < 100
    view = FIGHT.view(state, 0)
    assert view["fighters"][1]["hp"] < 100


def test_fighting_bot_acts_in_tick():
    state = FIGHT.create_state(players(2, bot_from=1), {"difficulty": "normal"})
    start = state["fighters"][1]["x"]
    for _ in range(200):
        FIGHT.on_tick(state, 0.05)
        if state["fighters"][0]["hp"] < 100:
            break
    assert state["fighters"][1]["x"] != start
    assert state["fighters"][0]["hp"] < 100


def test_jumanji_roll():
    state = JUMANJI.create_state(players(2, bot_from=1), {})
    JUMANJI.on_action(state, 0, {"type": "roll"})
    assert state["positions"][0] > 0
    assert state["turn"] == 1
    events = JUMANJI.bot_move(state)
    assert events is not None
