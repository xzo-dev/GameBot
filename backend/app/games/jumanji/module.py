from __future__ import annotations

import random
from typing import Any

from ..base import GameError, GameModule, Player

BOARD_SIZE = 30
_PATTERN = ["jungle", "jungle", "jungle", "hazard", "bonus", "challenge"]
CELLS: list[str] = ["start"] + [_PATTERN[i % len(_PATTERN)] for i in range(1, BOARD_SIZE)] + ["finish"]
EVENTS = {
    "hazard": [
        "Zaharli ilonlar yo'li — bir navbat o'tkazasiz.",
        "Botqoqqa cho'kdingiz — keyingi navbatni o'tkazasiz.",
        "Yirtqich hayvon izi — qo'rqib bir navbat kutasiz.",
    ],
    "bonus": [
        "Qadimiy xazina topdingiz: +1 energiya.",
        "Sirli meva: +1 energiya.",
        "Yashirin yo'l: +1 energiya.",
    ],
    "challenge": [
        "Tosh yo'lbars sinovi: 4+ tashlasangiz o'tasiz.",
        "Daryo kechuv sinovi: 4+ kerak.",
        "Jungli qo'riqchisi sinovi: 4+ kerak.",
    ],
}


class Jumanji(GameModule):
    id = "jumanji"
    title = "Jumanji sarguzashti"
    description = "4 o'yinchigacha sarguzasht: zar, voqealar, sinovlar va xazinalar."
    icon = "🐘"
    min_players = 2
    max_players = 4
    turn_timeout = 40
    rules_text = "Zar tashlang, 30-katakka yeting. Energiya sarflab +2 qo'shishingiz mumkin."

    def create_state(self, players: list[Player], settings: dict[str, Any]) -> dict[str, Any]:
        coop = str(settings.get("mode", "competitive")) == "coop"
        return {
            "slots": [p.public() for p in players],
            "positions": [0 for _ in players],
            "energy": [2 for _ in players],
            "skips": [0 for _ in players],
            "done": [],
            "turn": 0,
            "dice": 0,
            "last": "",
            "log": ["Jumanji o'yini boshlandi. Omad!"],
            "finished": False,
            "winners": [],
            "draw": False,
            "reason": "",
            "coop": coop,
            "difficulty": settings.get("difficulty", "normal"),
        }

    def _advance(self, state: dict[str, Any], slot: int) -> None:
        state["turn"] = (slot + 1) % len(state["slots"])
        guard = 0
        while guard < 12:
            turn = state["turn"]
            if state["skips"][turn] > 0:
                state["skips"][turn] -= 1
                state["log"].append(f"{state['slots'][turn]['name']} navbatni o'tkazadi")
                state["turn"] = (turn + 1) % len(state["slots"])
            elif turn in state["done"] and len(state["done"]) < len(state["slots"]):
                state["turn"] = (turn + 1) % len(state["slots"])
            else:
                break
            guard += 1
        if len(state["done"]) == len(state["slots"]):
            self._finish_all(state)

    def _finish_all(self, state: dict[str, Any]) -> None:
        state["finished"] = True
        state["reason"] = "all_finished"
        if state["coop"]:
            state["winners"] = [s["slot"] for s in state["slots"]]
        else:
            state["winners"] = [state["done"][0]] if state["done"] else []

    def on_action(self, state: dict[str, Any], slot: int, action: dict[str, Any]) -> list[dict[str, Any]]:
        if state["finished"]:
            raise GameError("O'yin tugagan")
        if slot != state["turn"]:
            raise GameError("Hozir sizning navbatingiz emas")
        kind = action.get("type")
        if kind != "roll":
            raise GameError("Faqat zar tashlash mumkin")

        boost = bool(action.get("energy"))
        if boost and state["energy"][slot] <= 0:
            raise GameError("Energiya yo'q")
        if boost:
            state["energy"][slot] -= 1

        dice = random.randint(1, 6)
        step = dice + (2 if boost else 0)
        state["dice"] = dice
        pos = state["positions"][slot] + step
        if pos > BOARD_SIZE:
            pos = BOARD_SIZE - (pos - BOARD_SIZE)
        state["positions"][slot] = max(0, pos)
        state["log"].append(f"{state['slots'][slot]['name']}: 🎲 {dice}{' (+2)' if boost else ''} → {pos}-katak")
        events: list[dict[str, Any]] = [{"type": "roll", "by": slot, "dice": dice, "to": pos}]

        if pos >= BOARD_SIZE:
            if slot not in state["done"]:
                state["done"].append(slot)
                state["log"].append(f"{state['slots'][slot]['name']} marraga yetdi!")
                events.append({"type": "reached", "by": slot})
            if state["coop"]:
                if len(state["done"]) == len(state["slots"]):
                    self._finish_all(state)
                    events.append({"type": "finish"})
                    return events
            else:
                state["finished"] = True
                state["winners"] = [slot]
                state["reason"] = "reached"
                events.append({"type": "finish"})
                return events
            self._advance(state, slot)
            return events

        cell = CELLS[pos]
        if cell == "hazard":
            state["skips"][slot] = 1
            state["log"].append(random.choice(EVENTS["hazard"]))
        elif cell == "bonus":
            state["energy"][slot] += 1
            state["log"].append(random.choice(EVENTS["bonus"]))
        elif cell == "challenge":
            check = random.randint(1, 6)
            if check >= 4:
                state["positions"][slot] = min(BOARD_SIZE, pos + 2)
                state["log"].append(f"{random.choice(EVENTS['challenge'])} Sinov o'tdi (🎲 {check})! +2 katak.")
            else:
                state["positions"][slot] = max(0, pos - 2)
                state["log"].append(f"Sinov muvaffaqiyatsiz (🎲 {check}). -2 katak.")
            if state["positions"][slot] >= BOARD_SIZE and slot not in state["done"]:
                state["done"].append(slot)
                state["log"].append(f"{state['slots'][slot]['name']} sinov orqali marraga yetdi!")
                if not state["coop"]:
                    state["finished"] = True
                    state["winners"] = [slot]
                    state["reason"] = "reached"
                    events.append({"type": "finish"})
                    return events
                if len(state["done"]) == len(state["slots"]):
                    self._finish_all(state)
                    events.append({"type": "finish"})
                    return events
        state["last"] = CELLS[state["positions"][slot]]
        self._advance(state, slot)
        return events

    def on_timeout(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        if state["finished"]:
            return []
        slot = state["turn"]
        state["log"].append(f"{state['slots'][slot]['name']} vaqt tugadi — avtomatik zar")
        return self.on_action(state, slot, {"type": "roll"})

    def bot_move(self, state: dict[str, Any]) -> list[dict[str, Any]] | None:
        if state["finished"]:
            return None
        slot = state["turn"]
        if not state["slots"][slot]["bot"]:
            return None
        use_energy = state["energy"][slot] > 0 and state["positions"][slot] >= BOARD_SIZE - 8
        if state.get("difficulty") == "easy" and random.random() < 0.5:
            use_energy = False
        return self.on_action(state, slot, {"type": "roll", "energy": use_energy})

    def view(self, state: dict[str, Any], slot: int | None) -> dict[str, Any]:
        return {
            "positions": state["positions"],
            "energy": state["energy"],
            "done": state["done"],
            "turn": state["turn"],
            "dice": state["dice"],
            "last": state["last"],
            "log": state["log"][-10:],
            "coop": state["coop"],
            "your_slot": slot,
            "board_size": BOARD_SIZE,
            "cells": CELLS,
            "slots": state["slots"],
            "finished": state["finished"],
            "result": self.result(state) if state["finished"] else None,
        }

    def result(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "draw": state.get("draw", False),
            "winners": state.get("winners", []),
            "scores": {str(i): p for i, p in enumerate(state["positions"])},
            "reason": state.get("reason", ""),
        }


MODULE = Jumanji()
