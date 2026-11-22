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
        self.state = None
        self.code = None
        self.chat = []
        self.events = []

    async def connect(self):
        self.ws = await websockets.connect(f"{WS}?token={self.token}", ping_interval=20)
        hello = json.loads(await self.ws.recv())
        assert hello["type"] == "hello", hello
        return hello

    async def send(self, payload):
        await self.ws.send(json.dumps(payload))

    async def wait_for(self, kind, timeout=12):
        end = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < end:
            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=end - asyncio.get_event_loop().time())
            except asyncio.TimeoutError:
                break
            msg = json.loads(raw)
            if msg["type"] == "game_state":
                self.state = msg["state"]
                self.events.extend(msg.get("events") or [])
            if msg["type"] == "room_state":
                self.code = msg["room"]["code"]
            if msg["type"] == "chat":
                self.chat.append(msg)
            if msg["type"] == kind:
                return msg
            if msg["type"] == "error":
                print(f"[{self.name}] error:", msg)
        raise TimeoutError(f"{self.name}: {kind} kelmadi")


async def main():
    t1 = await login(1001, "Ali")
    t2 = await login(1002, "Vali")
    a, b = Client(t1, "Ali"), Client(t2, "Vali")
    hello = await a.connect()
    print("hello games:", [g["id"] for g in hello["games"]])

    await a.send({"type": "create_room", "game_id": "chess", "mode": "bot", "capacity": 2,
                  "settings": {"time_minutes": 5}})
    await a.wait_for("room_created")
    await a.wait_for("game_state")
    print("chess bot room:", a.code, "fen ok:", bool(a.state["fen"]))
    uci = a.state["legal"][0]
    await a.send({"type": "action", "action": {"type": "move", "uci": uci}})
    await a.wait_for("game_state")
    await asyncio.sleep(2.5)
    print("after bot reply turn:", a.state["turn"], "last:", a.state.get("last_move"))
    await a.send({"type": "action", "action": {"type": "resign"}})
    res = await a.wait_for("match_result")
    print("chess result:", res["result"], "rewards:", res["rewards"]["outcome"], res["rewards"]["rating_delta"])
    await a.send({"type": "leave"})
    await a.wait_for("left")

    await a.send({"type": "create_room", "game_id": "uno", "mode": "room", "capacity": 2})
    created = await a.wait_for("room_created")
    await b.connect()
    await b.send({"type": "join_room", "code": created["code"]})
    await a.wait_for("game_state")
    await b.wait_for("game_state")
    print("uno started, code:", created["code"], "turn:", a.state["turn"])

    await b.send({"type": "chat", "text": "Salom, o'yin boshladik!"})
    chat = await a.wait_for("chat")
    print("chat:", chat["name"], chat["text"])

    for _ in range(4):
        actor = a if a.state["turn"] == a.state["your_slot"] else b
        if actor.state["finished"]:
            break
        if actor.state.get("legal"):
            await actor.send({"type": "action", "action": {"type": "play", "index": actor.state["legal"][0], "color": "R"}})
        else:
            await actor.send({"type": "action", "action": {"type": "draw"}})
        await asyncio.sleep(0.6)
        await a.wait_for("game_state", timeout=3)
        await b.wait_for("game_state", timeout=3)
    print("uno state ok, turn:", a.state["turn"], "hand:", len(a.state["hand"]))

    await a.send({"type": "leave"})
    await b.send({"type": "leave"})
    await asyncio.sleep(0.5)
    await a.ws.close()
    await b.ws.close()

    c = Client(t1, "Ali")
    await c.connect()
    await c.send({"type": "quick_match", "game_id": "football"})
    d = Client(t2, "Vali")
    await d.connect()
    await d.send({"type": "quick_match", "game_id": "football"})
    found = await c.wait_for("match_found", timeout=15)
    await d.wait_for("match_found", timeout=15)
    await c.wait_for("game_state")
    await d.wait_for("game_state")
    print("football match:", found["code"], "entities:", len(c.state["entities"]))
    await c.send({"type": "action", "action": {"type": "move", "x": 1, "y": 0, "sprint": True}})
    await asyncio.sleep(1.2)
    await c.wait_for("game_state", timeout=5)
    print("football tick ok, time:", c.state["time"], "ball:", c.state["ball"])
    await c.send({"type": "leave"})
    await asyncio.sleep(0.6)
    await c.ws.close()
    await d.ws.close()
    print("SMOKE OK")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print("SMOKE FAIL:", type(exc).__name__, exc)
        sys.exit(1)
