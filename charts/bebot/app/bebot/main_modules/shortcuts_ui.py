"""Ported from Modules/ShortCutsUi.php.

Thin chat-command UI over the already-ported `core("shortcuts")`
(main_modules/shortcuts.py): lists the defined shortcuts as a clickable
blob (with a "[DELETE]" link per row), and lets a SUPERADMIN add a new
shortcut or delete one by its numeric row id.

Faithful-port note on `shortcuts add <short> <long>`: the PHP regex
`/^shortcuts add (.*) (.*)$/i` is greedy, so it splits on the *last*
space in the remainder -- everything up to that point becomes `<short>`
and only the final word becomes `<long>`. That means multi-word
descriptions can't actually be added via this command (only their last
word would be stored as "long"), which looks like a bug in the original,
but it's preserved here verbatim rather than "fixed" since this is a
straight port. Nothing here does `stripslashes()` on the way out, since
the Python `core("shortcuts")`/db layer never adds backslash-escaping to
stored values in the first place (unlike PHP's `addslashes()`-on-write
convention), so there is nothing to strip back off on read.
"""
from __future__ import annotations

import re

from ..commodities.base import BaseActiveModule

_ADD_RE = re.compile(r"^shortcuts add (.*) (.*)$", re.IGNORECASE)
_DEL_RE = re.compile(r"^shortcuts del (\d+)$", re.IGNORECASE)


class ShortcutsUi(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("shortcuts_ui")
        self.register_command("all", "shortcuts", "SUPERADMIN")
        self.help["description"] = (
            "Allows you view, add and delete entries in the shortcut database."
        )
        self.help["command"] = {
            "shortcuts": (
                "Shows currently existing shortcuts with corresponding long "
                "entries and allows deleting selected entries."
            ),
            "shortcuts add <short> <long>": (
                "Adds <short> as shortcut for <long> to the database. Any "
                "quote is removed."
            ),
        }

    # -- dispatch ---------------------------------------------------------------
    def command_handler(self, name, msg, origin):
        if re.match(r"^shortcuts$", msg, re.IGNORECASE):
            return self.show_shortcuts()
        match = _ADD_RE.match(msg)
        if match:
            return self.add(match.group(1), match.group(2))
        match = _DEL_RE.match(msg)
        if match:
            return self.delete(int(match.group(1)))
        return None

    # -- views --------------------------------------------------------------------
    def show_shortcuts(self):
        shortcuts = self.bot.db.select(
            "SELECT shortcut, long_desc, id FROM #___shortcuts ORDER BY shortcut ASC"
        )
        if not shortcuts:
            return "No shortcuts defined!"
        tools = self.bot.core("tools")
        blob = "##ao_infoheader##The following shortcuts are defined:##end##\n"
        for shortcut, long_desc, entry_id in shortcuts:
            blob += f"\n##ao_infotext##{shortcut} ##end##short for##ao_infotext## "
            blob += f"{long_desc}##end## "
            blob += tools.chatcmd(f"shortcuts del {entry_id}", "[DELETE]")
        return tools.make_blob("Defined shortcuts", blob)

    # -- mutation -------------------------------------------------------------------
    def add(self, short: str, long: str):
        short = short.replace("'", "").replace('"', "")
        long = long.replace("'", "").replace('"', "")
        if len(short) >= len(long):
            return "Short cannot be longer (nor equal) than long."
        return self.bot.core("shortcuts").add(short, long)

    def delete(self, entry_id: int):
        return self.bot.core("shortcuts").delete_id(entry_id)
