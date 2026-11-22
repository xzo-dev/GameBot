from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import json
import time
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import ROOT, settings
from ..games.registry import registry
from ..models import (
    Achievement, BackupLog, GameProfile, InventoryItem, MatchRecord, Report, Setting, ShopItem,
    Transaction, User, UserAchievement,
)
from ..security.auth import _b64d, _b64e
from ..version import APP_VERSION, SCHEMA_VERSION

BACKUP_DIR = ROOT / "backups"
RESTORE_TTL = 900

TABLES = [User, GameProfile, Transaction, ShopItem, InventoryItem, MatchRecord, Setting, Report, Achievement, UserAchievement]
TABLE_MODELS = {m.__tablename__: m for m in TABLES}

_previews: dict[str, dict[str, Any]] = {}


def _serialize(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return None
    return value


def _parse(value: Any, column: Any) -> Any:
    py_type = column.type.python_type
    if value is None:
        return None
    if py_type is datetime:
        return datetime.fromisoformat(value)
    if py_type is date:
        return date.fromisoformat(value)
    return value


async def dump_database(session: AsyncSession) -> dict[str, list[dict[str, Any]]]:
    data: dict[str, list[dict[str, Any]]] = {}
    for model in TABLES:
        rows = (await session.execute(select(model))).scalars().all()
        columns = [c for c in model.__table__.columns if c.name != "data"]
        data[model.__tablename__] = [
            {c.name: _serialize(getattr(row, c.name)) for c in columns} for row in rows
        ]
    return data


async def dump_config(session: AsyncSession) -> dict[str, Any]:
    shop = (await session.execute(select(ShopItem))).scalars().all()
    settings_rows = (await session.execute(select(Setting))).scalars().all()
    achievements = (await session.execute(select(Achievement))).scalars().all()
    return {
        "games": registry.catalog(),
        "enabled": {m.id: registry.is_enabled(m.id) for m in registry.all()},
        "shop": [
            {"id": i.id, "category": i.category, "name": i.name, "description": i.description, "price": i.price,
             "asset": i.asset, "premium_only": i.premium_only, "active": i.active, "sort": i.sort}
            for i in shop
        ],
        "settings": {s.key: s.value for s in settings_rows},
        "achievements": [
            {"id": a.id, "title": a.title, "description": a.description, "achko_reward": a.achko_reward, "icon": a.icon}
            for a in achievements
        ],
    }


async def create_backup(session: AsyncSession, kind: str = "full", actor_id: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "app": "GameHub",
        "version": APP_VERSION,
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    if kind in ("full", "config"):
        payload["config"] = await dump_config(session)
    if kind in ("full", "db"):
        payload["database"] = await dump_database(session)

    raw = json.dumps(payload, ensure_ascii=False, indent=1).encode()
    checksum = hashlib.sha256(raw).hexdigest()
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    name = f"gamehub_{kind}_v{APP_VERSION}_{stamp}.zip"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("backup.json", raw)
        zf.writestr("meta.json", json.dumps({"version": APP_VERSION, "checksum": checksum, "kind": kind},
                                            ensure_ascii=False))
    blob = buffer.getvalue()

    BACKUP_DIR.mkdir(exist_ok=True)
    path = BACKUP_DIR / name
    path.write_bytes(blob)

    file_id = await _send_to_telegram(name, blob)
    log = BackupLog(version=APP_VERSION, kind=kind, file_name=name, size=len(blob),
                    telegram_file_id=file_id, checksum=checksum)
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return {
        "id": log.id, "version": APP_VERSION, "kind": kind, "file": name, "size": len(blob),
        "checksum": checksum, "telegram_file_id": file_id,
        "telegram_sent": bool(file_id), "local_path": str(path),
    }


async def _send_to_telegram(name: str, blob: bytes) -> str | None:
    if not settings.bot_token or not settings.backup_channel_id:
        return None
    url = f"https://api.telegram.org/bot{settings.bot_token}/sendDocument"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                url,
                data={"chat_id": settings.backup_channel_id, "caption": f"GameHub backup {name}"},
                files={"document": (name, blob, "application/zip")},
            )
            data = resp.json()
            if data.get("ok"):
                return data["result"]["document"]["file_id"]
    except Exception:
        return None
    return None


def parse_backup(blob: bytes) -> dict[str, Any]:
    if blob[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            raw = zf.read("backup.json")
    else:
        raw = blob
    payload = json.loads(raw)
    if payload.get("app") != "GameHub":
        raise ValueError("Bu GameHub backup fayli emas")
    if int(payload.get("schema_version", 0)) != SCHEMA_VERSION:
        raise ValueError("Backup sxema versiyasi mos emas")
    return payload


async def preview_restore(session: AsyncSession, blob: bytes) -> dict[str, Any]:
    payload = parse_backup(blob)
    checksum = hashlib.sha256(blob).hexdigest()
    db = payload.get("database") or {}
    counts = {name: len(rows) for name, rows in db.items()}
    current = {}
    for name, model in TABLE_MODELS.items():
        current[name] = len((await session.execute(select(model))).scalars().all())
    warnings = []
    if payload.get("kind") == "config":
        warnings.append("Bu faqat konfiguratsiya backupi — foydalanuvchi ma'lumotlari tiklanmaydi.")
    unknown = [name for name in db if name not in TABLE_MODELS]
    if unknown:
        raise ValueError(f"Noma'lum jadvallar: {', '.join(unknown)}")
    token_payload = {"h": checksum, "exp": int(time.time()) + RESTORE_TTL}
    body = _b64e(json.dumps(token_payload, separators=(",", ":")).encode())
    sig = _b64e(hmac.new(settings.session_key, body.encode(), hashlib.sha256).digest())
    _previews[checksum] = {"payload": payload, "ts": time.time()}
    return {
        "token": f"{body}.{sig}",
        "version": payload.get("version"),
        "kind": payload.get("kind"),
        "created_at": payload.get("created_at"),
        "counts": counts,
        "current": current,
        "warnings": warnings,
        "checksum": checksum,
    }


async def apply_restore(session: AsyncSession, token: str, actor_id: int) -> dict[str, Any]:
    try:
        body, sig = token.split(".", 1)
    except ValueError:
        raise ValueError("Tiklash tokeni noto'g'ri") from None
    expected = _b64e(hmac.new(settings.session_key, body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, sig):
        raise ValueError("Tiklash tokeni imzosi noto'g'ri")
    payload = json.loads(_b64d(body))
    if int(payload.get("exp", 0)) < time.time():
        raise ValueError("Tiklash tokeni muddati tugagan")
    checksum = payload.get("h")
    entry = _previews.get(checksum)
    if not entry:
        raise ValueError("Preview topilmadi. Faylni qayta yuklang")
    backup = entry["payload"]

    before = await create_backup(session, kind="db", actor_id=actor_id)
    db = backup.get("database") or {}
    config = backup.get("config")

    try:
        if db:
            for name in reversed(list(TABLE_MODELS)):
                await session.execute(delete(TABLE_MODELS[name]))
            for name, rows in db.items():
                model = TABLE_MODELS[name]
                columns = {c.name: c for c in model.__table__.columns if c.name != "data"}
                for row in rows:
                    clean = {k: _parse(v, columns[k]) for k, v in row.items() if k in columns}
                    session.add(model(**clean))
        if config:
            await _restore_config(session, config)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise ValueError(f"Tiklashda xatolik, o'zgarishlar bekor qilindi: {exc}") from None
    finally:
        _previews.pop(checksum, None)
    return {"ok": True, "restored": {name: len(rows) for name, rows in db.items()},
            "safety_backup": before["file"]}


async def _restore_config(session: AsyncSession, config: dict[str, Any]) -> None:
    for item in config.get("shop", []):
        existing = await session.get(ShopItem, item["id"])
        if existing:
            for key in ("category", "name", "description", "price", "asset", "premium_only", "active", "sort"):
                setattr(existing, key, item.get(key, getattr(existing, key)))
        else:
            session.add(ShopItem(**item))
    for ach in config.get("achievements", []):
        existing = await session.get(Achievement, ach["id"])
        if existing:
            for key in ("title", "description", "achko_reward", "icon"):
                setattr(existing, key, ach.get(key, getattr(existing, key)))
        else:
            session.add(Achievement(**ach))
    for key, value in (config.get("settings") or {}).items():
        existing = await session.get(Setting, key)
        if existing:
            existing.value = value
        else:
            session.add(Setting(key=key, value=value))
    for game_id, enabled in (config.get("enabled") or {}).items():
        try:
            registry.set_enabled(game_id, bool(enabled))
        except Exception:
            pass
    await session.flush()


async def backup_history(session: AsyncSession, limit: int = 20) -> list[dict[str, Any]]:
    rows = (await session.execute(select(BackupLog).order_by(BackupLog.id.desc()).limit(limit))).scalars().all()
    return [
        {"id": b.id, "version": b.version, "kind": b.kind, "file": b.file_name, "size": b.size,
         "checksum": b.checksum, "telegram_file_id": b.telegram_file_id,
         "created_at": b.created_at.isoformat() if b.created_at else None}
        for b in rows
    ]
