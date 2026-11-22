from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_session
from ..models import User


class AuthError(Exception):
    pass


@dataclass(slots=True)
class TelegramUser:
    id: int
    username: str | None
    first_name: str
    photo_url: str | None


def verify_init_data(init_data: str) -> TelegramUser:
    """Validate Telegram WebApp initData signature and freshness."""
    if not init_data:
        raise AuthError("initData bo'sh")
    if not settings.bot_token:
        raise AuthError("BOT_TOKEN sozlanmagan")

    pairs = dict(parse_qsl(init_data, strict_parsing=False))
    received_hash = pairs.pop("hash", "")
    if not received_hash:
        raise AuthError("hash yo'q")

    data_check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise AuthError("Imzo noto'g'ri")

    auth_date = int(pairs.get("auth_date", "0") or 0)
    if auth_date and time.time() - auth_date > 172800:
        raise AuthError("initData eskirgan")

    try:
        raw_user = json.loads(pairs.get("user", "{}"))
        user_id = int(raw_user["id"])
    except (KeyError, ValueError, json.JSONDecodeError):
        raise AuthError("Foydalanuvchi ma'lumoti yo'q") from None

    return TelegramUser(
        id=user_id,
        username=(raw_user.get("username") or None),
        first_name=(raw_user.get("first_name") or "O'yinchi")[:128],
        photo_url=raw_user.get("photo_url"),
    )


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def create_session_token(user_id: int, is_admin: bool) -> str:
    payload = {"sub": user_id, "exp": int(time.time()) + settings.session_ttl_hours * 3600, "adm": is_admin}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64e(hmac.new(settings.session_key, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def decode_session_token(token: str) -> dict:
    try:
        body, sig = token.split(".", 1)
    except ValueError:
        raise AuthError("Token formati noto'g'ri") from None
    expected = _b64e(hmac.new(settings.session_key, body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, sig):
        raise AuthError("Token imzosi noto'g'ri")
    try:
        payload = json.loads(_b64d(body))
    except (ValueError, json.JSONDecodeError):
        raise AuthError("Token buzilgan") from None
    if int(payload.get("exp", 0)) < time.time():
        raise AuthError("Sessiya muddati tugagan")
    return payload


async def _user_from_token(token: str, session: AsyncSession) -> User:
    try:
        payload = decode_session_token(token)
        user_id = int(payload["sub"])
    except (AuthError, KeyError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from None

    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Foydalanuvchi topilmadi")
    if user.is_banned:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Hisob bloklangan")
    return user


async def current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Avtorizatsiya kerak")
    return await _user_from_token(authorization[7:], session)


async def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Admin huquqi kerak")
    return user


async def user_from_ws_token(token: str, session: AsyncSession) -> User:
    return await _user_from_token(token, session)
