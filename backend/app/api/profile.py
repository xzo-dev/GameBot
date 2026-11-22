from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..games.registry import registry
from ..models import GameProfile, MatchRecord, Setting, ShopItem, Transaction, User, UserAchievement
from ..security.auth import current_user
from ..services.economy import claim_daily, exchange, get_profile, purchase_item, try_award
from ..services.matches import ACHIEVEMENTS
from ..services.profile import build_profile

router = APIRouter(prefix="/api", tags=["profile"])


@router.get("/me")
async def me(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    return {"profile": await build_profile(session, user), "games": registry.catalog()}


@router.get("/games")
async def games():
    return {"games": registry.catalog()}


@router.get("/leaderboard")
async def leaderboard(game_id: str | None = None, session: AsyncSession = Depends(get_session)):
    stmt = (
        select(GameProfile, User)
        .join(User, User.id == GameProfile.user_id)
        .where(User.is_banned.is_(False), GameProfile.matches > 0)
        .order_by(GameProfile.rating.desc())
        .limit(50)
    )
    if game_id:
        stmt = stmt.where(GameProfile.game_id == game_id)
    rows = (await session.execute(stmt)).all()
    return {
        "entries": [
            {
                "rank": i + 1,
                "user_id": u.id,
                "name": u.first_name,
                "avatar": u.avatar_url,
                "game_id": p.game_id,
                "rating": p.rating,
                "wins": p.wins,
                "losses": p.losses,
                "matches": p.matches,
            }
            for i, (p, u) in enumerate(rows)
        ]
    }


@router.post("/skill")
async def set_skill(payload: dict, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    game_id = str(payload.get("game_id", ""))
    registry.get(game_id)
    try:
        rating = int(payload.get("rating", 0))
    except (TypeError, ValueError):
        raise HTTPException(400, detail="Reyting noto'g'ri") from None
    if not 400 <= rating <= 2400:
        raise HTTPException(400, detail="Reyting 400 dan 2400 gacha bo'lishi kerak")
    profile = await get_profile(session, user.id, game_id)
    profile.rating = rating
    await session.commit()
    return {"ok": True, "rating": rating}


@router.get("/shop")
async def shop(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    items = (await session.execute(select(ShopItem).where(ShopItem.active.is_(True)).order_by(ShopItem.sort, ShopItem.price))).scalars().all()
    from ..models import InventoryItem

    owned = {i.item_id for i in (await session.execute(select(InventoryItem).where(InventoryItem.user_id == user.id))).scalars()}
    equipped = {i.item_id for i in (await session.execute(
        select(InventoryItem).where(InventoryItem.user_id == user.id, InventoryItem.equipped.is_(True))
    )).scalars()}
    return {
        "items": [
            {
                "id": i.id, "category": i.category, "name": i.name, "description": i.description,
                "price": i.price, "asset": i.asset, "premium_only": i.premium_only,
                "owned": i.id in owned, "equipped": i.id in equipped,
            }
            for i in items
        ],
        "coins": user.coins,
    }


@router.post("/shop/buy")
async def shop_buy(payload: dict, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    item = await session.get(ShopItem, str(payload.get("item_id", "")))
    if not item or not item.active:
        raise HTTPException(404, detail="Buyum topilmadi")
    if item.premium_only and not user.premium:
        raise HTTPException(403, detail="Bu buyum faqat Premium uchun")
    try:
        await purchase_item(session, user, item)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(400, detail=str(exc)) from None
    await session.refresh(user)
    refreshed = user
    return {"ok": True, "profile": await build_profile(session, refreshed)}


@router.post("/shop/equip")
async def shop_equip(payload: dict, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    from ..models import InventoryItem, ShopItem

    item_id = str(payload.get("item_id", ""))
    inv = await session.scalar(select(InventoryItem).where(InventoryItem.user_id == user.id, InventoryItem.item_id == item_id))
    if not inv:
        raise HTTPException(404, detail="Buyum sizda yo'q")
    item = await session.get(ShopItem, item_id)
    if not item:
        raise HTTPException(404, detail="Buyum topilmadi")
    same = (await session.execute(
        select(InventoryItem).join(ShopItem, ShopItem.id == InventoryItem.item_id)
        .where(InventoryItem.user_id == user.id, ShopItem.category == item.category)
    )).scalars().all()
    for other in same:
        other.equipped = other.item_id == item_id
    await session.commit()
    return {"ok": True}


@router.post("/exchange")
async def do_exchange(payload: dict, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    try:
        amount = int(payload.get("achko", 0))
        result = await exchange(session, user, amount)
        await session.commit()
    except (TypeError, ValueError) as exc:
        await session.rollback()
        raise HTTPException(400, detail=str(exc)) from None
    await session.refresh(user)
    refreshed = user
    return {"ok": True, **result, "profile": await build_profile(session, refreshed)}


@router.post("/daily")
async def daily(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    try:
        result = await claim_daily(session, user, date.today())
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(400, detail=str(exc)) from None
    await session.refresh(user)
    refreshed = user
    return {"ok": True, **result, "profile": await build_profile(session, refreshed)}


@router.get("/achievements")
async def achievements(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    unlocked = {ua.achievement_id for ua in (await session.execute(
        select(UserAchievement).where(UserAchievement.user_id == user.id)
    )).scalars()}
    return {"achievements": [{**a, "unlocked": a["id"] in unlocked} for a in ACHIEVEMENTS]}


@router.get("/matches")
async def matches(user: User = Depends(current_user), session: AsyncSession = Depends(get_session),
                  limit: int = Query(default=15, le=50)):
    rows = (await session.execute(select(MatchRecord).order_by(MatchRecord.id.desc()).limit(150))).scalars().all()
    result = []
    for m in rows:
        if any(p.get("id") == user.id for p in (m.players or [])):
            result.append({
                "id": m.id, "game_id": m.game_id, "mode": m.mode, "result": m.result,
                "scores": m.scores, "players": m.players,
                "ended_at": m.ended_at.isoformat() if m.ended_at else None,
            })
        if len(result) >= limit:
            break
    return {"matches": result}


@router.get("/transactions")
async def my_transactions(user: User = Depends(current_user), session: AsyncSession = Depends(get_session),
                          limit: int = Query(default=50, le=100)):
    rows = (await session.execute(
        select(Transaction).where(Transaction.user_id == user.id).order_by(Transaction.id.desc()).limit(limit)
    )).scalars().all()
    return {"transactions": [
        {"id": t.id, "currency": t.currency, "amount": t.amount, "balance": t.balance_after,
         "reason": t.reason, "reference": t.reference,
         "created_at": t.created_at.isoformat() if t.created_at else None}
        for t in rows
    ]}


@router.get("/featured")
async def featured(session: AsyncSession = Depends(get_session)):
    setting = await session.get(Setting, "featured")
    games = (setting.value or {}).get("games", []) if setting else []
    return {"featured": games}
