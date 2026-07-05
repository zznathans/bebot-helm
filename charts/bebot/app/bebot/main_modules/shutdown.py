"""Ported from Modules/Shutdown.php.

Handles `shutdown`/`restart` on the `tell` channel. Mirrors the PHP's
2-second grace period (announce, then a `cron("1sec")` tick actually
disconnects and terminates the process) rather than shutting down
immediately, so the "The bot has been shutdown."/"is restarting." tells
and broadcasts have a chance to actually go out first.

Scope note: `die($this->crontime[1] . "\\n")` (PHP's hard process exit) is
ported as `sys.exit(0)` after printing the message and calling
`bot.disconnect()`, the same pattern already used by
`commodities/base.py`'s `BotError.set(fatal=True)` for a fatal error exit
elsewhere in this codebase.
"""
from __future__ import annotations

import sys
import time

from ..commodities.base import BaseActiveModule


class Shutdown(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("shutdown")
        self.register_command("tell", "shutdown", "SUPERADMIN")
        self.register_command("tell", "restart", "SUPERADMIN")
        self.help["description"] = "Handles bot shut down and restart.."
        self.help["command"] = {}
        self.help["command"]["shutdown"] = "Shuts down the bot."
        self.help["command"]["restart"] = "Restarts the bot."
        self.help["notes"] = (
            "If the bot is started in debug mode input _might_ be required in the console for the bot to restart."
        )
        self.bot.core("settings").create(
            "Shutdown", "QuietShutdown", False,
            "Do shutdown/restart quietly without spamming the guild channel?",
        )
        self.crontime: tuple[float, str] | None = None

    def command_handler(self, name, msg, origin):
        connected_time = self.bot.connected_time or 0
        if time.time() < connected_time + 10:
            # ignore commands for 1st 10 secs to prevent unwanted restart command while offline
            return False
        parts = msg.split(" ", 1)
        command = parts[0].lower()
        why = parts[1] if len(parts) > 1 and parts[1] else "no reason"
        if command == "shutdown":
            self.stop(name, "has been shutdown.", why)
        elif command == "restart":
            self.stop(name, "is restarting.", why)
        else:
            return f"##error##Error: Shutdown Module received Unknown Command ##highlight##{command}##end####end##"
        return False

    def stop(self, name, text, why) -> None:
        if why:
            why = f" (for {why})"
        else:
            why = ""
        if not self.bot.core("settings").get("Shutdown", "QuietShutdown"):
            self.bot.send_irc("", "", f"The bot {text}{why}")
            self.bot.send_gc(f"The bot {text}{why}")
            self.bot.send_pgroup(f"The bot {text}{why}")
        self.bot.send_tell(name, f"The bot {text}")
        self.crontime = (time.time() + 2, f"The bot {text}")
        self.register_event("cron", "1sec")

    def cron(self, duration=None) -> None:
        if self.crontime is not None and self.crontime[0] <= time.time():
            self.bot.disconnect()
            print(self.crontime[1])
            sys.exit(0)
