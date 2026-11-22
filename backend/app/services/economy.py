from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import GameProfile, InventoryItem, Transaction, User, UserAchievement

CURRENCIES = {"achko", "coins", "xp"}
EXCHANGE_RATE = 5
DAILY_ACHKO = 50
DAILY_XP = 10


def level_from_xp(xp: int) -> int:
    level = 1
    need = 100
    total = 0
    while xp >= total + need and level < 200:
        total += need
        level += 1
        need = 100 + (level - 1) * 60
    return level


def xp_progress(xp: int) -> tuple[int, int, int]:
    level = 1
    need = 100
    total = 0
    while xp >= total + need and level < 200:
        total += need
        level += 1
        need = 100 + (level - 1) * 60
    return level, xp - total, need


async def get_or_create_user(
    session: AsyncSession, user_id: int, username: str | None, first_name: str, avatar: str | None
) -> User:
    user = await session.get(User, user_id)
    if user:
        user.username = username or user.username
        user.first_name = first_name or user.first_name
        user.avatar_url = avatar or user.avatar_url
        return user
    user = User(id=user_id, username=username, first_name=first_name, avatar_url=avatar, achko=0, coins=0, xp=0)
    session.add(user)
    await session.flush()
    return user


async def get_profile(session: AsyncSession, user_id: int, game_id: str) -> GameProfile:
    result = await session.execute(
        select(GameProfile).where(GameProfile.user_id == user_id, GameProfile.game_id == game_id)
    )
    profile = result.scalar_one_or_none()
    if profile:
        return profile
    profile = GameProfile(user_id=user_id, game_id=game_id)
    session.add(profile)
    await session.flush()
    return profile


async def try_award(
    session: AsyncSession,
    user_id: int,
    currency: str,
    amount: int,
    reason: str,
    reference: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Atomically move a balance. Negative amounts fail when balance is insufficient."""
    if currency not in CURRENCIES or amount == 0:
        raise ValueError("Noto'g'ri tranzaksiya")

    if idempotency_key:
        existing = await session.scalar(select(Transaction).where(Transaction.idempotency_key == idempotency_key))
        if existing:
            return {"applied": False, "balance": existing.balance_after, "idempotent": True}

    column = {"achko": User.achko, "coins": User.coins, "xp": User.xp}[currency]
    stmt = update(User).where(User.id == user_id)
    stmt = stmt.where(column + amount >= 0) if amount < 0 else stmt
    stmt = stmt.values(**{currency: column + amount}).returning(column)
    balance = await session.scalar(stmt)
    if balance is None:
        raise ValueError("Balans yetarli emas")

    if currency == "xp":
        await session.execute(update(User).where(User.id == user_id).values(level=level_from_xp(balance)))
        await session.flush()

    tx = Transaction(
        user_id=user_id,
        currency=currency,
        amount=amount,
        balance_after=balance,
        reason=reason,
        reference=reference,
        idempotency_key=idempotency_key,
    )
    session.add(tx)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(select(Transaction).where(Transaction.idempotency_key == idempotency_key))
        return {"applied": False, "balance": existing.balance_after if existing else balance, "idempotent": True}
    return {"applied": True, "balance": balance, "idempotent": False}


async def purchase_item(session: AsyncSession, user: User, item) -> dict[str, Any]:
    owned = await session.scalar(
        select(InventoryItem).where(InventoryItem.user_id == user.id, InventoryItem.item_id == item.id)
    )
    if owned:
        raise ValueError("Bu buyum allaqachon sizda")
    result = await try_award(session, user.id, "coins", -item.price, "shop_purchase", item.id)
    session.add(InventoryItem(user_id=user.id, item_id=item.id))
    await session.flush()
    return {"ok": True, "balance": result["balance"]}


async def exchange(session: AsyncSession, user: User, achko_amount: int) -> dict[str, Any]:
    if achko_amount < EXCHANGE_RATE or achko_amount % EXCHANGE_RATE:
        raise ValueError(f"Miqdor {EXCHANGE_RATE} ga karrali bo'lishi kerak")
    coins = achko_amount // EXCHANGE_RATE
    key = f"exchange:{user.id}:{achko_amount}:{user.achko}"
    await try_award(session, user.id, "achko", -achko_amount, "exchange_out", "coins", key)
    await try_award(session, user.id, "coins", coins, "exchange_in", "achko", f"{key}:in")
    return {"ok": True, "coins": coins}


async def claim_daily(session: AsyncSession, user: User, today) -> dict[str, Any]:
    if user.last_daily == today:
        raise ValueError("Bugungi mukofot allaqachon olingan")
    await session.execute(update(User).where(User.id == user.id).values(last_daily=today))
    key = f"daily:{user.id}:{today.isoformat()}"
    a = await try_award(session, user.id, "achko", DAILY_ACHKO, "daily", idempotency_key=f"{key}:achko")
    b = await try_award(session, user.id, "xp", DAILY_XP, "daily", idempotency_key=f"{key}:xp")
    return {"achko": a["balance"], "xp": b["balance"]}


async def sync_level(session: AsyncSession, user_id: int) -> int:
    xp = await session.scalar(select(User.xp).where(User.id == user_id)) or 0
    level = level_from_xp(xp)
    await session.execute(update(User).where(User.id == user_id).values(level=level))
    return level
