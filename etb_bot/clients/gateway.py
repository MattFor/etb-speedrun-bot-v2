from __future__ import annotations

import sys
import random
import asyncio
import logging
from typing import Any

import aiohttp

from ..util.serial import dumps, loads
from ..config import FATAL_CLOSE_CODES, GATEWAY_BASE, GATEWAY_QUERY

log = logging.getLogger("etb")


class GatewayClient:
    __slots__: tuple[str, ...] = (
        "token",
        "session",
        "seq",
        "session_id",
        "resume_url",
        "acked",
        "stop",
        "tasks",
    )

    def __init__(self, token: str, session: aiohttp.ClientSession) -> None:
        self.token: str = token
        self.session: aiohttp.ClientSession = session
        self.seq: int | None = None
        self.session_id: str | None = None
        self.resume_url: str | None = None
        self.acked: bool = True
        self.stop: asyncio.Event = asyncio.Event()
        self.tasks: set[asyncio.Task[Any]] = set()

    async def on_event(self, _event: str, _data: Any) -> None:
        pass

    async def dispatch(self, event: str, data: Any) -> None:
        if event == "READY":
            self.session_id = data["session_id"]
            self.resume_url = data.get("resume_gateway_url")
        elif event == "RESUMED":
            log.info("Resumed session")

        await self.on_event(event, data)

    def spawn(self, coro: Any) -> None:
        task = asyncio.ensure_future(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def run(self) -> None:
        gateway = asyncio.ensure_future(self.gateway_loop())
        _ = await self.stop.wait()
        _ = gateway.cancel()

        for task in tuple(self.tasks):
            _ = task.cancel()

        _ = await asyncio.gather(gateway, *self.tasks, return_exceptions=True)

    async def gateway_loop(self) -> None:
        backoff = 1.0
        while not self.stop.is_set():
            url = (self.resume_url or GATEWAY_BASE).rstrip("/") + GATEWAY_QUERY
            heartbeat: asyncio.Task[Any] | None = None
            try:
                async with self.session.ws_connect(
                    url, heartbeat=None, max_msg_size=0, autoclose=False
                ) as ws:
                    self.acked = True
                    async for message in ws:
                        if message.type is not aiohttp.WSMsgType.TEXT:
                            break

                        frame = loads(message.data)
                        op = frame["op"]

                        if op == 0:
                            self.seq = frame["s"]
                            backoff = 1.0

                            await self.dispatch(frame["t"], frame["d"])
                        elif op == 10:
                            interval = frame["d"]["heartbeat_interval"] / 1000.0
                            heartbeat = asyncio.ensure_future(
                                self.heartbeat(ws, interval)
                            )

                            await ws.send_json(self.hello_payload(), dumps=dumps)
                        elif op == 11:
                            self.acked = True
                        elif op == 1:
                            await ws.send_json({"op": 1, "d": self.seq}, dumps=dumps)
                        elif op == 7:
                            break
                        elif op == 9:
                            if not frame.get("d"):
                                self.session_id = None
                                self.seq = None
                                self.resume_url = None

                            await asyncio.sleep(random.uniform(1.0, 5.0))
                            break
                    code = ws.close_code
                    _ = await ws.close()
            except asyncio.CancelledError:
                raise
            except (TimeoutError, aiohttp.ClientError, OSError) as error:
                code = None
                log.warning("Gateway connection failed: %r", error)
            finally:
                if heartbeat is not None:
                    _ = heartbeat.cancel()

            if code in FATAL_CLOSE_CODES:
                log.error("Gateway closed fatally with %s", code)
                self.stop.set()
                return

            if code is not None and code not in (1000, 1001, 4000, 4007, 4009):
                self.session_id = None
                self.seq = None
                self.resume_url = None

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2.0, 60.0)

    def hello_payload(self) -> dict[str, Any]:
        if self.session_id and self.seq is not None:
            return {
                "op": 6,
                "d": {
                    "token": self.token,
                    "session_id": self.session_id,
                    "seq": self.seq,
                },
            }
        return {
            "op": 2,
            "d": {
                "token": self.token,
                "intents": 0,
                "properties": {
                    "os": sys.platform,
                    "browser": "etb-speedrunning-bot",
                    "device": "etb-speedrunning-bot",
                },
            },
        }

    async def heartbeat(
        self, ws: aiohttp.ClientWebSocketResponse, interval: float
    ) -> None:
        await asyncio.sleep(interval * random.random())

        while not ws.closed:
            if not self.acked:
                _ = await ws.close(code=4000)
                return

            self.acked = False

            await ws.send_json({"op": 1, "d": self.seq}, dumps=dumps)
            await asyncio.sleep(interval)
