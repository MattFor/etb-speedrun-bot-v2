from __future__ import annotations

import json
from typing import Any

try:
    import orjson

    def dumps(obj: Any) -> str:
        return orjson.dumps(obj).decode()

    loads = orjson.loads
except ImportError:
    dumps = json.dumps
    loads = json.loads
