from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import Track, User
from ..security.auth import current_user

router = APIRouter(prefix="/api/music", tags=["music"])

MAX_BYTES = 5 * 1024 * 1024
ALLOWED = {"audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/ogg": "ogg", "audio/wav": "wav", "audio/webm": "weba"}


def _track(t: Track) -> dict:
    return {"id": t.id, "title": t.title, "artist": t.artist, "url": t.url or f"/api/music/stream/{t.id}",
            "builtin": t.builtin, "uploader_id": t.uploader_id, "active": t.active}


@router.get("")
async def list_tracks(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        select(Track).where(Track.active.is_(True), or_(Track.builtin.is_(True), Track.uploader_id == user.id))
        .order_by(Track.builtin.desc(), Track.id)
    )).scalars().all()
    return {"tracks": [_track(t) for t in rows]}


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    title: str = Form(""),
    artist: str = Form(""),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    mime = file.content_type or ""
    if mime not in ALLOWED:
        raise HTTPException(400, detail="Faqat audio fayl (mp3, m4a, ogg, wav) yuklash mumkin")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, detail="Fayl hajmi 5 MB dan oshmasin")
    if not data:
        raise HTTPException(400, detail="Fayl bo'sh")
    track = Track(
        title=(title.strip() or (file.filename or "Audio")[:60])[:128],
        artist=(artist.strip() or user.first_name)[:128],
        url="",
        uploader_id=user.id,
        mime=mime,
        data=data,
    )
    session.add(track)
    await session.commit()
    await session.refresh(track)
    return {"ok": True, "track": _track(track)}


@router.get("/stream/{track_id}")
async def stream(track_id: int, session: AsyncSession = Depends(get_session)):
    track = await session.get(Track, track_id)
    if not track or not track.active or not track.data:
        raise HTTPException(404, detail="Audio topilmadi")
    return Response(content=track.data, media_type=track.mime, headers={"Cache-Control": "public, max-age=86400"})


@router.delete("/{track_id}")
async def delete(track_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    track = await session.get(Track, track_id)
    if not track or track.uploader_id != user.id or track.builtin:
        raise HTTPException(404, detail="Audio topilmadi")
    await session.delete(track)
    await session.commit()
    return {"ok": True}
