from __future__ import annotations

import sys
import logging


def setup_logging() -> None:
    formatter = logging.Formatter("%(asctime)s %(message)s", "%Y/%m/%d %H:%M:%S")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
