"""Ported from Modules/SetDebug.php.

Trivial `tell`-only OWNER command that flips `bot.debug`. No scope cuts.
"""
from __future__ import annotations

from ..commodities.base import BaseActiveModule


class SetDebug(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("set_debug")
        self.register_command("tell", "setdebug", "OWNER")

    def command_handler(self, name, msg, origin):
        self.bot.debug = not self.bot.debug
        if self.bot.debug:
            return "Debugging output enabled!"
        return "Debugging output disabled!"
