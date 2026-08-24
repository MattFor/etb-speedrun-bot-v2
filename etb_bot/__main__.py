from __future__ import annotations

import os
import signal
import asyncio

import aiohttp

from .bot import Bot
from .storage.mongo import DB
from .util.env import load_env
from .util.log import setup_logging


def read_token() -> str:
    token = os.environ.get("BOT_TOKEN", "").strip()
    if token:
        return token
    raise SystemExit("no bot token")


async def main() -> None:
    load_env()
    token = read_token()
    uri = os.environ.get("MONGODB_URI", "").strip()

    if not uri:
        raise SystemExit("missing MONGODB_URI")

    db = DB(
        uri,
        os.environ.get("MONGODB_DB", "etb").strip() or "etb",
        os.environ.get("MONGODB_COLLECTION", "src").strip() or "src",
    )
    connector = aiohttp.TCPConnector(limit=32, ttl_dns_cache=300)
    try:
        await db.start()
        async with aiohttp.ClientSession(
            connector=connector, timeout=aiohttp.ClientTimeout(total=None, connect=15)
        ) as session:
            bot = Bot(token, session, db)
            loop = asyncio.get_running_loop()

            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, bot.stop.set)
                except NotImplementedError:
                    pass

            await bot.run()
    finally:
        await db.close()


def run() -> None:
    setup_logging()
    try:
        import uvloop
    except ImportError:
        asyncio.run(main())
    else:
        uvloop.run(main())


if __name__ == "__main__":
    run()
