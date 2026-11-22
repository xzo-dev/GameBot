from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import GameProfile, InventoryItem, MatchRecord, ShopItem, User, UserAchievement
from ..services.economy import xp_progress
from ..services.matches import ACHIEVEMENTS


async def build_profile(session: AsyncSession, user: User) -> dict[str, Any]:
    level, xp_in, xp_need = xp_progress(user.xp)
    profiles = (await session.execute(select(GameProfile).where(GameProfile.user_id == user.id))).scalars().all()
    inventory = (await session.execute(select(InventoryItem).where(InventoryItem.user_id == user.id))).scalars().all()
    unlocked = {ua.achievement_id for ua in (await session.execute(
        select(UserAchievement).where(UserAchievement.user_id == user.id)
    )).scalars()}
    recent = (await session.execute(
        select(MatchRecord).order_by(MatchRecord.id.desc()).limit(200)
    )).scalars().all()
    history = []
    for m in recent:
        if not any(p.get("id") == user.id for p in (m.players or [])):
            continue
        history.append(
            {
                "id": m.id,
                "game_id": m.game_id,
                "mode": m.mode,
                "result": m.result,
                "scores": m.scores,
                "ended_at": m.ended_at.isoformat() if m.ended_at else None,
            }
        )
        if len(history) >= 10:
            break
    catalog = {i.id: i.name for i in (await session.execute(select(ShopItem))).scalars().all()}
    achievements = [{**a, "unlocked": a["id"] in unlocked} for a in ACHIEVEMENTS]
    return {
        "id": user.id,
        "username": user.username,
        "name": user.first_name,
        "avatar": user.avatar_url,
        "achko": user.achko,
        "coins": user.coins,
        "xp": user.xp,
        "level": level,
        "xp_in": xp_in,
        "xp_need": xp_need,
        "premium": user.premium,
        "is_admin": user.is_admin,
        "games": [
            {"game_id": p.game_id, "rating": p.rating, "wins": p.wins, "losses": p.losses, "draws": p.draws,
             "matches": p.matches, "streak": p.streak}
            for p in profiles
        ],
        "inventory": [
            {"item_id": i.item_id, "name": catalog.get(i.item_id, i.item_id), "equipped": i.equipped}
            for i in inventory
        ],
        "achievements": achievements,
        "history": history,
        "can_daily": user.last_daily is None or user.last_daily != date.today(),
    }
