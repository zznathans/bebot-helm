"""Ported from Modules/BotStatisticsUi.php.

Thin chat-command UI over the already-ported `core("bot_statistics")`
(main_modules/bot_statistics.py): exposes `bots` (uptime/status report,
MEMBER) and `environ` (runtime environment info, SUPERADMIN).

Faithful-port note on `bots`: matching the PHP original, when
`bot.accessallbots` is false the user-supplied argument is discarded
entirely and replaced with "<botname> <dimension>", restricting the
report to this bot's own stats regardless of what was typed. Only when
`accessallbots` is true does an explicit `<bot>` / `<bot> <dim>`
argument (or no argument, for the all-bots summary) get passed through
to `core("bot_statistics").check_bots()`.

Cut vs. the PHP original: `environ` reported PHP/BeBot-specific version
constants (`BOT_VERSION_NAME`, `BOT_VERSION`, `BOT_OPERATING_SYSTEM`,
`phpversion()`) that have no equivalent anywhere in this Python port (no
`__version__`/`BOT_VERSION` constant exists yet). It's replaced here with
the closest faithful Python equivalents -- the interpreter version and
platform string in place of the PHP version/OS, and the MySQL server
version (via the underlying pymysql connection's `get_server_info()`,
the same info `mysqli_get_server_info()` exposed) -- rather than
inventing bot-version constants that don't exist elsewhere in the port.
"""
from __future__ import annotations

import platform
import sys

from ..commodities.base import BaseActiveModule


class BotStatisticsUi(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("bot_statistics_ui")
        self.register_command("all", "bots", "MEMBER")
        self.register_command("all", "environ", "SUPERADMIN")
        self.help["description"] = (
            "Shows online/offline statistics for this bot (or, with access, "
            "any tracked bot) and the runtime environment it's running in."
        )
        self.help["command"] = {
            "bots": "Shows online/offline status and uptime stats for bots.",
            "environ": "Shows information about the runtime environment.",
        }

    # -- dispatch -----------------------------------------------------------------
    def command_handler(self, name, msg, origin):
        parts = msg.split(" ", 1)
        command = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        if command == "bots":
            return self.check_bots(name, origin, rest)
        if command == "environ":
            return self.check_environ(name, origin, rest)
        return (
            "##error##Error : Broken plugin, received unhandled command: "
            f"##highlight##{command}##end## in Bots.php##end##"
        )

    # -- views --------------------------------------------------------------------
    def check_environ(self, name, origin, msg) -> str:
        python_version = sys.version.split()[0]
        os_info = platform.platform()
        conn = getattr(self.bot.db, "conn", None)
        sql_version = conn.get_server_info() if conn is not None else "unknown"
        return (
            f"BeBot v.Python-port -- OS: {os_info} -- Python: {python_version} "
            f"-- SQL: {sql_version}"
        )

    def check_bots(self, name, origin, msg: str):
        if not self.bot.accessallbots:
            msg = f"{self.bot.botname} {self.bot.dimension}"
        if msg:
            parts = msg.split(" ", 1)
            if len(parts) > 1 and parts[1]:
                return self.bot.core("bot_statistics").check_bots(name, origin, parts[0], parts[1])
            return self.bot.core("bot_statistics").check_bots(name, origin, parts[0])
        return self.bot.core("bot_statistics").check_bots(name, origin)
