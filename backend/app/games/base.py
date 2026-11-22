from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class GameError(Exception):
    """Invalid player action, sent back to the client as a readable error."""


@dataclass(slots=True)
class Player:
    slot: int
    id: int
    name: str
    avatar: str | None = None
    bot: bool = False

    def public(self) -> dict[str, Any]:
        return {"slot": self.slot, "id": self.id, "name": self.name, "avatar": self.avatar, "bot": self.bot}


@dataclass(slots=True)
class RoomConfig:
    game_id: str
    mode: str = "room"
    difficulty: str = "normal"
    settings: dict[str, Any] = field(default_factory=dict)
    is_public: bool = True
    capacity: int = 2


class GameModule:
    """Contract every game module implements. States stay server-side."""

    id: str = ""
    title: str = ""
    description: str = ""
    icon: str = "🎮"
    min_players: int = 2
    max_players: int = 2
    realtime: bool = False
    tick_hz: int = 0
    turn_timeout: int = 60
    supports_bot: bool = True
    modes: tuple[str, ...] = ("quick", "room", "bot")
    rules_text: str = ""

    def create_state(self, players: list[Player], settings: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def on_action(self, state: dict[str, Any], slot: int, action: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError

    def on_timeout(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError

    def on_tick(self, state: dict[str, Any], dt: float) -> list[dict[str, Any]]:
        return []

    def bot_move(self, state: dict[str, Any]) -> list[dict[str, Any]] | None:
        return None

    def finished(self, state: dict[str, Any]) -> bool:
        return bool(state.get("finished"))

    def result(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "draw": bool(state.get("draw")),
            "winners": state.get("winners", []),
            "scores": state.get("scores", {}),
            "reason": state.get("reason", ""),
        }

    def view(self, state: dict[str, Any], slot: int | None) -> dict[str, Any]:
        raise NotImplementedError

    def public_view(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.view(state, None)

    def capacity_for(self, requested: int) -> int:
        return max(self.min_players, min(self.max_players, requested))
