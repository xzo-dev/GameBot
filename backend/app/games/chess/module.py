from __future__ import annotations

import random
from typing import Any

import chess

from ..base import GameError, GameModule, Player

VALUES = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}
CENTER = {chess.PAWN: 8, chess.KNIGHT: 12, chess.BISHOP: 6, chess.ROOK: 2, chess.QUEEN: 4, chess.KING: 0}

DEPTH = {"easy": 1, "normal": 2, "hard": 3}


def evaluate(board: chess.Board) -> int:
    if board.is_checkmate():
        return -99999 if board.turn == chess.WHITE else 99999
    score = 0
    for square, piece in board.piece_map().items():
        value = VALUES[piece.piece_type]
        if piece.piece_type in (chess.PAWN, chess.KNIGHT, chess.BISHOP):
            value += CENTER[piece.piece_type] * (3.5 - abs(chess.square_file(square) - 3.5))
        score += value if piece.color == chess.WHITE else -value
    mobility = board.legal_moves.count()
    score += mobility * 2 if board.turn == chess.WHITE else -mobility * 2
    return int(score)


def search(board: chess.Board, depth: int, alpha: float, beta: float) -> float:
    if depth == 0 or board.is_game_over(claim_draw=True):
        return evaluate(board)
    if board.turn == chess.WHITE:
        best = -1e9
        for move in board.legal_moves:
            board.push(move)
            best = max(best, search(board, depth - 1, alpha, beta))
            board.pop()
            alpha = max(alpha, best)
            if beta <= alpha:
                break
        return best
    best = 1e9
    for move in board.legal_moves:
        board.push(move)
        best = min(best, search(board, depth - 1, alpha, beta))
        board.pop()
        beta = min(beta, best)
        if beta <= alpha:
            break
    return best


def choose_move(board: chess.Board, difficulty: str) -> chess.Move:
    moves = list(board.legal_moves)
    if not moves:
        raise GameError("Yurish yo'q")
    depth = DEPTH.get(difficulty, 2)
    scored: list[tuple[float, chess.Move]] = []
    for move in moves:
        if difficulty == "easy" and random.random() < 0.45:
            scored.append((random.uniform(-50, 50), move))
            continue
        board.push(move)
        score = search(board, depth - 1, -1e9, 1e9)
        board.pop()
        if difficulty == "easy":
            score += random.uniform(-60, 60)
        elif difficulty == "normal":
            score += random.uniform(-12, 12)
        scored.append((score, move))
    scored.sort(key=lambda item: item[0], reverse=board.turn == chess.WHITE)
    top = scored[0][0]
    if difficulty == "hard":
        return scored[0][1]
    pool = [mv for sc, mv in scored if abs(sc - top) <= (80 if difficulty == "easy" else 20)]
    return random.choice(pool)


class Chess(GameModule):
    id = "chess"
    title = "Shaxmat"
    description = "Klassik shaxmat: 1v1, soat, bot darajalari va to'liq qoidalar."
    icon = "♞"
    min_players = 2
    max_players = 2
    turn_timeout = 300
    rules_text = "Navbat bilan yurish. Shoh va mat — g'alaba. Vaqt tugashi — mag'lubiyat."

    def create_state(self, players: list[Player], settings: dict[str, Any]) -> dict[str, Any]:
        minutes = min(30, max(1, int(settings.get("time_minutes", 5))))
        state = {
            "board": chess.Board(),
            "clocks": [minutes * 60.0, minutes * 60.0],
            "increment": int(settings.get("increment", 2)),
            "slots": [p.public() for p in players],
            "turn": 0,
            "draw_offer": None,
            "last_move": None,
            "finished": False,
            "winners": [],
            "draw": False,
            "reason": "",
            "moves": [],
            "turn_timeout": minutes * 60,
            "difficulty": settings.get("difficulty", "normal"),
        }
        return state

    def _slot_for_color(self, state: dict[str, Any], color: chess.Color) -> int:
        return 0 if color == chess.WHITE else 1

    def on_action(self, state: dict[str, Any], slot: int, action: dict[str, Any]) -> list[dict[str, Any]]:
        if state["finished"]:
            raise GameError("O'yin tugagan")
        kind = action.get("type")
        if slot != state["turn"] and kind not in ("accept_draw", "decline_draw"):
            raise GameError("Hozir sizning navbatingiz emas")

        if kind == "move":
            board: chess.Board = state["board"]
            try:
                move = chess.Move.from_uci(str(action.get("uci", "")))
            except ValueError:
                raise GameError("Yurish formati noto'g'ri") from None
            if move not in board.legal_moves:
                raise GameError("Bu yurish qoidalarga mos emas")
            san = board.san(move)
            board.push(move)
            state["clocks"][slot] += state["increment"]
            state["moves"].append(san)
            state["last_move"] = {"from": chess.square_name(move.from_square), "to": chess.square_name(move.to_square)}
            state["draw_offer"] = None
            state["turn"] = 1 - slot
            self._check_end(state)
            return [{"type": "move", "by": slot, "san": san, "uci": move.uci()}]

        if kind == "resign":
            state.update(finished=True, winners=[1 - slot], draw=False, reason="resign")
            return [{"type": "resign", "by": slot}]

        if kind == "offer_draw":
            if state["draw_offer"] is not None:
                raise GameError("Taklif allaqachon berilgan")
            state["draw_offer"] = slot
            return [{"type": "draw_offer", "by": slot}]

        if kind == "accept_draw":
            if state["draw_offer"] is None or state["draw_offer"] == slot:
                raise GameError("Qabul qilish uchun taklif yo'q")
            state.update(finished=True, draw=True, reason="draw_agreed")
            return [{"type": "draw", "by": slot}]

        if kind == "decline_draw":
            state["draw_offer"] = None
            return [{"type": "draw_declined", "by": slot}]

        raise GameError("Noma'lum amal")

    def _check_end(self, state: dict[str, Any]) -> None:
        board: chess.Board = state["board"]
        if not board.is_game_over(claim_draw=True):
            return
        outcome = board.outcome(claim_draw=True)
        state["finished"] = True
        if outcome and outcome.winner is not None:
            state["winners"] = [self._slot_for_color(state, outcome.winner)]
            state["reason"] = "checkmate" if board.is_checkmate() else "game_over"
        else:
            state["draw"] = True
            state["reason"] = "draw"

    def on_timeout(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        if state["finished"]:
            return []
        loser = state["turn"]
        state.update(finished=True, winners=[1 - loser], draw=False, reason="timeout")
        return [{"type": "timeout", "by": loser}]

    def on_tick(self, state: dict[str, Any], dt: float) -> list[dict[str, Any]]:
        if state["finished"]:
            return []
        state["clocks"][state["turn"]] -= dt
        if state["clocks"][state["turn"]] <= 0:
            state["clocks"][state["turn"]] = 0
            return self.on_timeout(state)
        return []

    def bot_move(self, state: dict[str, Any]) -> list[dict[str, Any]] | None:
        if state["finished"] or state["turn"] != 1:
            return None
        board: chess.Board = state["board"]
        difficulty = state.get("difficulty", "normal")
        move = choose_move(board, difficulty)
        return self.on_action(state, 1, {"type": "move", "uci": move.uci()})

    def view(self, state: dict[str, Any], slot: int | None) -> dict[str, Any]:
        board: chess.Board = state["board"]
        legal = [m.uci() for m in board.legal_moves] if slot == state["turn"] and not state["finished"] else []
        return {
            "fen": board.fen(),
            "turn": state["turn"],
            "your_slot": slot,
            "clocks": [round(c, 1) for c in state["clocks"]],
            "last_move": state["last_move"],
            "legal": legal,
            "check": board.is_check(),
            "draw_offer": state["draw_offer"],
            "moves": state["moves"][-12:],
            "finished": state["finished"],
            "result": self.result(state) if state["finished"] else None,
            "slots": state["slots"],
        }


MODULE = Chess()
