from __future__ import annotations

import asyncio
import logging
from typing import Any, final
from urllib.parse import quote

import aiohttp

from ..util.serial import loads
from ..config import ETB_GAME_SET, ETB_GAMES, REQUEST_TIMEOUT, SRC_BASE, SRC_HEADERS

log = logging.getLogger("etb")


class SRCError(Exception):
    pass


@final
class SRC:
    __slots__ = ("_session",)

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _get(self, path: str) -> Any:
        try:
            async with self._session.get(
                SRC_BASE + path, headers=SRC_HEADERS, timeout=REQUEST_TIMEOUT
            ) as response:
                if response.status != 200:
                    return None
                return loads(await response.read())
        except (TimeoutError, aiohttp.ClientError, ValueError) as error:
            raise SRCError(repr(error)) from error

    async def run_count(self) -> int | None:
        payloads = await asyncio.gather(
            *(self._get(f"/v2/GetGameSummary?gameId={game}") for game in ETB_GAMES),
            return_exceptions=True,
        )

        total = 0

        for payload in payloads:
            if isinstance(payload, BaseException):
                log.warning("GetGameSummary failed: %r", payload)
                return None

            summary: dict[str, Any] = payload or {}
            game_summary: dict[str, Any] = summary.get("game") or {}
            count = game_summary.get("runCount")

            if not isinstance(count, int):
                return None

            total += count

        return total

    async def discord_connection(self, username: str) -> tuple[str, str, bool] | None:
        payload = await self._get("/v2/GetUserSummary?Url=" + quote(username, safe=""))
        if not payload:
            return None

        user: dict[str, Any] = payload.get("user") or {}
        if not user.get("powerLevel"):
            return None

        connections: list[dict[str, Any]] = (
            payload.get("userSocialConnectionList") or []
        )

        for connection in connections:
            if connection.get("networkId") == 5:
                return (
                    user.get("id") or "",
                    connection.get("value") or "",
                    bool(connection.get("verified")),
                )

        return None

    async def etb_wrs(
        self, user_id: str
    ) -> tuple[list[tuple[str, tuple[str, ...]]], bool]:
        try:
            payload = await self._get(
                "/v2/GetUserLeaderboard?userId=" + quote(user_id, safe="")
            )
        except SRCError as error:
            log.warning("GetUserLeaderboard %s failed: %s", user_id, error)
            return [], False

        if not payload:
            return [], False

        wrs: list[tuple[str, tuple[str, ...]]] = []
        has_runs = False
        for run in payload.get("runs") or ():
            if run.get("gameId") in ETB_GAME_SET:
                has_runs = True
                if run.get("place") == 1:
                    wrs.append(
                        (run.get("categoryId") or "", tuple(run.get("valueIds") or ()))
                    )

        return wrs, has_runs
