from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Achievement, Setting, ShopItem, Track
from ..services.matches import ACHIEVEMENTS

SHOP_ITEMS = [
    {"id": "av_neon", "category": "avatar", "name": "Neon niqob", "price": 250, "asset": {"emoji": "🤖", "color": "#7c3aed"}},
    {"id": "av_crown", "category": "avatar", "name": "Oltin toj", "price": 600, "asset": {"emoji": "👑", "color": "#f5c542"}},
    {"id": "av_ghost", "category": "avatar", "name": "Tungi soyа", "price": 400, "asset": {"emoji": "👻", "color": "#a78bfa"}},
    {"id": "av_phoenix", "category": "avatar", "name": "Feniks", "price": 1200, "premium_only": True, "asset": {"emoji": "🔥", "color": "#f97316"}},
    {"id": "fr_purple", "category": "frame", "name": "Ametist ramka", "price": 300, "asset": {"color": "#8b5cf6"}},
    {"id": "fr_gold", "category": "frame", "name": "Oltin ramka", "price": 800, "asset": {"color": "#eab308"}},
    {"id": "fr_ice", "category": "frame", "name": "Muz ramka", "price": 1000, "premium_only": True, "asset": {"color": "#67e8f9"}},
    {"id": "th_void", "category": "theme", "name": "Bo'shliq", "price": 500, "asset": {"accent": "#7c3aed"}},
    {"id": "th_royal", "category": "theme", "name": "Qirollik", "price": 900, "asset": {"accent": "#a855f7"}},
    {"id": "th_aurora", "category": "theme", "name": "Aurora", "price": 1400, "premium_only": True, "asset": {"accent": "#22d3ee"}},
    {"id": "board_neon", "category": "board", "name": "Neon taxta", "price": 450, "asset": {"light": "#3b2a66", "dark": "#1a1030"}},
    {"id": "board_marble", "category": "board", "name": "Marmar taxta", "price": 700, "asset": {"light": "#cfc6e8", "dark": "#4b3d72"}},
    {"id": "board_wood", "category": "board", "name": "Qadimiy yog'och", "price": 380, "asset": {"light": "#8a6a4f", "dark": "#432e1f"}},
    {"id": "card_neon", "category": "cards", "name": "Neon kartalar", "price": 500, "asset": {"accent": "#7c3aed"}},
    {"id": "card_gold", "category": "cards", "name": "Oltin kartalar", "price": 950, "asset": {"accent": "#eab308"}},
    {"id": "fx_glow", "category": "victory", "name": "Nur effekti", "price": 350, "asset": {"effect": "glow"}},
    {"id": "fx_confetti", "category": "victory", "name": "Konfetti", "price": 550, "asset": {"effect": "confetti"}},
    {"id": "fx_lightning", "category": "victory", "name": "Chaqmoq", "price": 1100, "premium_only": True, "asset": {"effect": "lightning"}},
]

BUILTIN_TRACKS = [
    {"title": "Nebula Drift", "artist": "GameHub", "url": "/app/assets/music/nebula.wav"},
    {"title": "Violet Hours", "artist": "GameHub", "url": "/app/assets/music/violet.wav"},
    {"title": "Midnight Arena", "artist": "GameHub", "url": "/app/assets/music/arena.wav"},
]


async def seed(session: AsyncSession) -> None:
    for item in SHOP_ITEMS:
        existing = await session.get(ShopItem, item["id"])
        if existing:
            continue
        session.add(ShopItem(
            id=item["id"], category=item["category"], name=item["name"],
            description=item.get("description", ""), price=item["price"],
            asset=item.get("asset", {}), premium_only=item.get("premium_only", False),
        ))
    for ach in ACHIEVEMENTS:
        if not await session.get(Achievement, ach["id"]):
            session.add(Achievement(**ach))
    for track in BUILTIN_TRACKS:
        exists = await session.scalar(select(Track).where(Track.url == track["url"]))
        if not exists:
            session.add(Track(title=track["title"], artist=track["artist"], url=track["url"], builtin=True))
    if not await session.get(Setting, "maintenance"):
        session.add(Setting(key="maintenance", value={"enabled": False}))
    if not await session.get(Setting, "featured"):
        session.add(Setting(key="featured", value={"games": ["football", "chess", "uno"]}))
    await session.commit()
