from __future__ import annotations

import time
import asyncio
import logging
from typing import Any, final, override

import aiohttp
from pymongo.errors import PyMongoError

from .storage.mongo import DB
from .clients.discord_rest import Rest
from .clients.gateway import GatewayClient
from .clients.speedrun import SRC, SRCError
from .config import (
    ANY_IDS,
    BLUE,
    COMMANDS,
    COOLDOWN,
    DB_RETRY_DELAY,
    FULL_CHECK_DELAY,
    GREEN,
    GUILD_ID,
    NMG_IDS,
    NOSYNC_ROLE,
    RED,
    ROLE_ANY,
    ROLE_NMG,
    ROLE_OTHER,
    ROLE_RUN,
    SRC_ROLES,
    USER_CHECK_DELAY,
)

log = logging.getLogger("etb")


def embed(title: str, description: str, color: int) -> dict[str, Any]:
    return {"title": title, "description": description, "color": color}


@final
class Bot(GatewayClient):
    __slots__ = ("rest", "src", "db", "cooldowns", "unlinked", "app_id", "started")

    def __init__(self, token: str, session: aiohttp.ClientSession, db: DB) -> None:
        super().__init__(token, session)
        self.rest = Rest(session, token)
        self.src = SRC(session)
        self.db = db
        self.cooldowns: dict[str, float] = {}
        self.unlinked: set[str] = set()
        self.app_id = ""
        self.started = False

    @override
    async def on_event(self, event: str, data: Any) -> None:
        if event == "INTERACTION_CREATE":
            self.spawn(self.on_interaction(data))
        elif event == "READY":
            self.app_id = data["application"]["id"]
            log.info("Logged in as %s", data["user"]["username"])

            if not self.started:
                self.started = True
                await self.rest.set_guild_commands(self.app_id, GUILD_ID, COMMANDS)
                self.spawn(self.check_loop())

    async def on_interaction(self, data: Any) -> None:
        if data.get("type") != 2:
            return

        member = data.get("member")
        user: dict[str, Any] = (member or data).get("user") or {}
        user_id = user.get("id")

        if not user_id:
            return

        interaction_id = data["id"]
        token = data["token"]
        now = time.monotonic()
        last = self.cooldowns.get(user_id)

        if last is not None and now - last < COOLDOWN:
            wait = COOLDOWN - (now - last)
            log.info("%s tripped cooldown with %.2fs left", user_id, wait)

            await self.rest.callback(
                interaction_id,
                token,
                {
                    "type": 4,
                    "data": {
                        "embeds": (
                            embed("Cooldown", f"Try again in `{wait:.2f}s`", BLUE),
                        ),
                        "flags": 64,
                    },
                },
            )
            return

        self.cooldowns[user_id] = now

        if not await self.rest.callback(
            interaction_id, token, {"type": 5, "data": {"flags": 64}}
        ):
            return

        command: dict[str, Any] = data.get("data") or {}
        name = command.get("name")

        if name == "link":
            target: str = ""
            options: list[dict[str, Any]] = command.get("options") or []
            for option in options:
                if option.get("name") == "username":
                    target = option.get("value") or ""

            result = await self.link(user_id, user.get("username") or "", target)
        elif name == "unlink":
            result = await self.unlink(user_id)
        else:
            result = embed("Error", "Unknown command.", RED)
        await self.rest.edit_original(self.app_id, token, {"embeds": (result,)})

    async def link(
        self, user_id: str, discord_name: str, username: str
    ) -> dict[str, Any]:
        log.info("%s is trying to link to %s", user_id, username)

        try:
            connection = await self.src.discord_connection(username)
        except SRCError as error:
            log.info("%s tried linking to %s, SRCError: %s", user_id, username, error)
            return embed("Error", "There was some error on speedrun.com's side.", RED)

        if connection is None:
            log.info("%s tried linking to %s, NoDiscordOnAcc", user_id, username)
            return embed(
                "Error", f"`{username}` doesn't have a Discord account connected.", RED
            )

        src_id, linked_name, verified = connection

        if not verified:
            log.info("%s tried linking to %s, NotVerified", user_id, username)
            return embed(
                "Error",
                f"`{username}`'s Discord account connection is not verified.",
                RED,
            )

        if discord_name != linked_name:
            log.info("%s tried linking to %s, DiscordMismatch", user_id, username)
            return embed(
                "Error",
                f"Your Discord username doesn't match with `{username}`'s.",
                RED,
            )

        if await self.db.contains(user_id):
            log.info("%s tried linking to %s, AlreadyLinked", user_id, username)
            return embed("Error", "You already have a linked account.", RED)
        try:
            await self.db.save(src_id, user_id)
        except PyMongoError as error:
            log.error("save src user failed: %r", error)
            return embed("Error", "Unexpected database error.", RED)

        self.unlinked.discard(user_id)
        log.info("%s linked to %s", user_id, username)

        return embed(
            "Success",
            "Account linked successfully.\nRoles will be granted on the next check cycle which happens every 5 minutes.",
            GREEN,
        )

    async def unlink(self, user_id: str) -> dict[str, Any]:
        log.info("%s is trying to unlink", user_id)

        if not await self.db.contains(user_id):
            log.info("%s is trying to unlink, NoLinkedAcc", user_id)
            return embed("Error", "You don't have a linked account.", RED)

        self.unlinked.add(user_id)

        try:
            await self.db.delete(user_id)
        except PyMongoError as error:
            log.error("delete src user failed: %r", error)
            return embed("Error", "Unexpected database error.", RED)

        await self.strip_roles(user_id, "Account unlinked")
        log.info("%s unlinked", user_id)

        return embed("Success", "Account unlinked successfully.", GREEN)

    async def strip_roles(self, user_id: str, reason: str) -> None:
        member = await self.rest.get_member(GUILD_ID, user_id)
        if not member:
            return

        roles: set[str] = set(member.get("roles") or ())
        target = roles - SRC_ROLES

        if target != roles:
            await self.rest.set_roles(GUILD_ID, user_id, list(target), reason)

    async def check_loop(self) -> None:
        log.info("Started check loop")
        runs = -1
        linked = -1

        while not self.stop.is_set():
            log.info("Check started")
            try:
                rows = await self.db.all()
            except PyMongoError as error:
                log.error("read linked users failed: %r", error)
                await asyncio.sleep(DB_RETRY_DELAY)
                continue

            count = await self.src.run_count()

            if count is not None and (count != runs or len(rows) != linked):
                for index, (src_id, discord_id) in enumerate(rows):
                    if self.stop.is_set():
                        return
                    if index:
                        await asyncio.sleep(USER_CHECK_DELAY)
                    await self.sync(src_id, discord_id)

                runs = count
                linked = len(rows)
            else:
                log.info("Skipping src check")

            self.unlinked.clear()
            cutoff = time.monotonic() - COOLDOWN

            for user_id in [k for k, v in self.cooldowns.items() if v < cutoff]:
                del self.cooldowns[user_id]

            log.info("Check ended")
            await asyncio.sleep(FULL_CHECK_DELAY)

    async def sync(self, src_id: str, discord_id: str) -> None:
        log.info("Checking src (%s, %s)", src_id, discord_id)
        member = await self.rest.get_member(GUILD_ID, discord_id)

        if not member:
            log.info("(%s, %s) is not on the server", src_id, discord_id)
            return

        roles: set[str] = set(member.get("roles") or ())
        if discord_id in self.unlinked or NOSYNC_ROLE in roles:
            log.info("(%s, %s) is skipped", src_id, discord_id)
            return

        wanted = await self.wr_roles(src_id)

        if (roles - SRC_ROLES) | wanted == roles:
            return

        member = await self.rest.get_member(GUILD_ID, discord_id)
        if not member or discord_id in self.unlinked:
            return

        roles = set(member.get("roles") or ())
        if NOSYNC_ROLE in roles:
            return

        target = (roles - SRC_ROLES) | wanted
        if target != roles:
            await self.rest.set_roles(
                GUILD_ID, discord_id, list(target), "Updated world record roles"
            )

    async def wr_roles(self, src_id: str) -> set[str]:
        wrs, has_runs = await self.src.etb_wrs(src_id)
        roles: set[str] = set()

        if has_runs:
            log.info("%s has RUN", src_id)
            roles.add(ROLE_RUN)

        other = False
        for category, values in wrs:
            if category in ANY_IDS or not ANY_IDS.isdisjoint(values):
                log.info("%s has ANY%%", src_id)
                roles.add(ROLE_ANY)
            elif category in NMG_IDS or not NMG_IDS.isdisjoint(values):
                log.info("%s has NMG", src_id)
                roles.add(ROLE_NMG)
            else:
                other = True

        if other:
            log.info("%s has OTHER", src_id)
            roles.add(ROLE_OTHER)

        return roles
