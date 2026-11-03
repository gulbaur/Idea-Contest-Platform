"""WebSocket `/api/ws`: вход первым сообщением, затем только сигналы (D-039)."""

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket

from app.deps import find_session
from app.realtime import CLOSE_AUTH_TIMEOUT, CLOSE_BAD_MESSAGE, CLOSE_UNAUTHORIZED

router = APIRouter(tags=["realtime"])


def _parse(text: str | None) -> dict | None:
    try:
        message = json.loads(text) if text is not None else None
    except ValueError:
        return None
    return message if isinstance(message, dict) else None


def _auth_token(text: str | None) -> str | None:
    message = _parse(text)
    if message is None or message.get("type") != "auth":
        return None
    token = message.get("token")
    return token if isinstance(token, str) and 0 < len(token) <= 256 else None


@router.websocket("/api/ws")
async def realtime(websocket: WebSocket) -> None:
    app = websocket.app
    clock, hub = app.state.clock, app.state.hub
    await websocket.accept()

    # Токен — первым сообщением, а не в адресе: адреса попадают в журналы серверов (D-003).
    try:
        first = await asyncio.wait_for(
            websocket.receive(), timeout=app.state.settings.ws_auth_timeout_seconds
        )
    except TimeoutError:
        await websocket.close(code=CLOSE_AUTH_TIMEOUT)
        return
    if first["type"] == "websocket.disconnect":
        return
    token = _auth_token(first.get("text"))
    if token is None:
        await websocket.close(code=CLOSE_BAD_MESSAGE)
        return
    async with app.state.sessionmaker() as db:
        found = await find_session(db, token, clock.now())
    if found is None:
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return
    session, user = found

    connection = hub.register(
        websocket,
        user_id=user.id,
        role=user.role,
        session_id=session.id,
        expires_at=session.expires_at,
    )
    connection.send(
        {"type": "ready", "user_id": user.id, "server_time": clock.now().isoformat()}
    )
    sender = asyncio.create_task(connection.run())
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if _parse(message.get("text")) == {"type": "ping"}:
                connection.send({"type": "pong"})
            # Остальные сообщения клиента не нужны и игнорируются.
    finally:
        hub.unregister(connection)
        sender.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sender
