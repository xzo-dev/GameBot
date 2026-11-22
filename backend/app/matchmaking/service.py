from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class QueueEntry:
    user_id: int
    game_id: str
    rating: int
    since: float = field(default_factory=time.monotonic)
    settings: dict[str, Any] = field(default_factory=dict)


class Matchmaker:
    def __init__(self) -> None:
        self.queues: dict[str, list[QueueEntry]] = {}
        self.by_user: dict[int, str] = {}

    def add(self, user_id: int, game_id: str, rating: int, settings: dict[str, Any] | None = None) -> bool:
        if user_id in self.by_user:
            return False
        entry = QueueEntry(user_id=user_id, game_id=game_id, rating=rating, settings=settings or {})
        self.queues.setdefault(game_id, []).append(entry)
        self.by_user[user_id] = game_id
        return True

    def remove(self, user_id: int) -> QueueEntry | None:
        game_id = self.by_user.pop(user_id, None)
        if not game_id:
            return None
        queue = self.queues.get(game_id, [])
        for i, entry in enumerate(queue):
            if entry.user_id == user_id:
                return queue.pop(i)
        return None

    def position(self, user_id: int) -> int | None:
        game_id = self.by_user.get(user_id)
        if not game_id:
            return None
        for i, entry in enumerate(self.queues.get(game_id, [])):
            if entry.user_id == user_id:
                return i + 1
        return None

    def find_pairs(self, now: float) -> list[tuple[QueueEntry, QueueEntry, str]]:
        pairs: list[tuple[QueueEntry, QueueEntry, str]] = []
        for game_id, queue in list(self.queues.items()):
            queue.sort(key=lambda e: e.since)
            used: set[int] = set()
            for i, a in enumerate(queue):
                if id(a) in used:
                    continue
                window = min(700, 100 + 90 * (now - a.since))
                best: QueueEntry | None = None
                best_gap = 10**9
                for b in queue[i + 1:]:
                    if id(b) in used:
                        continue
                    gap = abs(a.rating - b.rating)
                    if gap <= max(window, 100) and gap < best_gap:
                        best, best_gap = b, gap
                if best:
                    used.add(id(a))
                    used.add(id(best))
                    pairs.append((a, best, game_id))
            self.queues[game_id] = [e for e in queue if id(e) not in used]
            for a, b, _ in pairs:
                self.by_user.pop(a.user_id, None)
                self.by_user.pop(b.user_id, None)
        return pairs

    def stats(self) -> dict[str, int]:
        return {game_id: len(queue) for game_id, queue in self.queues.items() if queue}
