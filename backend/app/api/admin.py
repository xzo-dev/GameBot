from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..backup.service import BACKUP_DIR, apply_restore, backup_history, create_backup, preview_restore
from ..config import settings as app_settings
from ..database import get_session
from ..games.registry import registry
from ..models import BackupLog, ErrorLog, MatchRecord, Report, Setting, ShopItem, Transaction, User
from ..security.auth import admin_user
from ..services.profile import build_profile
from ..websocket.hub import hub

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats")
async def stats(admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    users = await session.scalar(select(func.count(User.id))) or 0
    matches = await session.scalar(select(func.count(MatchRecord.id))) or 0
    achko = await session.scalar(select(func.coalesce(func.sum(User.achko), 0))) or 0
    coins = await session.scalar(select(func.coalesce(func.sum(User.coins), 0))) or 0
    reports = await session.scalar(select(func.count(Report.id)).where(Report.status == "open")) or 0
    return {
        "users": users,
        "matches": matches,
        "achko_total": int(achko),
        "coins_total": int(coins),
        "open_reports": reports,
        "rooms": len(hub.rooms),
        "online": len(hub.connections),
        "queue": hub.matcher.stats(),
        "games": [{"id": m.id, "title": m.title, "enabled": registry.is_enabled(m.id)} for m in registry.all()],
        "version": "1.0.0",
    }


@router.get("/users")
async def users(q: str = "", limit: int = Query(30, le=200), admin: User = Depends(admin_user),
                session: AsyncSession = Depends(get_session)):
    stmt = select(User).order_by(User.last_seen.desc()).limit(limit)
    if q.strip():
        value = q.strip()
        stmt = select(User).where(
            (User.username.ilike(f"%{value}%")) | (User.first_name.ilike(f"%{value}%"))
        ).limit(limit)
        if value.isdigit():
            stmt = select(User).where((User.id == int(value)) | (User.username.ilike(f"%{value}%")))
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "users": [
            {"id": u.id, "name": u.first_name, "username": u.username, "achko": u.achko, "coins": u.coins,
             "level": u.level, "xp": u.xp, "premium": u.premium, "banned": u.is_banned, "admin": u.is_admin,
             "last_seen": u.last_seen.isoformat() if u.last_seen else None}
            for u in rows
        ]
    }


@router.post("/users/{user_id}/balance")
async def adjust_balance(user_id: int, payload: dict, admin: User = Depends(admin_user),
                         session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, detail="Foydalanuvchi topilmadi")
    currency = str(payload.get("currency", "achko"))
    if currency not in ("achko", "coins", "xp"):
        raise HTTPException(400, detail="Valyuta noto'g'ri")
    try:
        amount = int(payload.get("amount", 0))
    except (TypeError, ValueError):
        raise HTTPException(400, detail="Miqdor noto'g'ri") from None
    if amount == 0:
        raise HTTPException(400, detail="Miqdor nol bo'lmasin")
    from ..services.economy import try_award

    try:
        result = await try_award(session, user_id, currency, amount, "admin_adjust", str(admin.id))
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(400, detail=str(exc)) from None
    await session.refresh(user)
    return {"ok": True, "balance": result["balance"], "profile": await build_profile(session, user)}


@router.post("/users/{user_id}/flags")
async def flags(user_id: int, payload: dict, admin: User = Depends(admin_user),
                session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, detail="Foydalanuvchi topilmadi")
    for key, attr in (("banned", "is_banned"), ("premium", "premium"), ("admin", "is_admin")):
        if key in payload:
            if attr == "is_admin" and user_id == app_settings.owner_id and not payload[key]:
                raise HTTPException(400, detail="Egasini adminlikdan chiqarib bo'lmaydi")
            setattr(user, attr, bool(payload[key]))
    await session.commit()
    return {"ok": True}


@router.post("/games/{game_id}/toggle")
async def toggle_game(game_id: str, payload: dict, admin: User = Depends(admin_user)):
    try:
        registry.set_enabled(game_id, bool(payload.get("enabled", True)))
    except Exception as exc:
        raise HTTPException(404, detail=str(exc)) from None
    return {"ok": True, "enabled": registry.is_enabled(game_id)}


@router.get("/shop")
async def admin_shop(admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    items = (await session.execute(select(ShopItem).order_by(ShopItem.category, ShopItem.price))).scalars().all()
    return {"items": [
        {"id": i.id, "category": i.category, "name": i.name, "description": i.description, "price": i.price,
         "asset": i.asset, "premium_only": i.premium_only, "active": i.active, "sort": i.sort}
        for i in items
    ]}


@router.post("/shop")
async def shop_create(payload: dict, admin: User = Depends(admin_user),
                      session: AsyncSession = Depends(get_session)):
    item_id = str(payload.get("id", "")).strip()
    if not item_id or not item_id.isidentifier():
        raise HTTPException(400, detail="ID faqat harflar/raqamlardan iborat bo'lsin")
    if await session.get(ShopItem, item_id):
        raise HTTPException(409, detail="Bunday ID mavjud")
    item = ShopItem(
        id=item_id,
        category=str(payload.get("category", "avatar")),
        name=str(payload.get("name", "Yangi buyum"))[:96],
        description=str(payload.get("description", ""))[:256],
        price=max(0, int(payload.get("price", 100))),
        asset=payload.get("asset") if isinstance(payload.get("asset"), dict) else {},
        premium_only=bool(payload.get("premium_only", False)),
    )
    session.add(item)
    await session.commit()
    return {"ok": True, "id": item_id}


@router.patch("/shop/{item_id}")
async def shop_update(item_id: str, payload: dict, admin: User = Depends(admin_user),
                      session: AsyncSession = Depends(get_session)):
    item = await session.get(ShopItem, item_id)
    if not item:
        raise HTTPException(404, detail="Buyum topilmadi")
    for key in ("category", "name", "description", "price", "premium_only", "active", "sort"):
        if key in payload:
            setattr(item, key, payload[key])
    if isinstance(payload.get("asset"), dict):
        item.asset = payload["asset"]
    await session.commit()
    return {"ok": True}


@router.delete("/shop/{item_id}")
async def shop_delete(item_id: str, admin: User = Depends(admin_user),
                      session: AsyncSession = Depends(get_session)):
    item = await session.get(ShopItem, item_id)
    if not item:
        raise HTTPException(404, detail="Buyum topilmadi")
    item.active = False
    await session.commit()
    return {"ok": True}


@router.get("/reports")
async def reports(status_filter: str = "open", admin: User = Depends(admin_user),
                  session: AsyncSession = Depends(get_session)):
    stmt = select(Report).order_by(Report.id.desc()).limit(100)
    if status_filter in ("open", "resolved"):
        stmt = stmt.where(Report.status == status_filter)
    rows = (await session.execute(stmt)).scalars().all()
    return {"reports": [
        {"id": r.id, "reporter_id": r.reporter_id, "target_id": r.target_id, "room": r.room_code,
         "reason": r.reason, "status": r.status, "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]}


@router.post("/reports/{report_id}/resolve")
async def resolve_report(report_id: int, admin: User = Depends(admin_user),
                         session: AsyncSession = Depends(get_session)):
    report = await session.get(Report, report_id)
    if not report:
        raise HTTPException(404, detail="Shikoyat topilmadi")
    report.status = "resolved"
    await session.commit()
    return {"ok": True}


@router.get("/matches")
async def matches(admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session),
                  limit: int = Query(30, le=100)):
    rows = (await session.execute(select(MatchRecord).order_by(MatchRecord.id.desc()).limit(limit))).scalars().all()
    return {"matches": [
        {"id": m.id, "game_id": m.game_id, "room": m.room_code, "mode": m.mode, "players": m.players,
         "result": m.result, "scores": m.scores, "ended_at": m.ended_at.isoformat() if m.ended_at else None}
        for m in rows
    ]}


@router.get("/transactions")
async def transactions(admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session),
                       limit: int = Query(50, le=200)):
    rows = (await session.execute(select(Transaction).order_by(Transaction.id.desc()).limit(limit))).scalars().all()
    return {"transactions": [
        {"id": t.id, "user_id": t.user_id, "currency": t.currency, "amount": t.amount, "balance": t.balance_after,
         "reason": t.reason, "reference": t.reference, "created_at": t.created_at.isoformat() if t.created_at else None}
        for t in rows
    ]}


@router.get("/settings")
async def get_settings(admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Setting))).scalars().all()
    data = {s.key: s.value for s in rows}
    data.setdefault("maintenance", {"enabled": False})
    return data


@router.patch("/settings")
async def patch_settings(payload: dict, admin: User = Depends(admin_user),
                         session: AsyncSession = Depends(get_session)):
    if "maintenance" in payload:
        setting = await session.get(Setting, "maintenance")
        value = {"enabled": bool(payload["maintenance"].get("enabled"))}
        if setting:
            setting.value = value
        else:
            session.add(Setting(key="maintenance", value=value))
    if "featured" in payload and isinstance(payload["featured"], list):
        setting = await session.get(Setting, "featured")
        value = {"games": [str(g) for g in payload["featured"]]}
        if setting:
            setting.value = value
        else:
            session.add(Setting(key="featured", value=value))
    await session.commit()
    return {"ok": True}


@router.get("/rooms")
async def rooms(admin: User = Depends(admin_user)):
    return {"rooms": [room.public() | {"players_count": len(room.players), "status": room.status}
                      for room in hub.rooms.values()]}


@router.post("/backup")
async def make_backup(payload: dict | None = None, admin: User = Depends(admin_user),
                      session: AsyncSession = Depends(get_session)):
    kind = str((payload or {}).get("kind", "full"))
    if kind not in ("full", "db", "config"):
        raise HTTPException(400, detail="Turi noto'g'ri")
    result = await create_backup(session, kind=kind, actor_id=admin.id)
    return result


@router.get("/backups")
async def backups(admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    return {"backups": await backup_history(session)}


@router.get("/backups/{backup_id}/download")
async def download_backup(backup_id: int, admin: User = Depends(admin_user),
                          session: AsyncSession = Depends(get_session)):
    row = await session.get(BackupLog, backup_id)
    if not row:
        raise HTTPException(404, detail="Backup topilmadi")
    path = BACKUP_DIR / row.file_name
    if not path.exists():
        raise HTTPException(404, detail="Fayl serverda saqlanmagan (Telegramdan yuklab oling)")
    return FileResponse(path, filename=row.file_name)


@router.post("/backup/preview")
async def backup_preview(file: UploadFile = File(...), admin: User = Depends(admin_user),
                         session: AsyncSession = Depends(get_session)):
    blob = await file.read(25 * 1024 * 1024 + 1)
    if len(blob) > 25 * 1024 * 1024:
        raise HTTPException(413, detail="Fayl juda katta")
    try:
        return await preview_restore(session, blob)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from None


@router.post("/backup/restore")
async def backup_restore(payload: dict, admin: User = Depends(admin_user),
                         session: AsyncSession = Depends(get_session)):
    if not payload.get("confirm"):
        raise HTTPException(400, detail="Tasdiqlash kerak")
    try:
        return await apply_restore(session, str(payload.get("token", "")), admin.id)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from None


@router.get("/errors")
async def errors(admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session),
                 limit: int = Query(50, le=200)):
    rows = (await session.execute(select(ErrorLog).order_by(ErrorLog.id.desc()).limit(limit))).scalars().all()
    return {"errors": [
        {"id": e.id, "level": e.level, "source": e.source, "message": e.message,
         "created_at": e.created_at.isoformat() if e.created_at else None}
        for e in rows
    ]}


@router.post("/maintenance")
async def maintenance(payload: dict, admin: User = Depends(admin_user),
                      session: AsyncSession = Depends(get_session)):
    setting = await session.get(Setting, "maintenance")
    value = {"enabled": bool(payload.get("enabled", False))}
    if setting:
        setting.value = value
    else:
        session.add(Setting(key="maintenance", value=value))
    await session.commit()
    return {"ok": True, **value}
