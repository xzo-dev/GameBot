from __future__ import annotations

import random
from typing import Any

from ..base import GameError, GameModule, Player

COLORS = ("R", "Y", "G", "B")
COLOR_NAMES = {"R": "Qizil", "Y": "Sariq", "G": "Yashil", "B": "Ko'k", "W": "Joker"}


def build_deck() -> list[dict[str, str]]:
    deck: list[dict[str, str]] = []
    for color in COLORS:
        deck.append({"color": color, "value": "0"})
        for value in [str(n) for n in range(1, 10)] + ["skip", "reverse", "draw2"]:
            deck.append({"color": color, "value": value})
            deck.append({"color": color, "value": value})
    for _ in range(4):
        deck.append({"color": "W", "value": "wild"})
        deck.append({"color": "W", "value": "wild4"})
    return deck


def playable(card: dict[str, str], top: dict[str, str], color: str) -> bool:
    return card["color"] == "W" or card["color"] == color or card["value"] == top["value"]


class Uno(GameModule):
    id = "uno"
    title = "UNO"
    description = "2–4 o'yinchi, to'liq navbat tizimi, joker va jarima kartalari."
    icon = "🎴"
    min_players = 2
    max_players = 4
    turn_timeout = 45
    rules_text = "Rang yoki raqam mos kartani tashlang. Bitta karta qolsa — UNO!"

    def create_state(self, players: list[Player], settings: dict[str, Any]) -> dict[str, Any]:
        deck = build_deck()
        random.shuffle(deck)
        count = len(players)
        state: dict[str, Any] = {
            "slots": [p.public() for p in players],
            "hands": [[deck.pop() for _ in range(7)] for _ in range(count)],
            "deck": deck,
            "discard": [],
            "turn": 0,
            "direction": 1,
            "current_color": None,
            "drawn_card": None,
            "drawn_prev": None,
            "finished": False,
            "winners": [],
            "draw": False,
            "reason": "",
            "log": [],
            "scores": {},
            "difficulty": settings.get("difficulty", "normal"),
        }
        first = deck.pop()
        while first["value"] in ("wild4",):
            deck.insert(random.randrange(len(deck)), first)
            first = deck.pop()
        state["discard"].append(first)
        state["current_color"] = first["color"] if first["color"] != "W" else random.choice(COLORS)
        self._log(state, f"O'yin boshlandi: {self._card_name(first)}")
        if first["color"] == "W":
            state["current_color"] = random.choice(COLORS)
        if first["value"] == "skip" and count > 1:
            state["turn"] = self._next(state, 0)
        elif first["value"] == "reverse":
            if count == 2:
                state["turn"] = 1
            else:
                state["direction"] = -1
                state["turn"] = count - 1
        elif first["value"] == "draw2":
            self._draw_cards(state, 0, 2)
            state["turn"] = self._next(state, 0)
        return state

    def _log(self, state: dict[str, Any], text: str) -> None:
        state["log"].append(text)
        state["log"] = state["log"][-30:]

    def _card_name(self, card: dict[str, str]) -> str:
        names = {
            "skip": "O'tkazib yubor",
            "reverse": "Teskari",
            "draw2": "+2",
            "wild": "Joker",
            "wild4": "Joker +4",
        }
        color = COLOR_NAMES.get(card["color"], "")
        return f"{color} {names.get(card['value'], card['value'])}"

    def _next(self, state: dict[str, Any], slot: int) -> int:
        count = len(state["hands"])
        return (slot + state["direction"]) % count

    def _ensure_deck(self, state: dict[str, Any]) -> None:
        if state["deck"]:
            return
        top = state["discard"][-1]
        rest = state["discard"][:-1]
        state["discard"] = [top]
        state["deck"] = rest
        random.shuffle(state["deck"])

    def _draw_cards(self, state: dict[str, Any], slot: int, amount: int) -> None:
        for _ in range(amount):
            self._ensure_deck(state)
            if not state["deck"]:
                return
            state["hands"][slot].append(state["deck"].pop())

    def _take_one(self, state: dict[str, Any], slot: int) -> dict[str, str] | None:
        self._ensure_deck(state)
        if not state["deck"]:
            return None
        card = state["deck"].pop()
        state["hands"][slot].append(card)
        return card

    def on_action(self, state: dict[str, Any], slot: int, action: dict[str, Any]) -> list[dict[str, Any]]:
        if state["finished"]:
            raise GameError("O'yin tugagan")
        if slot != state["turn"]:
            raise GameError("Hozir sizning navbatingiz emas")
        kind = action.get("type")
        hand: list[dict[str, str]] = state["hands"][slot]
        top = state["discard"][-1]

        if kind == "play":
            try:
                index = int(action.get("index", -1))
                card = hand[index]
            except (ValueError, IndexError):
                raise GameError("Karta tanlanmadi") from None
            if not playable(card, top, state["current_color"]):
                raise GameError("Bu kartani tashlab bo'lmaydi")
            if card["value"] == "wild4" and any(c["color"] == state["current_color"] for c in hand):
                raise GameError("Joker +4 faqat rangdagi karta bo'lmasa ishlatiladi")
            if state["drawn_card"] is not None and card is not state["drawn_card"]:
                raise GameError("Faqat yangi olingan kartani o'ynash mumkin")

            hand.pop(index)
            state["drawn_card"] = None
            state["discard"].append(card)
            if card["color"] == "W":
                color = str(action.get("color", "")).upper()
                if color not in COLORS:
                    raise GameError("Joker uchun rang tanlang (R/Y/G/B)")
                state["current_color"] = color
            else:
                state["current_color"] = card["color"]
            self._log(state, f"{state['slots'][slot]['name']}: {self._card_name(card)}")

            if not hand:
                return self._finish(state, slot, card)

            events: list[dict[str, Any]] = [{"type": "play", "by": slot, "card": card}]
            nxt = self._next(state, slot)
            value = card["value"]
            if value == "skip":
                self._log(state, f"{state['slots'][nxt]['name']} navbatni o'tkazib yubordi")
                nxt = self._next(state, nxt)
            elif value == "reverse":
                state["direction"] *= -1
                if len(state["hands"]) == 2:
                    nxt = slot
                else:
                    nxt = self._next(state, slot)
                self._log(state, "Yo'nalish teskari")
            elif value == "draw2":
                self._draw_cards(state, nxt, 2)
                self._log(state, f"{state['slots'][nxt]['name']} +2 oldi")
                nxt = self._next(state, nxt)
            elif value == "wild4":
                self._draw_cards(state, nxt, 4)
                self._log(state, f"{state['slots'][nxt]['name']} +4 oldi")
                nxt = self._next(state, nxt)
            state["turn"] = nxt
            events.append({"type": "turn", "slot": nxt})
            return events

        if kind == "draw":
            if state["drawn_card"] is not None:
                raise GameError("Avval olingan kartani o'ynang yoki navbatni bosing")
            card = self._take_one(state, slot)
            if card is None:
                raise GameError("Kartalar tugadi")
            if playable(card, top, state["current_color"]) and not (
                card["value"] == "wild4" and any(c["color"] == state["current_color"] for c in hand[:-1])
            ):
                state["drawn_card"] = card
                state["drawn_prev"] = top
                return [{"type": "drew", "by": slot, "playable": True}]
            self._log(state, f"{state['slots'][slot]['name']} karta oldi")
            state["turn"] = self._next(state, slot)
            return [{"type": "drew", "by": slot, "playable": False}, {"type": "turn", "slot": state["turn"]}]

        if kind == "pass":
            if state["drawn_card"] is None:
                raise GameError("Navbatni o'tkazish uchun karta oling")
            state["drawn_card"] = None
            state["turn"] = self._next(state, slot)
            self._log(state, f"{state['slots'][slot]['name']} navbatni o'tkazdi")
            return [{"type": "turn", "slot": state["turn"]}]

        raise GameError("Noma'lum amal")

    def _finish(self, state: dict[str, Any], slot: int, card: dict[str, str]) -> list[dict[str, Any]]:
        state["finished"] = True
        state["winners"] = [slot]
        state["scores"] = {str(i): len(h) for i, h in enumerate(state["hands"])}
        state["reason"] = "empty_hand"
        self._log(state, f"{state['slots'][slot]['name']} g'olib bo'ldi!")
        return [{"type": "play", "by": slot, "card": card}, {"type": "finish", "slot": slot}]

    def on_timeout(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        if state["finished"]:
            return []
        slot = state["turn"]
        card = self._take_one(state, slot)
        state["drawn_card"] = None
        state["turn"] = self._next(state, slot)
        self._log(state, f"{state['slots'][slot]['name']} vaqt tugadi, jarima karta")
        return [{"type": "timeout", "by": slot}] + ([{"type": "turn", "slot": state["turn"]}] if not state["finished"] else [])

    def bot_move(self, state: dict[str, Any]) -> list[dict[str, Any]] | None:
        if state["finished"]:
            return None
        slot = state["turn"]
        if not state["slots"][slot]["bot"]:
            return None
        hand = state["hands"][slot]
        top = state["discard"][-1]
        difficulty = state.get("difficulty", "normal")
        legal = [(i, c) for i, c in enumerate(hand) if playable(c, top, state["current_color"])]
        legal = [
            (i, c)
            for i, c in legal
            if not (c["value"] == "wild4" and any(x["color"] == state["current_color"] for x in hand))
        ]
        if state["drawn_card"] is not None:
            card = state["drawn_card"]
            if playable(card, top, state["current_color"]):
                return self.on_action(state, slot, {"type": "play", "index": hand.index(card), "color": self._bot_color(hand)})
            return self.on_action(state, slot, {"type": "pass"})
        if not legal:
            return self.on_action(state, slot, {"type": "draw"})
        if difficulty == "easy":
            index, card = random.choice(legal)
        else:
            opponent_count = min(len(h) for i, h in enumerate(state["hands"]) if i != slot)
            def score(item: tuple[int, dict[str, str]]) -> float:
                _, c = item
                value = 0.0
                if c["value"] == "wild4":
                    value = 60 if opponent_count <= 2 else 10
                elif c["value"] == "draw2":
                    value = 45 if opponent_count <= 3 else 20
                elif c["value"] in ("skip", "reverse"):
                    value = 30
                elif c["value"] == "wild":
                    value = 25
                if c["color"] == self._bot_color(hand):
                    value += 5
                return value + random.uniform(0, 8 if difficulty == "normal" else 2)
            index, card = max(legal, key=score)
        color = str(card["color"])
        if color == "W":
            color = self._bot_color(hand[:-1] if len(hand) > 1 else hand)
        return self.on_action(state, slot, {"type": "play", "index": index, "color": color})

    def _bot_color(self, hand: list[dict[str, str]]) -> str:
        counts: dict[str, int] = {}
        for card in hand:
            if card["color"] in COLORS:
                counts[card["color"]] = counts.get(card["color"], 0) + 1
        if not counts:
            return random.choice(COLORS)
        return max(counts, key=counts.get)

    def view(self, state: dict[str, Any], slot: int | None) -> dict[str, Any]:
        top = state["discard"][-1] if state["discard"] else None
        hand = state["hands"][slot] if slot is not None and slot < len(state["hands"]) else []
        legal = []
        if slot == state["turn"] and top:
            legal = [i for i, c in enumerate(hand) if playable(c, top, state["current_color"])]
            if any(c["value"] == "wild4" for c in hand) and any(c["color"] == state["current_color"] for c in hand):
                legal = [i for i in legal if hand[i]["value"] != "wild4"]
        return {
            "your_slot": slot,
            "turn": state["turn"],
            "direction": state["direction"],
            "current_color": state["current_color"],
            "top": top,
            "hand": hand,
            "counts": [len(h) for h in state["hands"]],
            "legal": legal,
            "drawn": state["drawn_card"] in hand if state["drawn_card"] else False,
            "drawn_index": hand.index(state["drawn_card"]) if state["drawn_card"] in hand else None,
            "finished": state["finished"],
            "result": self.result(state) if state["finished"] else None,
            "log": state["log"][-8:],
            "slots": state["slots"],
        }


MODULE = Uno()
