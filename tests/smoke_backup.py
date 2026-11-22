import asyncio
import io
import sys

import httpx

BASE = "http://127.0.0.1:8000"


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=60) as c:
        r = await c.post("/api/auth/dev", json={"user_id": 700000777, "name": "Futbol Test"})
        r.raise_for_status()
        token = r.json()["token"]
        h = {"Authorization": f"Bearer {token}"}

        r = await c.post("/api/admin/backup", json={"kind": "full"}, headers=h)
        r.raise_for_status()
        backup = r.json()
        print("created:", backup["file"], backup["size"], "bytes")
        bid = backup["id"]

        r = await c.get(f"/api/admin/backups/{bid}/download", headers=h)
        r.raise_for_status()
        blob = r.content
        assert blob[:2] == b"PK", "not a zip"

        r = await c.post("/api/admin/backup/preview", files={"file": ("b.zip", blob, "application/zip")}, headers=h)
        r.raise_for_status()
        preview = r.json()
        print("preview counts:", preview["counts"])
        assert preview["kind"] == "full"

        r = await c.post("/api/admin/backup/restore", json={"token": preview["token"], "confirm": True}, headers=h)
        if r.status_code != 200:
            print("restore failed:", r.status_code, r.text)
            return 1
        restored = r.json()
        print("restored:", restored["restored"])
        print("safety backup:", restored["safety_backup"])

        r = await c.get("/api/me", headers=h)
        r.raise_for_status()
        me = r.json()["profile"]
        print("me after restore:", me["name"], me["achko"], me["coins"])

        r = await c.get("/api/transactions", headers=h)
        r.raise_for_status()
        print("transactions:", len(r.json().get("transactions", [])))

        r = await c.post("/api/skill", json={"game_id": "football", "rating": 1234}, headers=h)
        r.raise_for_status()
        print("skill set:", r.json())
        r = await c.post("/api/skill", json={"game_id": "football", "rating": 9999}, headers=h)
        assert r.status_code == 400, "bad rating accepted"
        print("invalid skill rejected:", r.json()["detail"])
        await c.post("/api/skill", json={"game_id": "football", "rating": 1000}, headers=h)

        r = await c.get("/api/music", headers=h)
        r.raise_for_status()
        print("music tracks:", len(r.json().get("tracks", [])))
    print("BACKUP OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
