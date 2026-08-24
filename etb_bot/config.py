from __future__ import annotations

import aiohttp

SRC_BASE = "https://www.speedrun.com/api"
SRC_HEADERS = {
    "X-By": "We-<3-Cloudflare",
    "Accept": "application/json",
    "User-Agent": "ETB-Speedrunning-Bot/1.0",
}
API_BASE = "https://discord.com/api/v10"
GATEWAY_BASE = "wss://gateway.discord.gg"
GATEWAY_QUERY = "/?v=10&encoding=json"

GUILD_ID = "1016926742063104010"
NOSYNC_ROLE = "1133392191285366847"
ROLE_ANY = "1073358491256885399"
ROLE_NMG = "1273663624212123649"
ROLE_OTHER = "1073358646320312500"
ROLE_RUN = "1529891741878980758"
SRC_ROLES = frozenset((ROLE_ANY, ROLE_NMG, ROLE_OTHER, ROLE_RUN))

ANY_IDS = frozenset(
    (
        "zdn7gnek",
        "qvvondrq",
        "12vm8zdq",
        "1dkgmyjl",
        "1397ym31",
        "qke0x8dq",
        "q5vz05nl",
    )
)
NMG_IDS = frozenset(
    (
        "rklm9ywd",
        "le2zw8ml",
        "qj7v9m3q",
        "1pyognv1",
        "q65npojl",
        "q8k8m0kq",
        "qyzo6y71",
        "lmovp3m1",
        "qvvonrwq",
        "le2zw4zl",
        "1w4z9xvq",
    )
)
ETB_GAMES = ("m1zkg5m1", "m1mn5q3d", "3dxkwoy1")
ETB_GAME_SET = frozenset(ETB_GAMES)

USER_CHECK_DELAY = 15.0
FULL_CHECK_DELAY = 300.0
DB_RETRY_DELAY = 30.0
COOLDOWN = 15.0
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)

RED = 0xFF0000
GREEN = 0x00FF00
BLUE = 0x3498DB

COMMANDS = (
    {
        "type": 1,
        "name": "link",
        "description": "Link your account with speedrun.com",
        "options": (
            {
                "type": 3,
                "name": "username",
                "description": "speedrun.com username",
                "required": True,
            },
        ),
    },
    {
        "type": 1,
        "name": "unlink",
        "description": "Unlink your account with speedrun.com",
    },
)

FATAL_CLOSE_CODES = frozenset((4004, 4010, 4011, 4012, 4013, 4014))
