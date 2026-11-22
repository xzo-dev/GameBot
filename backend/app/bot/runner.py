from __future__ import annotations

import html
import logging

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

from ..config import settings
from ..database import SessionLocal
from ..games.registry import registry
from ..models import GameProfile, User
from ..services.economy import get_or_create_user, xp_progress


log = logging.getLogger("gamehub.bot")

_application: Application | None = None


def _webapp_url() -> str:
    if settings.frontend_url:
        return settings.frontend_url
    if settings.public_base_url:
        return settings.public_base_url.rstrip("/") + "/app/"
    return "https://example.com/app/"


def _keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🎮 GameHub'ni ochish", web_app=WebAppInfo(url=_webapp_url()))]])


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg = update.effective_user
    if not tg:
        return
    async with SessionLocal() as session:
        user = await get_or_create_user(
            session, tg.id, tg.username, tg.first_name or "O'yinchi",
            None,
        )
        await session.commit()
    await update.message.reply_text(
        f"Salom, {html.escape(tg.first_name or 'o\u2018yinchi')}!\n\n"
        "GameHub — Telegram ichidagi premium o'yin platformasi.\n"
        "Shaxmat, UNO, futbol, jang va Jumanji sarguzashti.\n\n"
        "Pastdagi tugma orqali mini ilovani oching.",
        reply_markup=_keyboard(),
    )


async def play(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Mini ilovani oching:", reply_markup=_keyboard())


async def profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg = update.effective_user
    if not tg:
        return
    async with SessionLocal() as session:
        user = await session.get(User, tg.id)
        if not user:
            await update.message.reply_text("Avval /start buyrug'ini yuboring.")
            return
        level, xp_in, xp_need = xp_progress(user.xp)
        profiles = (await session.execute(select(GameProfile).where(GameProfile.user_id == user.id))).scalars().all()
    lines = [
        f"👤 <b>{html.escape(user.first_name)}</b>",
        f"⭐ Daraja: {level} ({xp_in}/{xp_need} XP)",
        f"🪙 Coin: <b>{user.coins}</b>",
        f"🔮 Achko: <b>{user.achko}</b>",
        f"💎 Premium: {'ha' if user.premium else 'yo\u2018q'}",
    ]
    if profiles:
        lines.append("\n🎯 <b>Reytinglar</b>")
        for p in profiles:
            lines.append(f"• {p.game_id}: {p.rating} ({p.wins}W / {p.losses}L)")
    await update.message.reply_text("\n".join(lines), reply_markup=_keyboard())


async def top(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(GameProfile, User).join(User, User.id == GameProfile.user_id)
            .order_by(GameProfile.rating.desc()).limit(10)
        )).all()
    if not rows:
        await update.message.reply_text("Hali reyting bo'sh. Birinchi bo'lib o'ynang!")
        return
    lines = ["🏆 <b>Eng yaxshi o'yinchilar</b>"]
    for i, (p, u) in enumerate(rows, 1):
        lines.append(f"{i}. {html.escape(u.first_name)} — {p.rating} ({p.game_id})")
    await update.message.reply_text("\n".join(lines))


async def admin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg = update.effective_user
    if not tg or tg.id not in settings.admins:
        await update.message.reply_text("Bu buyruq faqat admin uchun.")
        return
    url = settings.public_base_url.rstrip("/") + "/app/#/admin" if settings.public_base_url else _webapp_url() + "#/admin"
    await update.message.reply_text(
        "🛡 Admin panel: mini ilovadagi Profil → Admin bo'limi orqali kirish mumkin.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin panel", web_app=WebAppInfo(url=url))]]),
    )


async def backup_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg = update.effective_user
    if not tg or tg.id not in settings.admins:
        await update.message.reply_text("Bu buyruq faqat admin uchun.")
        return
    from ..backup.service import create_backup

    await update.message.reply_text("💾 Backup yaratilmoqda...")
    async with SessionLocal() as session:
        try:
            result = await create_backup(session, kind="full", actor_id=tg.id)
        except Exception as exc:
            await update.message.reply_text(f"Xatolik: {exc}")
            return
    status = "Telegram kanaliga yuborildi ✅" if result["telegram_sent"] else "Mahalliy saqlandi (kanal sozlanmagan)"
    await update.message.reply_text(f"Backup: {result['file']}\n{status}\nSHA256: {result['checksum'][:16]}...")


def build_application() -> Application | None:
    global _application
    if not settings.bot_token:
        log.warning("BOT_TOKEN yo'q — bot ishga tushmadi")
        return None
    app = Application.builder().token(settings.bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", play))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("backup", backup_cmd))
    _application = app
    return app


def get_application() -> Application | None:
    return _application


async def start_bot(app: Application) -> None:
    await app.initialize()
    if settings.public_base_url and settings.webhook_secret:
        url = settings.public_base_url.rstrip("/") + f"/api/telegram/webhook/{settings.webhook_secret}"
        await app.bot.set_webhook(url=url, secret_token=settings.webhook_secret,
                                  allowed_updates=["message", "callback_query"], drop_pending_updates=True)
        await app.start()
        log.info("Bot webhook rejimida ishga tushdi")
    else:
        await app.updater.start_polling(drop_pending_updates=True, allowed_updates=["message", "callback_query"])
        await app.start()
        log.info("Bot polling rejimida ishga tushdi")


async def stop_bot(app: Application) -> None:
    try:
        if app.updater and app.updater.running:
            await app.updater.stop()
        await app.stop()
        await app.shutdown()
    except Exception:
        log.exception("bot shutdown error")


async def handle_webhook_update(data: dict, secret: str) -> bool:
    app = get_application()
    if not app:
        return False
    expected = settings.webhook_secret
    if not expected or secret != expected:
        return False
    update = Update.de_json(data, app.bot)
    await app.process_update(update)
    return True
