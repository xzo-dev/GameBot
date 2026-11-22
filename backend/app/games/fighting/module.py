from __future__ import annotations

import random
from typing import Any

from ..base import GameError, GameModule, Player

ARENA = 100.0
ATTACKS = {
    "light": {"cd": 0.42, "range": 9.0, "windup": 0.10, "damage": (5, 8)},
    "heavy": {"cd": 0.95, "range": 11.5, "windup": 0.28, "damage": (12, 17)},
}


class Fighting(GameModule):
    id = "fighting"
    title = "Jang"
    description = "1v1 real vaqt jangi: zarbalar, blok, dodj va raundlar."
    icon = "🥊"
    min_players = 2
    max_players = 2
    realtime = True
    tick_hz = 20
    rules_text = "3 raunddan 2 tasini yuting. Zarba, blok va dodjdan foydalaning."

    def create_state(self, players: list[Player], settings: dict[str, Any]) -> dict[str, Any]:
        return {
            "slots": [p.public() for p in players],
            "fighters": [
                {"slot": 0, "x": 30.0, "hp": 100.0, "facing": 1, "cd": 0.0, "dodge": 0.0, "dodge_cd": 0.0,
                 "stun": 0.0, "attack": None, "attack_t": 0.0, "block": False, "rounds": 0},
                {"slot": 1, "x": 70.0, "hp": 100.0, "facing": -1, "cd": 0.0, "dodge": 0.0, "dodge_cd": 0.0,
                 "stun": 0.0, "attack": None, "attack_t": 0.0, "block": False, "rounds": 0},
            ],
            "inputs": {"0": {"move": 0, "block": False}, "1": {"move": 0, "block": False}},
            "round": 1,
            "round_time": 60.0,
            "pause": 0.0,
            "finished": False,
            "winners": [],
            "draw": False,
            "reason": "",
            "events": [],
            "log": [],
            "difficulty": settings.get("difficulty", "normal"),
            "ai_cd": 0.0,
        }

    def _fighter(self, state: dict[str, Any], slot: int) -> dict[str, Any]:
        return state["fighters"][slot]

    def on_action(self, state: dict[str, Any], slot: int, action: dict[str, Any]) -> list[dict[str, Any]]:
        if state["finished"]:
            raise GameError("O'yin tugagan")
        if state["pause"] > 0:
            return []
        kind = action.get("type")
        other = self._fighter(state, 1 - slot)
        fighter = self._fighter(state, slot)
        fighter["facing"] = 1 if other["x"] > fighter["x"] else -1
        if kind == "move":
            try:
                move = int(action.get("move", 0))
            except (TypeError, ValueError):
                move = 0
            state["inputs"][str(slot)]["move"] = 0 if move == 0 else (1 if move > 0 else -1)
            return []
        if kind == "block":
            state["inputs"][str(slot)]["block"] = bool(action.get("on", True))
            fighter["block"] = bool(action.get("on", True))
            return []
        if kind == "attack":
            if fighter["cd"] > 0 or fighter["stun"] > 0 or fighter["dodge"] > 0:
                return []
            attack = str(action.get("kind", "light"))
            if attack not in ATTACKS:
                raise GameError("Zarba turi noto'g'ri")
            fighter["attack"] = attack
            fighter["attack_t"] = ATTACKS[attack]["windup"]
            fighter["cd"] = ATTACKS[attack]["cd"]
            fighter["block"] = False
            state["inputs"][str(slot)]["block"] = False
            return [{"type": "swing", "by": slot, "kind": attack}]
        if kind == "dodge":
            if fighter["dodge_cd"] > 0 or fighter["stun"] > 0:
                return []
            fighter["dodge"] = 0.32
            fighter["dodge_cd"] = 1.4
            return [{"type": "dodge", "by": slot}]
        if kind == "resign":
            state["finished"] = True
            state["winners"] = [1 - slot]
            state["reason"] = "resign"
            state["log"].append("Jangchi taslim bo'ldi")
            return [{"type": "finish"}]
        raise GameError("Noma'lum amal")

    def on_tick(self, state: dict[str, Any], dt: float) -> list[dict[str, Any]]:
        if state["finished"]:
            return []
        state["events"] = []
        if state["pause"] > 0:
            state["pause"] -= dt
            if state["pause"] <= 0:
                self._new_round(state)
            return state["events"]

        state["round_time"] -= dt
        for fighter in state["fighters"]:
            fighter["cd"] = max(0.0, fighter["cd"] - dt)
            fighter["stun"] = max(0.0, fighter["stun"] - dt)
            fighter["dodge"] = max(0.0, fighter["dodge"] - dt)
            fighter["dodge_cd"] = max(0.0, fighter["dodge_cd"] - dt)

        if state["slots"][1].get("bot"):
            state["ai_cd"] -= dt
            if state["ai_cd"] <= 0:
                state["ai_cd"] = 0.25
                state["events"].extend(self.bot_move(state) or [])

        for slot in (0, 1):
            fighter = self._fighter(state, slot)
            other = self._fighter(state, 1 - slot)
            fighter["facing"] = 1 if other["x"] > fighter["x"] else -1
            move = state["inputs"][str(slot)]["move"]
            if move and fighter["stun"] <= 0 and fighter["attack_t"] <= 0:
                speed = 20.0 if move * fighter["facing"] > 0 else 13.0
                fighter["x"] = max(6.0, min(ARENA - 6.0, fighter["x"] + move * speed * dt))
            if fighter["attack_t"] > 0:
                fighter["attack_t"] -= dt
                if fighter["attack_t"] <= 0:
                    self._resolve_hit(state, slot)

        if state["round_time"] <= 0:
            self._end_round(state)
        return state["events"]

    def _resolve_hit(self, state: dict[str, Any], slot: int) -> None:
        attacker = self._fighter(state, slot)
        defender = self._fighter(state, 1 - slot)
        spec = ATTACKS.get(attacker["attack"] or "light")
        attacker["attack"] = None
        if not spec:
            return
        distance = abs(attacker["x"] - defender["x"])
        if distance > spec["range"] or (defender["x"] - attacker["x"]) * attacker["facing"] < 0:
            return
        if defender["dodge"] > 0:
            state["events"].append({"type": "miss", "by": slot})
            return
        damage = random.uniform(*spec["damage"])
        blocked = defender["block"]
        if blocked:
            damage *= 0.18
        defender["hp"] = max(0.0, defender["hp"] - damage)
        if not blocked:
            defender["stun"] = 0.18
        state["events"].append({"type": "hit", "by": slot, "damage": round(damage, 1), "blocked": blocked})
        if defender["hp"] <= 0:
            self._end_round(state)

    def _end_round(self, state: dict[str, Any]) -> None:
        a, b = state["fighters"]
        if a["hp"] == b["hp"]:
            state["log"].append(f"{state['round']}-raund: durang")
            winner = None
        else:
            winner = 0 if a["hp"] > b["hp"] else 1
            state["fighters"][winner]["rounds"] += 1
            state["log"].append(f"{state['round']}-raund: {state['slots'][winner]['name']}")
        state["events"].append({"type": "round_end", "winner": winner, "round": state["round"]})
        if any(f["rounds"] >= 2 for f in state["fighters"]):
            winner_idx = 0 if a["rounds"] >= 2 else 1
            state["finished"] = True
            state["winners"] = [winner_idx]
            state["reason"] = "knockout"
            state["log"].append(f"{state['slots'][winner_idx]['name']} jangni yutdi")
            state["events"].append({"type": "finish"})
            return
        state["pause"] = 2.5
        state["round"] += 1
        state["round_time"] = 60.0

    def _new_round(self, state: dict[str, Any]) -> None:
        for i, fighter in enumerate(state["fighters"]):
            fighter.update(hp=100.0, x=30.0 if i == 0 else 70.0, cd=0.0, stun=0.0, dodge=0.0,
                           dodge_cd=0.0, attack=None, attack_t=0.0, block=False)
        state["inputs"] = {"0": {"move": 0, "block": False}, "1": {"move": 0, "block": False}}

    def bot_move(self, state: dict[str, Any]) -> list[dict[str, Any]] | None:
        if state["finished"] or state["pause"] > 0:
            return None
        slot = 1
        fighter = self._fighter(state, slot)
        opponent = self._fighter(state, 0)
        difficulty = state.get("difficulty", "normal")
        distance = abs(opponent["x"] - fighter["x"])
        events: list[dict[str, Any]] = []

        if difficulty == "easy" and random.random() < 0.4:
            return None
        if difficulty == "hard" and opponent["attack"] and distance < 13 and fighter["dodge_cd"] <= 0:
            if random.random() < 0.55:
                return self.on_action(state, slot, {"type": "dodge"})
            return self.on_action(state, slot, {"type": "block", "on": True})

        move = 1 if opponent["x"] > fighter["x"] else -1
        if distance > ATTACKS["light"]["range"] - 1:
            events += self.on_action(state, slot, {"type": "move", "move": move})
        else:
            if fighter["block"]:
                events += self.on_action(state, slot, {"type": "block", "on": False})
            if random.random() < (0.2 if difficulty == "easy" else 0.55 if difficulty == "normal" else 0.8):
                kind = "heavy" if difficulty == "hard" and random.random() < 0.35 else "light"
                events += self.on_action(state, slot, {"type": "attack", "kind": kind})
        return events

    def view(self, state: dict[str, Any], slot: int | None) -> dict[str, Any]:
        return {
            "fighters": [
                {"slot": f["slot"], "x": round(f["x"], 1), "hp": round(f["hp"], 1), "rounds": f["rounds"],
                 "block": f["block"], "dodge": f["dodge"] > 0, "stun": f["stun"] > 0,
                 "attack": f["attack"], "cd": round(f["cd"], 2)}
                for f in state["fighters"]
            ],
            "round": state["round"],
            "time": max(0, round(state["round_time"], 1)),
            "pause": round(state["pause"], 1),
            "your_slot": slot,
            "log": state["log"][-6:],
            "slots": state["slots"],
            "finished": state["finished"],
            "result": self.result(state) if state["finished"] else None,
        }

    def result(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "draw": state.get("draw", False),
            "winners": state.get("winners", []),
            "scores": {str(f["slot"]): f["rounds"] for f in state["fighters"]},
            "reason": state.get("reason", ""),
        }


MODULE = Fighting()
