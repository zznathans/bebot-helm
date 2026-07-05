"""Ported from Modules/StringFilterUi.php.

Thin chat-command UI over the already-ported `core("stringfilter")`
(main_modules/string_filter.py): lets ADMIN+ players list, add, and
remove entries from the bot's output string filter.
"""
from __future__ import annotations

import re

from ..commodities.base import BaseActiveModule, BotError

_ADD_REPLACE_RE = re.compile(r"^filter add (.+?) replace: (.+)$", re.IGNORECASE)
_ADD_RE = re.compile(r"^filter add (.+?)$", re.IGNORECASE)
_REM_RE = re.compile(r"^filter rem (.+)$", re.IGNORECASE)


class StringFilterUi(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_command("all", "filter", "ADMIN")
        self.register_module("string_filter_ui")
        self.help["description"] = "Add and remove strings to the bot's filter."
        self.help["command"] = {
            "filter": "- Display the current string filter list.",
            "filter add <string>": "- Replace <string> with default replacment text.",
            "filter add <string1> replace: <string2>": "- Replace <string1> with <string2>.",
            "filter rem <string>": "Remove <string> from the list.",
        }

    def command_handler(self, name, msg, origin) -> str | BotError:
        match = _ADD_REPLACE_RE.match(msg)
        if match:
            return self.add(match.group(1), match.group(2))
        match = _ADD_RE.match(msg)
        if match:
            return self.add(match.group(1))
        match = _REM_RE.match(msg)
        if match:
            return self.rem(match.group(1))
        return self.show(name)

    def add(self, string: str, new: str | None = None) -> str | BotError:
        return self.bot.core("stringfilter").add_string(string, new)

    def rem(self, string: str) -> str | BotError:
        return self.bot.core("stringfilter").rem_string(string)

    def show(self, source) -> str:
        strings = self.bot.core("stringfilter").get_strings()
        inside = "Filtered String List:\n\n"
        for string, replace in strings.items():
            inside += (
                f'Search for: "{string}" Replace with: "{replace}" '
                + self.bot.core("tools").chatcmd(f"filter rem {string}", "[REMOVE]")
            )
            inside += "\n"
        return self.bot.core("tools").make_blob("Filtered String List", inside)
