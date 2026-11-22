from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text

from .api import admin, auth, music, profile, ws
from .backup.service import BACKUP_DIR
from .bot.runner import build_application, handle_webhook_update, start_bot, stop_bot
from .config import ROOT, settings
from .database import SessionLocal, engine, init_db
from .database.seed import seed
from .games.registry import registry
from .models import ErrorLog, Setting, User
from .version import APP_VERSION
from .websocket.hub import hub

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("gamehub")

FRONTEND_DIR = ROOT / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with SessionLocal() as session:
        await seed(session)
    registry.discover()
    hub.start()
    application = build_application()
    if application:
        try:
            await start_bot(application)
        except Exception:
            log.exception("Bot ishga tushmadi")
    BACKUP_DIR.mkdir(exist_ok=True)
    log.info("GameHub %s ishga tushdi. O'yinlar: %s", APP_VERSION, ", ".join(m.id for m in registry.all()))
    yield
    await hub.stop()
    if application:
        await stop_bot(application)
    await engine.dispose()


app = FastAPI(title="GameHub", version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(music.router)
app.include_router(admin.router)
app.include_router(ws.router)


@app.get("/api/health")
@app.get("/health", include_in_schema=False)
async def health():
    db_ok = True
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "version": APP_VERSION, "db": db_ok,
            "rooms": len(hub.rooms), "online": len(hub.connections)}


@app.get("/api/status")
async def status():
    async with SessionLocal() as session:
        maint = await session.get(Setting, "maintenance")
        featured = await session.get(Setting, "featured")
        users = await session.scalar(select(func.count(User.id))) or 0
    return {
        "version": APP_VERSION,
        "maintenance": bool((maint.value or {}).get("enabled")) if maint else False,
        "featured": (featured.value or {}).get("games", []) if featured else [],
        "online": len(hub.connections),
        "rooms": len(hub.rooms),
        "users": users,
        "dev": settings.dev_mode,
        "games": registry.catalog(),
    }


@app.post("/api/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    data = await request.json()
    ok = await handle_webhook_update(data, secret)
    return JSONResponse({"ok": ok})


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path)
    try:
        async with SessionLocal() as session:
            session.add(ErrorLog(source=f"{request.method} {request.url.path}",
                                 message=f"{type(exc).__name__}: {exc}"[:2000]))
            await session.commit()
    except Exception:
        pass
    return JSONResponse({"detail": "Server xatosi. Birozdan so'ng qayta urinib ko'ring."}, status_code=500)


@app.get("/")
async def index():
    return RedirectResponse("/app/")


if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
