"""Ported from Modules/Say.php (class `Say`).

Lets an admin make the bot say something (`say`), send a raw `/tell` to a
player (`sendtell`), forward another command's help text to a player
(`sendhelp`), and lets anyone ask who last made the bot talk
(`whosaidthat`). Depends on `core("settings")` (the `Say/OutputChannel`
setting controlling where `!say` output goes) and, faithfully following
the PHP, `core("whois")` for the `sendtell`/`sendhelp` existence checks.

Scope notes / intentional deviations from the PHP:
  * `core("whois")` is never registered as a core module in this port (see
    the same note already made in `main_modules/flexible_security.py` and
    `main_modules/alts.py`): `bot.core("whois")` returns the bot's dummy
    fallback module, whose `.lookup()` returns an error *string*, not a
    `BotError` instance. The PHP's `... instanceof BotError` check is kept
    verbatim here (`isinstance(..., BotError)`), so in practice -- same as
    upstream precedent -- this existence check never actually fires today;
    it will start working the moment a real `whois` module is ported.
  * `sendhelp()`'s `$this->bot->send_help($args[0], $args[1])` call is kept
    as `self.bot.send_help(player, command)`.
"""
from __future__ import annotations

import time

from ..commodities.base import BaseActiveModule, BotError


class Say(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.whosaidthat_info: dict[str, object] = {}

        self.register_command("all", "say", "ADMIN")
        self.register_command("all", "whosaidthat", "MEMBER")
        self.register_command("all", "sendtell", "ADMIN")
        self.register_command("all", "sendhelp", "ADMIN")
        self.register_module("say")

        self.bot.core("settings").create(
            "Say",
            "OutputChannel",
            "both",
            "Into which channel should the output of !say be sent? Either gc, pgmsg, both or original channel.",
            "gc;pgmsg;both;origin",
        )

        self.help["description"] = "Makes the bot say things."
        self.help["command"] = {
            "say something": "Makes that bot say 'something' in org/private channel.",
            "sendtell someone message": "Makes the bot send 'message' in /tell to someone.",
            "sendhelp someone command": "Makes the bot send command's help in /tell to someone.",
            "whosaidthat": "Find out who made the bot say that.",
        }

    # -- dispatch ---------------------------------------------------------------
    def command_handler(self, name, msg, source):
        com, _, args = msg.partition(" ")
        com = com.lower()

        if com == "say":
            said = self.saythis(name, args)
            channel = str(self.bot.core("settings").get("Say", "OutputChannel")).lower()
            if channel == "origin":
                return said
            self.bot.send_output(name, said, channel)
            return False
        if com == "sendtell":
            return self.sendtell(name, args)
        if com == "sendhelp":
            return self.sendhelp(name, args)
        if com == "whosaidthat":
            return self.whosaidthat()

        self.bot.send_help(name)
        return False

    # -- say ------------------------------------------------------------------------
    def saythis(self, name: str, message: str) -> str:
        self.whosaidthat_info = {"time": time.time(), "name": name, "what": message}
        return message

    def sendhelp(self, name: str, message: str) -> str:
        if not message:
            return "Please provide player & command"
        args = message.split(" ")
        target = args[0]
        if isinstance(self.bot.core("whois").lookup(target), BotError):
            return f"Player {target} doesn't exist"
        if name.lower() == target.lower():
            return "No use to send help to yourself"
        if len(args) == 2 and args[1]:
            self.whosaidthat_info = {"time": time.time(), "name": name, "what": message}
            self.bot.send_help(target, args[1])
            return f"Help sent to {target}"
        return "Can't send wrong command"

    def sendtell(self, name: str, message: str) -> str:
        if not message:
            return "Please provide player & message"
        target, _, rest = message.partition(" ")
        if isinstance(self.bot.core("whois").lookup(target), BotError):
            return f"Player {target} does not exist"
        if name.lower() == target.lower():
            return "No use to send a tell to yourself"
        if rest:
            self.whosaidthat_info = {"time": time.time(), "name": name, "what": message}
            self.bot.send_tell(target, rest)
            return f"Message sent to {target}"
        return "Can't send empty message"

    # -- whosaidthat ------------------------------------------------------------------
    def whosaidthat(self) -> str:
        if not self.whosaidthat_info:
            return "Nobody has used the say command since I logged in."
        elapsed = int(time.time() - self.whosaidthat_info["time"])
        return (
            f"{self.whosaidthat_info['name']} made me say \"{self.whosaidthat_info['what']}\" "
            f"{elapsed} seconds ago."
        )
