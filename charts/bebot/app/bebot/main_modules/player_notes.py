"""Ported (reduced) from Core/PlayerNotes.php.

Schema-version migration (`update_schema()`, and the underlying
`db.set_version`/`get_version`/`update_table` dance the PHP module used to
step a table from v1 -> v2 -> v3) is dropped, matching the precedent already
established in main_modules/settings.py: the table is created directly with
the final (v3) schema below -- a `timestamp` column (not the old `timestmp`
typo) and a `player VARCHAR(30) NOT NULL` column -- instead of migrating an
older layout forward. There is nothing to migrate for a fresh Python port.

`del` is a Python reserved keyword, so the PHP module's `del($pnid)` method
is ported as `delete(pnid)`.
"""
from __future__ import annotations

import time

from ..commodities.base import BasePassiveModule, BotError

_CLASS_NAMES = {"admin": 2, "ban": 1}


def _is_numeric(value: str) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


class PlayerNotes(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        db = bot.db
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('player_notes', False)} "
            "(pnid INT NOT NULL AUTO_INCREMENT PRIMARY KEY, "
            "player VARCHAR(30) NOT NULL, "
            "author VARCHAR(30) NOT NULL, "
            "note VARCHAR(255) NOT NULL, "
            "class TINYINT NOT NULL DEFAULT 0, "
            "timestamp INT UNSIGNED NOT NULL)"
        )
        self.register_module("player_notes")

    def _resolve_class(self, class_) -> int:
        text = str(class_).lower()
        if not _is_numeric(text):
            value = _CLASS_NAMES.get(text, 0)
        else:
            value = int(float(text))
        if value > 3:
            value = 3  # Currently only 3 classes are defined.
        return value

    def add(self, player: str, author: str, note: str, class_) -> str | BotError:
        author = self.bot.core("tools").sanitize_player(author)
        player = self.bot.core("tools").sanitize_player(player)
        class_value = self._resolve_class(class_)
        if len(note) > 255:
            note = note[:254]
        db = self.bot.db
        note_escaped = db.real_escape_string(note)
        author_escaped = db.real_escape_string(author)
        player_escaped = db.real_escape_string(player)
        sql = (
            "INSERT INTO #___player_notes (player, author, note, class, timestamp) "
            f"VALUES ('{player_escaped}', '{author_escaped}', '{note_escaped}', "
            f"{class_value}, {int(time.time())})"
        )
        result = db.query(sql)
        if result is not False:
            select_sql = (
                f"SELECT pnid FROM #___player_notes WHERE player = '{player_escaped}' "
                "ORDER BY pnid DESC LIMIT 1"
            )
            rows = db.select(select_sql)
            pnid = rows[0][0]
            return f'Successfully added "{note}" note to {player} as note id {pnid}'
        self.error.set("An unknown error occurred. Check your bot console for more information.")
        return self.error

    def delete(self, pnid) -> str | BotError:
        result = self.bot.db.return_query(f"DELETE FROM #___player_notes WHERE pnid = {pnid}")
        if result:
            return f"Deleted player note {pnid}"
        self.error.set(f"Could not delete player note {pnid}. No note with that ID could be found.")
        return self.error

    def update(self, pnid, what: str, newvalue) -> BotError | None:
        if not isinstance(pnid, int):
            self.error.set("Only integers can be player note ID numbers.")
            return self.error
        db = self.bot.db
        what_escaped = db.real_escape_string(what)
        newvalue_escaped = db.real_escape_string(newvalue)
        sql = f"UPDATE #___player_notes SET {what_escaped} = {newvalue_escaped} WHERE pnid = {pnid}"
        if not db.query(sql):
            self.error.set(f"There was a MySQL error when updating '{what}' to '{newvalue}'.")
            return self.error
        return None

    def get_notes(self, name: str, player: str = "All", pnid="all", order: str = "ASC"):
        name = self.bot.core("tools").sanitize_player(name)  # Name of person requesting notes.
        player = self.bot.core("tools").sanitize_player(player)  # Notes attached to this player.
        sql = "SELECT * FROM #___player_notes"
        where = "WHERE"
        if player != "All":
            sql += f" {where} player = '{player}'"
            where = "AND"
        leader = self.bot.core("security").check_access(name, "LEADER")
        if not leader:  # Only show general notes to non leaders.
            sql += f" {where} class = 0"
            where = "AND"
        if str(pnid).lower() != "all" and _is_numeric(str(pnid)):
            sql += f" {where} pnid = {pnid}"
        sql += f" ORDER BY pnid {order}"
        result = self.bot.db.select(sql, True)
        if not result:
            self.error.set(f"No notes found for '{player}'", False)
            return self.error
        return result
