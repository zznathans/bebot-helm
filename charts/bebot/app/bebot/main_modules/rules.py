"""Ported from Modules/Rules.php.

Shows the raid rules blob, sourced from `./Text/<botname>Rules.txt` if
present, else `./Text/Rules.txt`, else an empty body -- both relative to
the process's working directory, same as the PHP original. No scope
cuts.
"""
from __future__ import annotations

from pathlib import Path

from ..commodities.base import BaseActiveModule


class Rules(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("rules")
        self.register_command("all", "rules", "GUEST")

    def command_handler(self, name, msg, origin):
        return self.make_rules()

    def make_rules(self) -> str:
        content = "<font color=CCInfoHeadline> :::: RULES ::::</font>\n\n"
        bot_rules = Path("Text") / f"{self.bot.botname}Rules.txt"
        default_rules = Path("Text") / "Rules.txt"
        if bot_rules.is_file():
            content += bot_rules.read_text(errors="replace")
        elif default_rules.is_file():
            content += default_rules.read_text(errors="replace")
        return "<botname>'s Rules :: " + self.bot.core("tools").make_blob("click to view", content)
