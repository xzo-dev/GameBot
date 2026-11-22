from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import GameProfile, InventoryItem, MatchRecord, User, UserAchievement
from .economy import get_profile, try_award

REWARDS = {
    "win": {"achko": 40, "xp": 30},
    "draw": {"achko": 20, "xp": 15},
    "loss": {"achko": 8, "xp": 8},
}

ACHIEVEMENTS = [
    {"id": "first_win", "title": "Birinchi g'alaba", "description": "Bitta o'yinda g'alaba qozondingiz.", "achko_reward": 25, "icon": "🥇"},
    {"id": "five_wins", "title": "Jangchi", "description": "5 ta g'alaba.", "achko_reward": 60, "icon": "⚔️"},
    {"id": "ten_matches", "title": "Tajribali", "description": "10 ta o'yin o'tkazdingiz.", "achko_reward": 80, "icon": "🎖️"},
    {"id": "level_5", "title": "5-daraja", "description": "5-darajaga yetdingiz.", "achko_reward": 100, "icon": "⭐"},
    {"id": "rich", "title": "Xazina egasi", "description": "1000 achko to'pladingiz.", "achko_reward": 0, "icon": "💎"},
    {"id": "collector", "title": "Kolleksioner", "description": "3 ta buyumga ega bo'ldingiz.", "achko_reward": 50, "icon": "🎨"},
]


def elo(own: int, opp: int, score: float, k: float = 24.0) -> int:
    expected = 1.0 / (1.0 + 10 ** ((opp - own) / 400.0))
    return int(round(own + k * (score - expected)))


async def evaluate_achievements(session: AsyncSession, user: User) -> list[str]:
    unlocked: list[str] = []
    profiles = (await session.execute(select(GameProfile).where(GameProfile.user_id == user.id))).scalars().all()
    wins = sum(p.wins for p in profiles)
    matches = sum(p.matches for p in profiles)
    items = (await session.execute(select(InventoryItem).where(InventoryItem.user_id == user.id))).scalars().all()
    owned = {ua.achievement_id for ua in (await session.execute(
        select(UserAchievement).where(UserAchievement.user_id == user.id)
    )).scalars()}

    candidates: list[str] = []
    if wins >= 1:
        candidates.append("first_win")
    if wins >= 5:
        candidates.append("five_wins")
    if matches >= 10:
        candidates.append("ten_matches")
    if user.level >= 5:
        candidates.append("level_5")
    if user.achko >= 1000:
        candidates.append("rich")
    if len(items) >= 3:
        candidates.append("collector")

    for ach in ACHIEVEMENTS:
        if ach["id"] in candidates and ach["id"] not in owned:
            session.add(UserAchievement(user_id=user.id, achievement_id=ach["id"]))
            await session.flush()
            if ach["achko_reward"]:
                await try_award(
                    session, user.id, "achko", ach["achko_reward"], "achievement",
                    ach["id"], idempotency_key=f"ach:{user.id}:{ach['id']}",
                )
            unlocked.append(ach["id"])
    return unlocked


async def finalize_match(
    session: AsyncSession,
    game_id: str,
    room_code: str | None,
    mode: str,
    slots: list[dict[str, Any]],
    result: dict[str, Any],
    started_at: datetime | None = None,
) -> list[dict[str, Any]]:
    humans = [s for s in slots if s.get("id") and not s.get("bot")]
    winners = set(result.get("winners") or [])
    is_draw = bool(result.get("draw"))
    record = MatchRecord(
        game_id=game_id,
        room_code=room_code,
        mode=mode,
        players=[{"id": s.get("id"), "name": s.get("name"), "bot": s.get("bot")} for s in slots],
        result=result,
        scores=result.get("scores", {}),
        started_at=started_at or datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
    )
    session.add(record)
    await session.flush()

    ratings = {s["slot"]: (await get_profile(session, s["id"], game_id)).rating for s in humans}
    vs_humans = len(humans) >= 2
    rewards: list[dict[str, Any]] = []

    for s in humans:
        slot = s["slot"]
        user = await session.get(User, s["id"])
        if not user:
            continue
        profile = await get_profile(session, s["id"], game_id)
        outcome = "draw" if is_draw else ("win" if slot in winners else "loss")
        profile.matches += 1
        if outcome == "win":
            profile.wins += 1
            profile.streak = max(1, profile.streak + 1)
        elif outcome == "loss":
            profile.losses += 1
            profile.streak = min(-1, profile.streak - 1)
        else:
            profile.draws += 1
            profile.streak = 0

        delta = 0
        if vs_humans:
            opponents = [ratings[o["slot"]] for o in humans if o["slot"] != slot]
            expected_scores = []
            score = 1.0 if outcome == "win" else (0.5 if outcome == "draw" else 0.0)
            avg_opp = sum(opponents) / len(opponents)
            delta = elo(profile.rating, int(avg_opp), score) - profile.rating
            profile.rating = max(100, profile.rating + delta)

        reward = REWARDS[outcome]
        key = f"match:{record.id}:{user.id}"
        a = await try_award(session, user.id, "achko", reward["achko"], "match_reward", outcome, f"{key}:achko")
        x = await try_award(session, user.id, "xp", reward["xp"], "match_reward", outcome, f"{key}:xp")
        unlocked = await evaluate_achievements(session, user)
        rewards.append(
            {
                "user_id": user.id,
                "outcome": outcome,
                "achko": a["balance"],
                "xp": x["balance"],
                "rating_delta": delta,
                "rating": profile.rating,
                "achievements": unlocked,
            }
        )

    await session.flush()
    return rewards
