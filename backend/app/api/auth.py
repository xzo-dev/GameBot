from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_session
from ..games.registry import registry
from ..security.auth import AuthError, create_session_token, verify_init_data
from ..services.economy import get_or_create_user
from ..services.profile import build_profile

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/telegram")
async def telegram_login(payload: dict, session: AsyncSession = Depends(get_session)):
    try:
        tg = verify_init_data(str(payload.get("init_data", "")))
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from None
    user = await get_or_create_user(session, tg.id, tg.username, tg.first_name, tg.photo_url)
    if user.is_banned:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Hisob bloklangan")
    user.is_admin = tg.id in settings.admins
    await session.commit()
    token = create_session_token(user.id, user.is_admin)
    return {"token": token, "profile": await build_profile(session, user), "games": registry.catalog()}


@router.post("/dev")
async def dev_login(payload: dict, session: AsyncSession = Depends(get_session)):
    if not settings.dev_mode:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Topilmadi")
    try:
        user_id = int(payload.get("user_id", 700000000 + 1))
        name = str(payload.get("name", "Sinov o'yinchisi"))[:64]
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Noto'g'ri ma'lumot") from None
    user = await get_or_create_user(session, user_id, f"dev{user_id % 10000}", name, None)
    user.is_admin = True
    await session.commit()
    return {"token": create_session_token(user.id, True), "profile": await build_profile(session, user),
            "games": registry.catalog()}
