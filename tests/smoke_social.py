import asyncio
import json
import sys

import httpx
import websockets

BASE = "http://127.0.0.1:8000"
WS = "ws://127.0.0.1:8000/ws"


async def login(user_id: int, name: str) -> str:
    async with httpx.AsyncClient(trust_env=False) as c:
        r = await c.post(f"{BASE}/api/auth/dev", json={"user_id": user_id, "name": name})
        r.raise_for_status()
        return r.json()["token"]


class Client:
    def __init__(self, token: str, name: str):
        self.token = token
        self.name = name
        self.ws = None
        self.inbox: list[dict] = []

    async def connect(self):
        self.ws = await websockets.connect(f"{WS}?token={self.token}", ping_interval=20)
        hello = json.loads(await self.ws.recv())
        assert hello["type"] == "hello", hello
        asyncio.create_task(self._reader())

    async def _reader(self):
        try:
            async for raw in self.ws:
                self.inbox.append(json.loads(raw))
        except websockets.ConnectionClosed:
            pass

    async def send(self, payload):
        await self.ws.send(json.dumps(payload))

    async def wait_for(self, kind, timeout=10, **match):
        end = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < end:
            for i, msg in enumerate(self.inbox):
                if msg.get("type") != kind:
                    continue
                if all(msg.get(k) == v for k, v in match.items()):
                    return self.inbox.pop(i)
            await asyncio.sleep(0.05)
        raise AssertionError(f"{self.name}: '{kind}' {match} topilmadi. Inbox: {self.inbox[-6:]}")

    def drain(self, kind):
        self.inbox = [m for m in self.inbox if m.get("type") != kind]

    async def close(self):
        try:
            await self.ws.close()
        except Exception:
            pass


async def main() -> int:
    a = Client(await login(700000901, "Sardor"), "Sardor")
    b = Client(await login(700000902, "Dilnoza"), "Dilnoza")
    await a.connect()
    await b.connect()

    await a.send({"type": "create_room", "game_id": "chess", "capacity": 2, "public": True, "mode": "room"})
    code = (await a.wait_for("room_created"))["code"]
    print("room:", code)

    await b.send({"type": "rooms", "game_id": "chess"})
    listing = await b.wait_for("rooms")
    assert any(r["code"] == code for r in listing["rooms"]), listing
    print("public room listed")

    await b.send({"type": "join_room", "code": code})
    gs_b = await b.wait_for("game_state", timeout=12)
    gs_a = await a.wait_for("game_state", timeout=12)
    await a.wait_for("room_state")
    slot_a = gs_a["state"]["your_slot"]
    assert gs_b["state"]["your_slot"] != slot_a
    print("game started, slots:", slot_a, gs_b["state"]["your_slot"])

    await b.send({"type": "chat", "text": "Salom, omad!"})
    chat = await a.wait_for("chat", text="Salom, omad!")
    assert chat["name"] == "Dilnoza"
    print("chat received:", chat["name"], "->", chat["text"])

    await b.send({"type": "report", "target_id": 700000901, "reason": "Test shikoyat"})
    toast = await b.wait_for("toast")
    print("report toast:", toast["message"])

    await a.send({"type": "mute", "target_id": 700000902, "mute": True})
    await a.wait_for("muted", target_id=700000902)
    a.drain("chat")
    await b.send({"type": "chat", "text": "Meni eshityapsanmi?"})
    await asyncio.sleep(1.0)
    assert not any(m.get("type") == "chat" and m.get("text") == "Meni eshityapsanmi?" for m in a.inbox), "mute failed"
    print("mute works")

    state = gs_a["state"]
    mover = a if state["turn"] == slot_a else b
    uci = "e2e4" if state["turn"] == 0 else "e7e5"
    await mover.send({"type": "action", "action": {"type": "move", "uci": uci}})
    moved_a = await a.wait_for("game_state", timeout=10)
    moved_b = await b.wait_for("game_state", timeout=10)
    assert moved_a["state"]["last_move"] and moved_b["state"]["last_move"]
    print("move synced:", moved_b["state"]["last_move"])

    await b.close()
    await asyncio.sleep(1.0)
    b2 = Client(b.token, "Dilnoza")
    await b2.connect()
    await b2.send({"type": "join_room", "code": code})
    await b2.wait_for("room_state", timeout=6)
    resumed = await b2.wait_for("game_state", timeout=6)
    print("reconnect restored, fen ok:", bool(resumed["state"]["fen"]))

    await a.send({"type": "leave"})
    await b2.send({"type": "leave"})
    await asyncio.sleep(0.8)

    a.drain("match_found")
    b2.drain("match_found")
    await a.send({"type": "quick_match", "game_id": "chess"})
    await b2.send({"type": "quick_match", "game_id": "chess"})
    ma = await a.wait_for("match_found", timeout=8)
    mb = await b2.wait_for("match_found", timeout=8)
    assert ma["code"] == mb["code"]
    print("quick match paired:", ma["code"])

    await a.send({"type": "leave"})
    await b2.send({"type": "leave"})
    await asyncio.sleep(0.4)
    await a.close()
    await b2.close()
    print("SOCIAL OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
