from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from fastapi.exceptions import HTTPException

from ..database import SessionLocal
from ..games.registry import registry
from ..security.auth import user_from_ws_token
from ..services.profile import build_profile
from ..websocket.hub import hub

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(default="")):
    await ws.accept()
    try:
        async with SessionLocal() as session:
            user = await user_from_ws_token(token, session)
            profile = await build_profile(session, user)
    except HTTPException as exc:
        await ws.send_json({"type": "error", "message": exc.detail, "code": "auth"})
        await ws.close(code=4401)
        return
    except Exception:
        await ws.send_json({"type": "error", "message": "Avtorizatsiya xatosi", "code": "auth"})
        await ws.close(code=4401)
        return

    conn = await hub.connect(user, ws)
    await conn.send({
        "type": "hello",
        "user": profile,
        "games": registry.catalog(),
        "online": len(hub.connections),
    })
    try:
        while True:
            data = await ws.receive_json()
            if isinstance(data, dict):
                await hub.handle(conn, data)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await hub.disconnect(user.id)
