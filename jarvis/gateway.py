"""OpenClaw gateway client (WebSocket RPC) for the panel. Only used when your agent is OpenClaw.

Connects as a "local backend client": just the gateway token, no device pairing, because the connection is
loopback (see OpenClaw docs/gateway/protocol/handshake.md). One connection that reopens itself; `call()` blocks,
so the panel's server threads can use it directly.
"""
from __future__ import annotations

import asyncio
import json
import threading
import uuid
from urllib.parse import urlparse

from . import brain, settings

SCOPES = ["operator.read", "operator.write", "operator.admin"]  # admin: cron.run and cron.update require it


class GatewayError(Exception):
    pass


class Gateway:
    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._ws = None
        self._pending: dict[str, asyncio.Future] = {}
        self._connecting: asyncio.Lock | None = None
        threading.Thread(target=self._loop.run_forever, daemon=True, name="gateway").start()

    def call(self, method: str, params: dict | None = None, timeout: float = 20) -> dict:
        future = asyncio.run_coroutine_threadsafe(self._call(method, params or {}, timeout), self._loop)
        return future.result(timeout + 15)

    async def _connect(self) -> None:
        import websockets
        if self._connecting is None:
            self._connecting = asyncio.Lock()
        async with self._connecting:
            if self._ws is not None:
                return
            u = urlparse(settings.load()["agent"]["url"])
            ws = await websockets.connect(f"ws://{u.hostname}:{u.port}", max_size=2**25, open_timeout=10)
            await ws.recv()  # connect.challenge
            await ws.send(json.dumps({"type": "req", "id": "connect", "method": "connect", "params": {
                "minProtocol": 4, "maxProtocol": 4,
                "client": {"id": "gateway-client", "version": "for-real-jarvis", "platform": "windows", "mode": "backend"},
                "role": "operator", "scopes": SCOPES, "caps": [], "commands": [], "permissions": {},
                "auth": {"token": brain.token()}, "locale": "en"}}))
            while True:
                m = json.loads(await asyncio.wait_for(ws.recv(), 30))
                if m.get("type") == "res" and m.get("id") == "connect":
                    break
            if not m.get("ok"):
                await ws.close()
                raise GatewayError(f"the gateway refused the connection: {m.get('error')}")
            self._ws = ws
            asyncio.ensure_future(self._read(ws))

    async def _read(self, ws) -> None:
        try:
            async for raw in ws:
                m = json.loads(raw)
                if m.get("type") == "res" and m.get("id") in self._pending:
                    self._pending.pop(m["id"]).set_result(m)
        except Exception:  # noqa: BLE001 — dropped: the next call reconnects
            pass
        finally:
            if self._ws is ws:
                self._ws = None
            for f in self._pending.values():
                if not f.done():
                    f.set_exception(GatewayError("lost the connection to OpenClaw"))
            self._pending.clear()

    async def _call(self, method: str, params: dict, timeout: float) -> dict:
        if self._ws is None:
            await self._connect()
        rid = str(uuid.uuid4())
        future = self._loop.create_future()
        self._pending[rid] = future
        await self._ws.send(json.dumps({"type": "req", "id": rid, "method": method, "params": params}))
        try:
            r = await asyncio.wait_for(future, timeout)
        finally:
            self._pending.pop(rid, None)
        if not r.get("ok"):
            raise GatewayError(f"{method}: {(r.get('error') or {}).get('message', r.get('error'))}")
        return r.get("payload") or {}
