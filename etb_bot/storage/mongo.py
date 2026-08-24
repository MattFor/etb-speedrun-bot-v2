from __future__ import annotations

import logging
from typing import Any, final

from pymongo import AsyncMongoClient
from pymongo.asynchronous.collection import AsyncCollection

log = logging.getLogger("etb")


@final
class DB:
    __slots__ = ("_client", "_col")

    def __init__(self, uri: str, name: str, collection: str) -> None:
        self._client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(
            uri,
            appname="etb-speedrun-bot",
            serverSelectionTimeoutMS=10_000,
            retryWrites=True,
        )
        self._col: AsyncCollection[dict[str, Any]] = self._client[name][collection]
        log.info("Created DB client (%s.%s)", name, collection)

    async def start(self) -> None:
        await self._client.aconnect()
        _ = await self._col.create_index("discordid")
        log.info("Connected to MongoDB, %d linked users", await self.count())

    async def close(self) -> None:
        await self._client.close()

    async def count(self) -> int:
        return await self._col.count_documents({})

    async def contains(self, discord_id: str) -> bool:
        doc = await self._col.find_one({"discordid": discord_id}, {"_id": 1})
        return doc is not None

    async def save(self, src_id: str, discord_id: str) -> None:
        _ = await self._col.update_one(
            {"_id": src_id},
            {"$setOnInsert": {"discordid": discord_id}},
            upsert=True,
        )

    async def delete(self, discord_id: str) -> None:
        _ = await self._col.delete_many({"discordid": discord_id})

    async def all(self) -> list[tuple[str, str]]:
        cursor = self._col.find({}, {"_id": 1, "discordid": 1})
        return [(doc["_id"], doc["discordid"]) async for doc in cursor]
