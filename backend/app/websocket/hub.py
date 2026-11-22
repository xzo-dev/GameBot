from __future__ import annotations

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket
from sqlalchemy import select

from ..database import SessionLocal
from ..games.base import GameError, Player
from ..games.registry import registry
from ..matchmaking.service import Matchmaker
from ..models import GameProfile, Report, User
from ..services.matches import finalize_match
from ..services.economy import xp_progress

log = logging.getLogger("gamehub.hub")

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MAX_CHAT = 300
CHAT_WINDOW = 5.0
CHAT_LIMIT = 4
REALTIME_GRACE = 45.0
BOT_NAMES = ["Bot Nodir", "Bot Zilola", "Bot Temur", "Bot Aziza"]


@dataclass
class Connection:
    ws: WebSocket
    user_id: int
    name: str
    avatar: str | None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send(self, payload: dict[str, Any]) -> None:
        try:
            async with self.lock:
                await self.ws.send_json(payload)
        except Exception:
            pass


@dataclass
class Room:
    code: str
    game_id: str
    module: Any
    mode: str
    is_public: bool
    capacity: int
    host_id: int
    difficulty: str
    settings: dict[str, Any]
    players: list[Player] = field(default_factory=list)
    conns: dict[int, Connection] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    status: str = "waiting"
    created: float = field(default_factory=time.monotonic)
    started_at: Any = None
    turn_deadline: float = 0.0
    bot_due: float = 0.0
    chat: list[dict[str, Any]] = field(default_factory=list)
    chat_times: dict[int, list[float]] = field(default_factory=dict)
    mutes: dict[int, set[int]] = field(default_factory=dict)
    offline: dict[int, float] = field(default_factory=dict)
    finalized: bool = False
    finished_at: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    snapshot_interval: float = 0.1
    bot_active: bool = False

    @property
    def human_ids(self) -> set[int]:
        return {p.id for p in self.players if not p.bot}

    def player_for(self, user_id: int) -> Player | None:
        for p in self.players:
            if p.id == user_id:
                return p
        return None

    def slot_of(self, user_id: int) -> int | None:
        p = self.player_for(user_id)
        return p.slot if p else None

    def public(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "game_id": self.game_id,
            "status": self.status,
            "players": [p.public() for p in self.players if not p.bot],
            "capacity": self.capacity,
            "host_id": self.host_id,
            "public": self.is_public,
            "mode": self.mode,
            "settings": self.settings,
            "difficulty": self.difficulty,
        }


class Hub:
    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}
        self.user_room: dict[int, str] = {}
        self.connections: dict[int, Connection] = {}
        self.matcher = Matchmaker()
        self._task: asyncio.Task | None = None
        self._last_tick = time.monotonic()
        self._last_match = 0.0
        self._bot_seq = 0

    def start(self) -> None:
        if not self._task:
            self._task = asyncio.create_task(self._loop(), name="hub-loop")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def _new_code(self) -> str:
        for _ in range(200):
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(5))
            if code not in self.rooms:
                return code
        raise GameError("Xona kodi yaratilmadi")

    async def connect(self, user: User, ws: WebSocket) -> Connection:
        old = self.connections.get(user.id)
        if old:
            await old.send({"type": "session_replaced"})
        conn = Connection(ws=ws, user_id=user.id, name=user.first_name, avatar=user.avatar_url)
        self.connections[user.id] = conn

        code = self.user_room.get(user.id)
        room = self.rooms.get(code) if code else None
        if room and user.id in room.conns:
            room.conns[user.id] = conn
            room.offline.pop(user.id, None)
            await conn.send({"type": "room_state", "room": room.public(), "chat": self._chat_for(room, user.id)})
            if room.status == "playing":
                await conn.send({"type": "game_state", "state": room.module.view(room.state, room.slot_of(user.id)),
                                 "game_id": room.game_id, "code": room.code})
            self._system(room, f"{user.first_name} qaytdi")
        return conn

    async def disconnect(self, user_id: int) -> None:
        self.connections.pop(user_id, None)
        code = self.user_room.get(user_id)
        room = self.rooms.get(code) if code else None
        if room:
            conn = room.conns.pop(user_id, None)
            if conn is None:
                return
            if room.status == "waiting":
                await self.leave(user_id, silent=True)
                return
            room.offline[user_id] = time.monotonic()
            self._system(room, f"{conn.name} aloqasi uzildi")

    async def send(self, user_id: int, payload: dict[str, Any]) -> None:
        conn = self.connections.get(user_id)
        if conn:
            await conn.send(payload)

    def _system(self, room: Room, text: str) -> None:
        message = {"type": "chat", "system": True, "text": text, "ts": time.time()}
        self._remember(room, message)
        self.broadcast(room, message)

    def _remember(self, room: Room, message: dict[str, Any]) -> None:
        room.chat.append(message)
        room.chat = room.chat[-80:]

    def _chat_for(self, room: Room, user_id: int) -> list[dict[str, Any]]:
        muted = room.mutes.get(user_id, set())
        return [m for m in room.chat if m.get("system") or m.get("user_id") not in muted]

    def broadcast(self, room: Room, payload: dict[str, Any], exclude: int | None = None) -> None:
        for user_id, conn in list(room.conns.items()):
            if user_id != exclude:
                asyncio.create_task(conn.send(payload))

    def _broadcast_state(self, room: Room, events: list[dict[str, Any]] | None = None) -> None:
        if not room.state:
            return
        for user_id, conn in list(room.conns.items()):
            slot = room.slot_of(user_id)
            try:
                view = room.module.view(room.state, slot)
            except Exception:
                log.exception("view failed")
                continue
            asyncio.create_task(conn.send({"type": "game_state", "state": view, "events": events or [],
                                           "game_id": room.game_id, "code": room.code}))

    async def _send_room(self, room: Room, user_id: int) -> None:
        await self.send(user_id, {"type": "room_state", "room": room.public(), "chat": self._chat_for(room, user_id)})

    async def handle(self, conn: Connection, data: dict[str, Any]) -> None:
        kind = data.get("type")
        user = await self._load_user(conn.user_id)
        if not user:
            await conn.send({"type": "error", "message": "Foydalanuvchi topilmadi"})
            return
        try:
            if kind == "ping":
                await conn.send({"type": "pong", "ts": time.time()})
            elif kind == "create_room":
                await self._create(conn, user, data)
            elif kind == "join_room":
                await self._join(conn, user, str(data.get("code", "")).strip().upper())
            elif kind == "quick_match":
                await self._quick(conn, user, data)
            elif kind == "cancel_match":
                self.matcher.remove(user.id)
                await conn.send({"type": "queue_left"})
            elif kind == "start":
                await self._start_request(conn, user)
            elif kind == "leave":
                await self.leave(user.id)
            elif kind == "action":
                await self._action(conn, user, data.get("action") or {})
            elif kind == "chat":
                await self._chat(conn, user, data)
            elif kind == "rooms":
                await conn.send({"type": "rooms", "rooms": self.public_rooms(data.get("game_id")),
                                 "queues": self.matcher.stats()})
            elif kind == "report":
                await self._report(conn, data)
            elif kind == "mute":
                await self._mute(conn, data)
            elif kind == "sync":
                await self._sync(conn, user)
            else:
                await conn.send({"type": "error", "message": "Noma'lum buyruq"})
        except GameError as exc:
            await conn.send({"type": "error", "message": str(exc)})
        except Exception:
            log.exception("ws handle failed")
            await conn.send({"type": "error", "message": "Kutilmagan xatolik"})

    async def _load_user(self, user_id: int) -> User | None:
        async with SessionLocal() as session:
            return await session.get(User, user_id)

    async def _sync(self, conn: Connection, user: User) -> None:
        await conn.send({"type": "profile", "user": self._profile_payload(user)})

    def _profile_payload(self, user: User) -> dict[str, Any]:
        level, xp_in, xp_need = xp_progress(user.xp)
        return {
            "id": user.id,
            "name": user.first_name,
            "username": user.username,
            "avatar": user.avatar_url,
            "achko": user.achko,
            "coins": user.coins,
            "xp": user.xp,
            "level": level,
            "xp_in": xp_in,
            "xp_need": xp_need,
            "premium": user.premium,
            "is_admin": user.is_admin,
        }

    async def _create(self, conn: Connection, user: User, data: dict[str, Any]) -> None:
        game_id = str(data.get("game_id", ""))
        module = registry.get(game_id)
        if self.user_room.get(user.id):
            await self.leave(user.id)
        capacity = module.capacity_for(int(data.get("capacity", module.min_players) or module.min_players))
        mode = str(data.get("mode", "room"))
        difficulty = str(data.get("difficulty", "normal"))
        if difficulty not in ("easy", "normal", "hard"):
            difficulty = "normal"
        settings = data.get("settings") if isinstance(data.get("settings"), dict) else {}
        room = Room(
            code=self._new_code(),
            game_id=game_id,
            module=module,
            mode=mode,
            is_public=bool(data.get("public", True)),
            capacity=capacity,
            host_id=user.id,
            difficulty=difficulty,
            settings=settings,
        )
        room.players.append(Player(slot=0, id=user.id, name=user.first_name, avatar=user.avatar_url))
        room.conns[user.id] = conn
        self.rooms[room.code] = room
        self.user_room[user.id] = room.code
        self._remember(room, {"type": "chat", "system": True, "text": "Xona yaratildi", "ts": time.time()})
        await self._send_room(room, user.id)
        await conn.send({"type": "room_created", "code": room.code})
        if mode == "bot":
            await self._start(room)

    async def _join(self, conn: Connection, user: User, code: str) -> None:
        room = self.rooms.get(code)
        if not room:
            raise GameError("Bunday kodli xona topilmadi")
        if user.id in room.conns and room.status == "playing":
            room.conns[user.id] = conn
            room.offline.pop(user.id, None)
            await self._send_room(room, user.id)
            await conn.send({"type": "game_state", "state": room.module.view(room.state, room.slot_of(user.id)),
                             "game_id": room.game_id, "code": room.code})
            return
        if room.status == "playing" and room.player_for(user.id):
            room.conns[user.id] = conn
            room.offline.pop(user.id, None)
            self.user_room[user.id] = code
            await self._send_room(room, user.id)
            await conn.send({"type": "game_state", "state": room.module.view(room.state, room.slot_of(user.id)),
                             "game_id": room.game_id, "code": room.code})
            return
        if room.status != "waiting":
            raise GameError("Xona allaqachon boshlangan")
        if user.id not in {p.id for p in room.players} and len(room.players) >= room.capacity:
            raise GameError("Xona to'la")
        current = self.user_room.get(user.id)
        if current and current != code:
            await self.leave(user.id)
        should_start = False
        async with room.lock:
            if user.id not in {p.id for p in room.players}:
                room.players.append(
                    Player(slot=len(room.players), id=user.id, name=user.first_name, avatar=user.avatar_url)
                )
                self._system(room, f"{user.first_name} xonaga qo'shildi")
            room.conns[user.id] = conn
            self.user_room[user.id] = code
            await self._send_room(room, user.id)
            self._broadcast_room_state(room)
            should_start = len(room.players) >= room.capacity
        if should_start:
            await self._start(room)

    def _broadcast_room_state(self, room: Room) -> None:
        for user_id in list(room.conns):
            asyncio.create_task(self.send(user_id, {"type": "room_state", "room": room.public(),
                                                    "chat": self._chat_for(room, user_id)}))

    async def _quick(self, conn: Connection, user: User, data: dict[str, Any]) -> None:
        game_id = str(data.get("game_id", ""))
        module = registry.get(game_id)
        if self.user_room.get(user.id):
            await self.leave(user.id)
        async with SessionLocal() as session:
            profile = await session.scalar(
                select(GameProfile).where(GameProfile.user_id == user.id, GameProfile.game_id == game_id)
            )
            rating = profile.rating if profile else 1000
        settings = data.get("settings") if isinstance(data.get("settings"), dict) else {}
        if not self.matcher.add(user.id, game_id, rating, settings):
            await conn.send({"type": "queue", "status": "searching", "game_id": game_id,
                             "position": self.matcher.position(user.id) or 1})
            return
        await conn.send({"type": "queue", "status": "searching", "game_id": game_id, "position": 1})
        await self._match_now()

    async def _match_now(self) -> None:
        pairs = self.matcher.find_pairs(time.monotonic())
        for a, b, game_id in pairs:
            module = registry.get(game_id)
            room = Room(
                code=self._new_code(),
                game_id=game_id,
                module=module,
                mode="quick",
                is_public=False,
                capacity=module.min_players,
                host_id=a.user_id,
                difficulty="normal",
                settings=a.settings,
            )
            for i, uid in enumerate((a.user_id, b.user_id)):
                user = await self._load_user(uid)
                if not user or user.is_banned or uid not in self.connections:
                    continue
                room.players.append(Player(slot=len(room.players), id=uid, name=user.first_name, avatar=user.avatar_url))
                room.conns[uid] = self.connections[uid]
                self.user_room[uid] = room.code
            if len(room.players) < module.min_players:
                for uid in room.conns:
                    self.user_room.pop(uid, None)
                continue
            self.rooms[room.code] = room
            for uid in room.conns:
                await self.send(uid, {"type": "match_found", "code": room.code, "game_id": game_id})
            self._system(room, "Raqib topildi. O'yin boshlanmoqda")
            await self._start(room, fill_only=False)

    async def _start_request(self, conn: Connection, user: User) -> None:
        code = self.user_room.get(user.id)
        room = self.rooms.get(code) if code else None
        if not room:
            raise GameError("Xona topilmadi")
        if room.host_id != user.id:
            raise GameError("Faqat xona egasi boshlashi mumkin")
        await self._start(room)

    async def _start(self, room: Room, fill_only: bool = True) -> None:
        async with room.lock:
            if room.status != "waiting":
                return
            module = room.module
            if room.mode == "bot" and len(room.players) < room.capacity:
                self._fill_bots(room, target=room.capacity)
            if len(room.players) < module.min_players:
                raise GameError(f"Kamida {module.min_players} o'yinchi kerak")
            if room.game_id == "football":
                if len(room.players) % 2:
                    self._fill_bots(room, target=len(room.players) + 1)
                if len(room.players) > 4:
                    raise GameError("Futbol 2 yoki 4 o'yinchi bilan o'ynaladi")
            if len(room.players) > room.capacity and room.mode != "bot":
                raise GameError("Xona to'la")
            settings = dict(room.settings)
            settings["difficulty"] = room.difficulty
            room.players.sort(key=lambda p: (p.bot, p.slot))
            for i, p in enumerate(room.players):
                p.slot = i
            room.state = module.create_state(room.players, settings)
            room.status = "playing"
            room.started_at = datetime.now(timezone.utc)
            self._set_deadline(room)
            self._schedule_bot(room)
            self._system(room, "O'yin boshlandi")
            self._broadcast_room_state(room)
            self._broadcast_state(room)

    def _fill_bots(self, room: Room, target: int | None = None) -> None:
        if not room.module.supports_bot:
            return
        if target is None:
            target = room.capacity
        while len(room.players) < target:
            self._bot_seq += 1
            name = BOT_NAMES[(self._bot_seq - 1) % len(BOT_NAMES)]
            bot = Player(slot=len(room.players), id=-900000 - self._bot_seq, name=name, bot=True)
            room.players.append(bot)

    def _set_deadline(self, room: Room) -> None:
        if room.module.realtime or not room.state:
            room.turn_deadline = 0.0
            return
        timeout = float(room.state.get("turn_timeout") or room.module.turn_timeout)
        room.turn_deadline = time.monotonic() + timeout

    def _schedule_bot(self, room: Room) -> None:
        room.bot_due = 0.0
        if room.module.realtime or not room.state:
            return
        turn = room.state.get("turn")
        if turn is None:
            return
        for p in room.players:
            if p.slot == turn and p.bot:
                room.bot_due = time.monotonic() + 0.7
                return

    async def _action(self, conn: Connection, user: User, action: dict[str, Any]) -> None:
        code = self.user_room.get(user.id)
        room = self.rooms.get(code) if code else None
        if not room or room.status != "playing":
            raise GameError("Faol o'yin topilmadi")
        async with room.lock:
            slot = room.slot_of(user.id)
            if slot is None:
                raise GameError("Siz bu o'yinda emassiz")
            events = room.module.on_action(room.state, slot, action)
            if events or not room.module.realtime:
                self._broadcast_state(room, events)
            if room.module.finished(room.state):
                await self._finish(room)
            else:
                self._set_deadline(room)
                self._schedule_bot(room)

    async def _match_bot_turn(self, room: Room) -> None:
        if room.bot_active or room.module.realtime or room.status != "playing":
            return
        room.bot_active = True
        try:
            guard = 0
            while room.status == "playing" and not room.module.finished(room.state):
                turn = room.state.get("turn")
                player = next((p for p in room.players if p.slot == turn), None)
                if not player or not player.bot:
                    break
                guard += 1
                if guard > 30:
                    break
                await asyncio.sleep(0.55)
                async with room.lock:
                    if room.status != "playing":
                        return
                    events = room.module.bot_move(room.state)
                    if events is None:
                        break
                    self._broadcast_state(room, events)
                    if room.module.finished(room.state):
                        await self._finish(room)
                        return
                    self._set_deadline(room)
        finally:
            room.bot_active = False

    async def _finish(self, room: Room) -> None:
        if room.finalized:
            return
        room.finalized = True
        room.status = "finished"
        room.finished_at = time.monotonic()
        result = room.module.result(room.state)
        self._system(room, "O'yin tugadi")
        self._broadcast_state(room, [{"type": "finish", "result": result}])

        rewards: list[dict[str, Any]] = []
        match_id = None
        try:
            async with SessionLocal() as session:
                rewards = await finalize_match(
                    session,
                    room.game_id,
                    room.code,
                    room.mode,
                    [p.public() for p in room.players],
                    result,
                    room.started_at,
                )
                await session.commit()
        except Exception:
            log.exception("match persist failed")

        for entry in rewards:
            uid = entry["user_id"]
            user = await self._load_user(uid)
            payload = {"type": "match_result", "result": result, "rewards": entry,
                       "profile": self._profile_payload(user) if user else None}
            await self.send(uid, payload)
        self.broadcast(room, {"type": "room_status", "status": "finished"})

    async def leave(self, user_id: int, silent: bool = False) -> None:
        code = self.user_room.pop(user_id, None)
        self.matcher.remove(user_id)
        if not code:
            if not silent:
                await self.send(user_id, {"type": "left"})
            return
        room = self.rooms.get(code)
        if not room:
            if not silent:
                await self.send(user_id, {"type": "left"})
            return
        room.conns.pop(user_id, None)
        player = room.player_for(user_id)
        if room.status == "waiting":
            room.players = [p for p in room.players if p.id != user_id]
            for i, p in enumerate(room.players):
                p.slot = i
            if not room.players:
                self.rooms.pop(room.code, None)
            else:
                if room.host_id == user_id:
                    room.host_id = next(p.id for p in room.players if not p.bot)
                self._system(room, f"{player.name if player else 'Oʻyinchi'} chiqdi")
                self._broadcast_room_state(room)
        elif room.status == "playing" and player and not player.bot:
            self._system(room, f"{player.name} o'yinni tark etdi")
            others = [p.slot for p in room.players if p.slot != player.slot]
            if others:
                room.state["finished"] = True
                room.state["draw"] = False
                room.state["reason"] = "forfeit"
                room.state["winners"] = others
                try:
                    await self._finish(room)
                except Exception:
                    log.exception("forfeit finish failed")
            else:
                room.status = "finished"
                room.finished_at = time.monotonic()
                room.finalized = True
        if not silent:
            await self.send(user_id, {"type": "left"})
        if room.status == "finished" and not room.conns:
            self.rooms.pop(room.code, None)

    async def _chat(self, conn: Connection, user: User, data: dict[str, Any]) -> None:
        code = self.user_room.get(user.id)
        room = self.rooms.get(code) if code else None
        if not room:
            raise GameError("Chat uchun xonaga kiring")
        text = str(data.get("text", "")).strip()
        text = "".join(ch for ch in text if ch.isprintable())[:MAX_CHAT]
        if not text:
            return
        now = time.monotonic()
        times = [t for t in room.chat_times.get(user.id, []) if now - t < CHAT_WINDOW]
        if len(times) >= CHAT_LIMIT:
            raise GameError("Juda tez yozmoqdasiz")
        if times and now - times[-1] < 0.7:
            raise GameError("Biroz sekinroq yozing")
        times.append(now)
        room.chat_times[user.id] = times
        message = {
            "type": "chat",
            "system": False,
            "user_id": user.id,
            "name": user.first_name,
            "avatar": user.avatar_url,
            "text": text,
            "ts": time.time(),
        }
        self._remember(room, message)
        for uid, c in list(room.conns.items()):
            if message["user_id"] in room.mutes.get(uid, set()):
                continue
            asyncio.create_task(c.send(message))

    async def _report(self, conn: Connection, data: dict[str, Any]) -> None:
        try:
            target = int(data.get("target_id", 0)) or None
        except (TypeError, ValueError):
            target = None
        reason = str(data.get("reason", "")).strip()[:500] or "Sabab ko'rsatilmagan"
        code = self.user_room.get(conn.user_id)
        async with SessionLocal() as session:
            session.add(Report(reporter_id=conn.user_id, target_id=target, room_code=code, reason=reason))
            await session.commit()
        await conn.send({"type": "toast", "message": "Shikoyat yuborildi. Rahmat."})

    async def _mute(self, conn: Connection, data: dict[str, Any]) -> None:
        code = self.user_room.get(conn.user_id)
        room = self.rooms.get(code) if code else None
        if not room:
            return
        try:
            target = int(data.get("target_id", 0))
        except (TypeError, ValueError):
            return
        muted = room.mutes.setdefault(conn.user_id, set())
        if data.get("mute", True):
            muted.add(target)
        else:
            muted.discard(target)
        await conn.send({"type": "muted", "target_id": target, "mute": data.get("mute", True)})

    def public_rooms(self, game_id: str | None = None) -> list[dict[str, Any]]:
        rooms = []
        for room in self.rooms.values():
            if room.status != "waiting" or not room.is_public or room.mode == "bot":
                continue
            if game_id and room.game_id != game_id:
                continue
            rooms.append(
                {
                    "code": room.code,
                    "game_id": room.game_id,
                    "title": room.module.title,
                    "icon": room.module.icon,
                    "players": len(room.players),
                    "capacity": room.capacity,
                    "host": next((p.name for p in room.players if p.id == room.host_id), ""),
                }
            )
        return rooms

    async def _loop(self) -> None:
        self._last_tick = time.monotonic()
        while True:
            try:
                now = time.monotonic()
                dt = min(0.2, now - self._last_tick)
                self._last_tick = now
                if now - self._last_match > 0.75:
                    self._last_match = now
                    await self._match_now()
                for room in list(self.rooms.values()):
                    if room.status == "playing":
                        await self._tick_room(room, now, dt)
                    elif room.status == "waiting" and now - room.created > 2700:
                        self.rooms.pop(room.code, None)
                        for uid in list(room.conns):
                            self.user_room.pop(uid, None)
                            await self.send(uid, {"type": "room_closed", "reason": "timeout"})
                    elif room.status == "finished" and now - room.finished_at > 60:
                        self.rooms.pop(room.code, None)
                await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("hub loop error")
                await asyncio.sleep(0.2)

    async def _tick_room(self, room: Room, now: float, dt: float) -> None:
        module = room.module
        if module.realtime:
            async with room.lock:
                if room.status != "playing":
                    return
                events = module.on_tick(room.state, dt)
                if module.finished(room.state):
                    await self._finish(room)
                    return
                room.snapshot_interval -= dt
                if room.snapshot_interval <= 0 or events:
                    room.snapshot_interval = 0.1
                    self._broadcast_state(room, events)
            for uid, ts in list(room.offline.items()):
                if now - ts > REALTIME_GRACE:
                    await self.leave(uid, silent=True)
            return

        async with room.lock:
            if room.status != "playing":
                return
            events = module.on_tick(room.state, dt)
            if events:
                self._broadcast_state(room, events)
            if module.finished(room.state):
                await self._finish(room)
                return
            if room.turn_deadline and now >= room.turn_deadline:
                events = module.on_timeout(room.state)
                self._broadcast_state(room, events)
                if module.finished(room.state):
                    await self._finish(room)
                    return
                self._set_deadline(room)
                self._schedule_bot(room)
                return
            if room.bot_due and now >= room.bot_due:
                room.bot_due = 0.0
                asyncio.create_task(self._match_bot_turn(room))
        for uid, ts in list(room.offline.items()):
            if now - ts > 90:
                await self.leave(uid, silent=True)


hub = Hub()
