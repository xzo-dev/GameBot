from __future__ import annotations

import math
import random
from typing import Any

from ..base import GameError, GameModule, Player

W, H = 100.0, 64.0
GOAL_Y1, GOAL_Y2 = 22.0, 42.0
SPEED = {"easy": 11.0, "normal": 13.5, "hard": 15.5}
SHOOT_SPEED = 62.0
PASS_SPEED = 40.0


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


class Football(GameModule):
    id = "football"
    title = "Futbol"
    description = "Real vaqtda 1v1 va 2v2 futbol: dribling, pas, zarba, bot raqiblar."
    icon = "⚽"
    min_players = 2
    max_players = 4
    realtime = True
    tick_hz = 20
    rules_text = "To'pni darvoza ichiga kiriting. Joystick bilan yuring, pas va zarba tugmalari bilan o'ynang."

    def create_state(self, players: list[Player], settings: dict[str, Any]) -> dict[str, Any]:
        per_team = max(1, len(players) // 2)
        difficulty = settings.get("difficulty", "normal")
        minutes = clamp(float(settings.get("seconds", 120)), 60, 300)
        entities = []
        homes0 = [(4.0, 32.0, True), (20.0, 17.0, False), (20.0, 47.0, False), (36.0, 32.0, False), (50.0, 32.0, False)]
        for i, (x, y, gk) in enumerate(homes0):
            entities.append({"id": i, "t": 0, "x": x, "y": y, "hx": x, "hy": y, "gk": gk, "cd": 0.0, "vx": 0.0, "vy": 0.0})
        for i, (x, y, gk) in enumerate(homes0):
            entities.append({"id": i + 5, "t": 1, "x": W - x, "y": H - y, "hx": W - x, "hy": H - y, "gk": gk, "cd": 0.0, "vx": 0.0, "vy": 0.0})

        control: dict[str, Any] = {}
        for i, p in enumerate(players):
            team = 0 if i < per_team else 1
            idx = i if team == 0 else (i - per_team)
            candidates = [4, 3] if per_team == 2 else [4]
            ent_id = team * 5 + candidates[idx]
            control[str(p.slot)] = ent_id
            for e in entities:
                if e["id"] == ent_id:
                    e["human"] = True

        state: dict[str, Any] = {
            "slots": [p.public() for p in players],
            "entities": entities,
            "control": control,
            "inputs": {str(p.slot): {"x": 0.0, "y": 0.0, "sprint": False} for p in players},
            "ball": {"x": W / 2, "y": H / 2, "vx": 0.0, "vy": 0.0},
            "score": [0, 0],
            "time_left": minutes,
            "freeze": 1.5,
            "celebration": None,
            "finished": False,
            "winners": [],
            "draw": False,
            "reason": "",
            "difficulty": difficulty,
            "per_team": per_team,
            "last_touch": None,
            "events": [],
        }
        return state

    def _controlled_entity(self, state: dict[str, Any], slot: int) -> dict[str, Any] | None:
        ent_id = state["control"].get(str(slot))
        for e in state["entities"]:
            if e["id"] == ent_id:
                return e
        return None

    def on_action(self, state: dict[str, Any], slot: int, action: dict[str, Any]) -> list[dict[str, Any]]:
        if state["finished"]:
            raise GameError("O'yin tugagan")
        kind = action.get("type")
        if kind == "move":
            try:
                x = clamp(float(action.get("x", 0)), -1, 1)
                y = clamp(float(action.get("y", 0)), -1, 1)
            except (TypeError, ValueError):
                raise GameError("Harakat formati noto'g'ri") from None
            state["inputs"][str(slot)] = {"x": x, "y": y, "sprint": bool(action.get("sprint"))}
            return []
        if kind == "kick":
            if state["freeze"] > 0:
                return []
            ent = self._controlled_entity(state, slot)
            if not ent:
                raise GameError("O'yinchi topilmadi")
            self._kick(state, ent, str(action.get("kind", "pass")))
            return []
        if kind == "switch":
            self._switch(state, slot)
            return []
        raise GameError("Noma'lum amal")

    def _switch(self, state: dict[str, Any], slot: int) -> None:
        ent = self._controlled_entity(state, slot)
        if not ent:
            return
        ball = state["ball"]
        options = [e for e in state["entities"] if e["t"] == ent["t"] and not e["gk"]]
        nearest = min(options, key=lambda e: dist(e["x"], e["y"], ball["x"], ball["y"]))
        ent["human"] = False
        nearest["human"] = True
        state["control"][str(slot)] = nearest["id"]

    def _kick(self, state: dict[str, Any], ent: dict[str, Any], kind: str) -> None:
        ball = state["ball"]
        if dist(ent["x"], ent["y"], ball["x"], ball["y"]) > 4.0 or ent["cd"] > 0:
            return
        goal_x = W if ent["t"] == 0 else 0.0
        if kind == "shoot":
            spread = {"easy": 10.0, "normal": 6.0, "hard": 3.0}[state["difficulty"]]
            target_y = clamp(32.0 + random.uniform(-spread, spread), GOAL_Y1 + 2, GOAL_Y2 - 2)
            angle = math.atan2(target_y - ball["y"], goal_x - ball["x"])
            ball["vx"] = math.cos(angle) * SHOOT_SPEED
            ball["vy"] = math.sin(angle) * SHOOT_SPEED
            state["events"].append({"type": "shot", "by": ent["t"]})
        else:
            mates = [e for e in state["entities"] if e["t"] == ent["t"] and e["id"] != ent["id"]]
            if not mates:
                return
            direction = 1 if ent["t"] == 0 else -1
            target = max(mates, key=lambda m: (m["x"] - ent["x"]) * direction + random.uniform(0, 10))
            angle = math.atan2(target["y"] - ball["y"], target["x"] - ball["x"])
            ball["vx"] = math.cos(angle) * PASS_SPEED
            ball["vy"] = math.sin(angle) * PASS_SPEED
        ent["cd"] = 0.45
        state["last_touch"] = ent["t"]
        state["events"].append({"type": "touch", "team": ent["t"]})

    def on_tick(self, state: dict[str, Any], dt: float) -> list[dict[str, Any]]:
        if state["finished"]:
            return []
        state["events"] = []
        if state["celebration"]:
            state["celebration"]["left"] -= dt
            if state["celebration"]["left"] <= 0:
                state["celebration"] = None
                self._reset_positions(state)
                state["freeze"] = 1.0
            return state["events"]
        if state["freeze"] > 0:
            state["freeze"] -= dt
            return state["events"]

        state["time_left"] -= dt
        ball = state["ball"]
        speed_base = SPEED.get(state["difficulty"], 13.5)

        for ent in state["entities"]:
            ent["cd"] = max(0.0, ent["cd"] - dt)

        for slot_str, inp in state["inputs"].items():
            ent = self._controlled_entity(state, int(slot_str))
            if not ent or ent["gk"]:
                continue
            speed = 18.0 if inp["sprint"] else 13.0
            self._move_entity(ent, inp["x"], inp["y"], speed, dt)

        for ent in state["entities"]:
            if not ent.get("human"):
                self._ai_entity(state, ent, speed_base, dt)

        b = state["ball"]
        b["x"] += b["vx"] * dt
        b["y"] += b["vy"] * dt
        friction = 0.988 ** (dt * 20)
        b["vx"] *= friction
        b["vy"] *= friction
        if abs(b["vx"]) < 0.4:
            b["vx"] = 0.0
        if abs(b["vy"]) < 0.4:
            b["vy"] = 0.0

        if b["y"] < 0.6:
            b["y"] = 0.6
            b["vy"] = abs(b["vy"]) * 0.55
        if b["y"] > H - 0.6:
            b["y"] = H - 0.6
            b["vy"] = -abs(b["vy"]) * 0.55

        if b["x"] >= W and GOAL_Y1 < b["y"] < GOAL_Y2:
            return self._goal(state, 0, dt)
        if b["x"] <= 0 and GOAL_Y1 < b["y"] < GOAL_Y2:
            return self._goal(state, 1, dt)
        if b["x"] < -2.0 or b["x"] > W + 2.0:
            b["x"] = clamp(b["x"], 1.0, W - 1.0)
            b["vx"] *= -0.4

        for ent in state["entities"]:
            if ent["gk"]:
                continue
            d = dist(ent["x"], ent["y"], b["x"], b["y"])
            if d < 2.3 and ent["cd"] <= 0:
                direction = 1 if ent["t"] == 0 else -1
                move_x = ent["vx"] if abs(ent["vx"]) > 0.2 else direction * 0.4
                move_y = ent["vy"]
                norm = math.hypot(move_x, move_y) or 1
                b["x"] = ent["x"] + (move_x / norm) * 1.6
                b["y"] = clamp(ent["y"] + (move_y / norm) * 1.6, 0.8, H - 0.8)
                b["vx"] = (move_x / norm) * 13.5
                b["vy"] = (move_y / norm) * 13.5
                state["last_touch"] = ent["t"]
                if not ent.get("human") and ent["cd"] <= 0 and random.random() < 0.45:
                    ent["cd"] = 0.0
                    self._ai_kick(state, ent)
                ent["cd"] = max(ent["cd"], 0.12)

        for i, a in enumerate(state["entities"]):
            for bb in state["entities"][i + 1:]:
                d = dist(a["x"], a["y"], bb["x"], bb["y"])
                if 0 < d < 2.0:
                    push = (2.0 - d) / 2
                    nx = (a["x"] - bb["x"]) / d
                    ny = (a["y"] - bb["y"]) / d
                    a["x"] = clamp(a["x"] + nx * push, 1, W - 1)
                    a["y"] = clamp(a["y"] + ny * push, 1, H - 1)
                    bb["x"] = clamp(bb["x"] - nx * push, 1, W - 1)
                    bb["y"] = clamp(bb["y"] - ny * push, 1, H - 1)

        if state["per_team"] == 1:
            self._auto_switch(state)

        if state["time_left"] <= 0:
            self._finish(state)
        return state["events"]

    def _move_entity(self, ent: dict[str, Any], dx: float, dy: float, speed: float, dt: float) -> None:
        mag = math.hypot(dx, dy)
        if mag < 0.08:
            ent["vx"] = ent["vy"] = 0.0
            return
        dx, dy = dx / mag, dy / mag
        ent["vx"] = dx * speed
        ent["vy"] = dy * speed
        ent["x"] = clamp(ent["x"] + dx * speed * dt, 1.0, W - 1.0)
        ent["y"] = clamp(ent["y"] + dy * speed * dt, 1.0, H - 1.0)

    def _auto_switch(self, state: dict[str, Any]) -> None:
        for slot_str, ent_id in list(state["control"].items()):
            ent = self._controlled_entity(state, int(slot_str))
            if not ent:
                continue
            ball = state["ball"]
            options = [e for e in state["entities"] if e["t"] == ent["t"] and not e["gk"]]
            nearest = min(options, key=lambda e: dist(e["x"], e["y"], ball["x"], ball["y"]))
            if nearest["id"] != ent["id"] and dist(nearest["x"], nearest["y"], ball["x"], ball["y"]) < dist(
                ent["x"], ent["y"], ball["x"], ball["y"]
            ) - 12:
                ent["human"] = False
                nearest["human"] = True
                state["control"][slot_str] = nearest["id"]

    def _ai_entity(self, state: dict[str, Any], ent: dict[str, Any], speed: float, dt: float) -> None:
        ball = state["ball"]
        team = ent["t"]
        direction = 1 if team == 0 else -1
        if ent["gk"]:
            target_x = 3.5 if team == 0 else W - 3.5
            target_y = clamp(ball["y"], GOAL_Y1, GOAL_Y2)
            dx = clamp(target_x - ent["x"], -1, 1)
            dy = clamp(target_y - ent["y"], -1, 1)
            if abs(ent["x"] - target_x) < 0.6:
                dx = 0
            self._move_entity(ent, dx, dy, speed * 0.7, dt)
            return

        teammates = [e for e in state["entities"] if e["t"] == team and not e["gk"]]
        nearest = min(teammates, key=lambda e: dist(e["x"], e["y"], ball["x"], ball["y"]))
        d_ball = dist(ent["x"], ent["y"], ball["x"], ball["y"])

        if ent is nearest or d_ball < 6:
            dx = clamp(ball["x"] - ent["x"], -1, 1)
            dy = clamp(ball["y"] - ent["y"], -1, 1)
            self._move_entity(ent, dx, dy, speed, dt)
            if d_ball < 2.6 and ent["cd"] <= 0:
                self._ai_kick(state, ent)
            return

        shift = clamp(ball["x"] - W / 2, -14, 14) * direction
        target_x = ent["hx"] + shift * 0.5
        target_y = ent["hy"] + (ball["y"] - H / 2) * 0.25
        self._move_entity(ent, clamp(target_x - ent["x"], -1, 1), clamp(target_y - ent["y"], -1, 1), speed * 0.8, dt)

    def _ai_kick(self, state: dict[str, Any], ent: dict[str, Any]) -> None:
        direction = 1 if ent["t"] == 0 else -1
        goal_x = W if ent["t"] == 0 else 0.0
        near_goal = (goal_x - ent["x"]) * direction < 32
        if near_goal and random.random() < 0.85:
            self._kick(state, ent, "shoot")
        elif random.random() < 0.7:
            self._kick(state, ent, "pass")

    def _goal(self, state: dict[str, Any], team: int, dt: float) -> list[dict[str, Any]]:
        state["score"][team] += 1
        state["celebration"] = {"team": team, "left": 2.0}
        state["freeze"] = 0.0
        state["events"].append({"type": "goal", "team": team})
        state["ball"] = {"x": W / 2, "y": H / 2, "vx": 0.0, "vy": 0.0}
        kickoff_team = 1 - team
        state["kickoff_team"] = kickoff_team
        for ent in state["entities"]:
            ent["vx"] = ent["vy"] = 0.0
            if ent["t"] == kickoff_team and not ent["gk"]:
                ent["x"] = W / 2 - 4 if kickoff_team == 0 else W / 2 + 4
                ent["y"] = H / 2
        return state["events"]

    def _reset_positions(self, state: dict[str, Any]) -> None:
        for ent in state["entities"]:
            ent["x"], ent["y"] = ent["hx"], ent["hy"]
            ent["vx"] = ent["vy"] = 0.0
            ent["cd"] = 0.0
        state["ball"] = {"x": W / 2, "y": H / 2, "vx": 0.0, "vy": 0.0}
        for ent in state["entities"]:
            if ent.get("human") and ent["gk"]:
                ent["human"] = False

    def _finish(self, state: dict[str, Any]) -> None:
        state["finished"] = True
        scores = state["score"]
        if scores[0] == scores[1]:
            state["draw"] = True
            state["reason"] = "draw"
            return
        winner_team = 0 if scores[0] > scores[1] else 1
        state["winners"] = [s["slot"] for s in state["slots"] if (s["slot"] < state["per_team"]) == (winner_team == 0)]
        state["reason"] = "goals"

    def result(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "draw": state.get("draw", False),
            "winners": state.get("winners", []),
            "scores": {"0": state["score"][0], "1": state["score"][1]} if "score" in state else {},
            "reason": state.get("reason", ""),
        }

    def view(self, state: dict[str, Any], slot: int | None) -> dict[str, Any]:
        ball = state["ball"]
        return {
            "your_slot": slot,
            "entities": [
                {
                    "id": e["id"],
                    "t": e["t"],
                    "x": round(e["x"], 2),
                    "y": round(e["y"], 2),
                    "gk": e["gk"],
                    "human": bool(e.get("human")),
                }
                for e in state["entities"]
            ],
            "ball": {"x": round(ball["x"], 2), "y": round(ball["y"], 2)},
            "score": state["score"],
            "time": max(0, round(state["time_left"], 1)),
            "freeze": max(0, round(state["freeze"], 1)),
            "celebration": state["celebration"],
            "control": state["control"],
            "per_team": state["per_team"],
            "finished": state["finished"],
            "result": self.result(state) if state["finished"] else None,
            "slots": state["slots"],
        }


MODULE = Football()
