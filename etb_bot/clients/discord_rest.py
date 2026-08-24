from __future__ import annotations

import asyncio
import logging
from typing import Any, final
from urllib.parse import quote
from collections.abc import Awaitable

import aiohttp

from ..util.serial import dumps, loads
from ..config import API_BASE, REQUEST_TIMEOUT

log = logging.getLogger("etb")


@final
class Rest:
    __slots__ = ("_session", "_headers")

    def __init__(self, session: aiohttp.ClientSession, token: str) -> None:
        self._session = session
        self._headers = {
            "Authorization": "Bot " + token,
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (https://speedrun.com, 2.0)",
        }

    async def request(
        self,
        method: str,
        path: str,
        payload: Any = None,
        reason: str | None = None,
        attempts: int = 3,
    ) -> Any:
        headers = self._headers

        if reason is not None:
            headers = {**headers, "X-Audit-Log-Reason": quote(reason, safe=" ")}

        body = dumps(payload).encode() if payload is not None else None

        for attempt in range(attempts):
            try:
                async with self._session.request(
                    method,
                    API_BASE + path,
                    data=body,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                ) as response:
                    status = response.status
                    if status == 429:
                        raw = await response.read()
                        try:
                            retry_after = float(loads(raw).get("retry_after", 1.0))
                        except (ValueError, AttributeError, TypeError):
                            retry_after = 1.0

                        log.warning(
                            "%s %s rate limited for %.2fs", method, path, retry_after
                        )

                        await asyncio.sleep(min(retry_after, 60.0) + 0.1)
                        continue
                    if status >= 500:
                        await asyncio.sleep(1.0 + attempt)
                        continue

                    if status == 404:
                        return None

                    if status >= 400:
                        log.error(
                            "%s %s failed: %s %s",
                            method,
                            path,
                            status,
                            await response.text(),
                        )
                        return None

                    raw = await response.read()

                    return loads(raw) if raw else True
            except (TimeoutError, aiohttp.ClientError) as error:
                log.warning("%s %s errored: %r", method, path, error)
                await asyncio.sleep(1.0 + attempt)

        return None

    def set_guild_commands(
        self, app_id: str, guild_id: str, commands: Any
    ) -> Awaitable[Any]:
        return self.request(
            "PUT", f"/applications/{app_id}/guilds/{guild_id}/commands", commands
        )

    def callback(self, interaction_id: str, token: str, payload: Any) -> Awaitable[Any]:
        return self.request(
            "POST", f"/interactions/{interaction_id}/{token}/callback", payload
        )

    def edit_original(self, app_id: str, token: str, payload: Any) -> Awaitable[Any]:
        return self.request(
            "PATCH", f"/webhooks/{app_id}/{token}/messages/@original", payload
        )

    def get_member(self, guild_id: str, user_id: str) -> Awaitable[Any]:
        return self.request("GET", f"/guilds/{guild_id}/members/{user_id}")

    def set_roles(
        self, guild_id: str, user_id: str, roles: list[str], reason: str
    ) -> Awaitable[Any]:
        return self.request(
            "PATCH", f"/guilds/{guild_id}/members/{user_id}", {"roles": roles}, reason
        )
