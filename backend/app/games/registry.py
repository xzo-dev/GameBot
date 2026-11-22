from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any

from .base import GameError, GameModule


class GameRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, GameModule] = {}
        self._enabled: dict[str, bool] = {}

    def discover(self) -> None:
        package_dir = Path(__file__).parent
        for info in pkgutil.iter_modules([str(package_dir)]):
            if not info.ispkg or info.name.startswith("_") or info.name == "shared":
                continue
            try:
                mod = importlib.import_module(f"{__package__}.{info.name}.module")
            except ImportError:
                continue
            module = getattr(mod, "MODULE", None)
            if isinstance(module, GameModule) and module.id:
                self._modules[module.id] = module
                self._enabled.setdefault(module.id, True)

    def get(self, game_id: str) -> GameModule:
        module = self._modules.get(game_id)
        if not module:
            raise GameError("O'yin topilmadi")
        if not self._enabled.get(game_id, True):
            raise GameError("Bu o'yin vaqtincha o'chirilgan")
        return module

    def is_enabled(self, game_id: str) -> bool:
        return game_id in self._modules and self._enabled.get(game_id, True)

    def set_enabled(self, game_id: str, enabled: bool) -> None:
        if game_id not in self._modules:
            raise GameError("O'yin topilmadi")
        self._enabled[game_id] = enabled

    def all(self) -> list[GameModule]:
        return list(self._modules.values())

    def catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "id": m.id,
                "title": m.title,
                "description": m.description,
                "icon": m.icon,
                "min_players": m.min_players,
                "max_players": m.max_players,
                "realtime": m.realtime,
                "supports_bot": m.supports_bot,
                "modes": list(m.modes),
                "rules": m.rules_text,
                "enabled": self._enabled.get(m.id, True),
            }
            for m in self._modules.values()
        ]


registry = GameRegistry()
