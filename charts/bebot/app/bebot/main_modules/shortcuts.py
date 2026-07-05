"""Ported from Core/Shortcuts.php.

Registers itself as bot.core("shortcuts"). On construction it makes sure
the #___shortcuts table exists and seeds it (INSERT IGNORE, so re-runs are
harmless) with the default set of chat-rank shortcuts used by the original
bot (Pres/President, Gen/General, ...). Both lookup directions are then
cached in memory as plain dicts keyed in lowercase, rebuilt on an hourly
cron tick (register_event("cron", "1hour")) and after every add/delete.

Faithful-port note: delete_id() mirrors the PHP original's cache-eviction
lines exactly, including what looks like a pre-existing bug there --
`unset($this->long[strtolower($ret[0][1])])` uses the long description as
the key into `$long` (which is actually indexed by shortcut), and likewise
for `$short`/`$ret[0][0]`. In practice this means the in-memory caches are
usually *not* cleaned up correctly by delete_id() (the stale entries would
still resolve until the next hourly cron rebuild), even though the
database row is deleted correctly and the returned message is accurate.
That behavior is intentionally preserved here rather than "fixed", since
this is a straight port.
"""
from __future__ import annotations

from ..commodities.base import BasePassiveModule, BotError

DEFAULT_SHORTCUTS: list[tuple[str, str]] = [
    ("Pres", "President"),
    ("Gen", "General"),
    ("SC", "Squad Commander"),
    ("UC", "Unit Commander"),
    ("UL", "Unit Leader"),
    ("UM", "Unit Member"),
    ("App", "Applicant"),
    ("Dir", "Director"),
    ("BM", "Board Member"),
    ("Exec", "Executive"),
    ("Mem", "Member"),
    ("Adv", "Advisor"),
    ("Vet", "Veteran"),
    ("Mon", "Monarch"),
    ("Coun", "Counsel"),
    ("Fol", "Follower"),
    ("Anar", "Anarchist"),
    ("Lord", "Lord"),
    ("Knght", "Knight"),
    ("Vas", "Vassal "),
    ("Peas", "Peasant"),
]


class Shortcuts(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        db = bot.db
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('shortcuts', False)} "
            "(id INT NOT NULL AUTO_INCREMENT UNIQUE, shortcut VARCHAR(20) NOT NULL PRIMARY KEY, "
            "long_desc VARCHAR(255) NOT NULL UNIQUE)"
        )
        values = ", ".join(f"('{short}', '{long}')" for short, long in DEFAULT_SHORTCUTS)
        db.query(f"INSERT IGNORE INTO #___shortcuts (`shortcut`, `long_desc`) VALUES {values}")
        self.register_module("shortcuts")
        self.register_event("cron", "1hour")
        self.short: dict[str, str] = {}
        self.long: dict[str, str] = {}
        self.create_caches()

    def create_caches(self) -> None:
        """Rebuild both lookup dicts (indexed in lowercase) from the DB."""
        self.short = {}
        self.long = {}
        rows = self.bot.db.select("SELECT shortcut, long_desc FROM #___shortcuts")
        for shortcut, long_desc in rows or []:
            self.short[long_desc.lower()] = shortcut
            self.long[shortcut.lower()] = long_desc

    def cron(self, duration=None) -> None:
        self.create_caches()

    def get_short(self, long: str) -> str:
        """Returns the shortcut for the argument if it exists, else the argument unmodified."""
        return self.short.get(long.lower(), long)

    def get_long(self, short: str) -> str:
        """Returns the long description for the shortcut if it exists, else the argument unmodified."""
        return self.long.get(short.lower(), short)

    def add(self, short: str, long: str) -> str | BotError:
        if long.lower() in self.short:
            self.error.set(
                f'The text {long} already is in the databse with shortcut "{self.short[long.lower()]}"!'
            )
            return self.error
        if short.lower() in self.long:
            self.error.set(
                f'The shortcut {short} is already defined for "{self.long[short.lower()]}"!'
            )
            return self.error
        self.long[short.lower()] = long
        self.short[long.lower()] = short
        db = self.bot.db
        db.query(
            "INSERT INTO #___shortcuts (shortcut, long_desc) VALUES "
            f"('{db.real_escape_string(short)}', '{db.real_escape_string(long)}')"
        )
        return f'New shortcut "{short}" added to database with corresponding long entry "{long}".'

    def delete_shortcut(self, short: str) -> str | BotError:
        if short.lower() not in self.long:
            self.error.set(f'The shortcut "{short}" does not exist in the database!')
            return self.error
        long_desc = self.long[short.lower()]
        del self.short[long_desc.lower()]
        del self.long[short.lower()]
        db = self.bot.db
        db.query(f"DELETE FROM #___shortcuts WHERE shortcut = '{db.real_escape_string(short)}'")
        return f'The shortcut "{short}" and the corresponding long description "{long_desc}" were deleted!'

    def delete_description(self, long: str) -> str | BotError:
        if long.lower() not in self.short:
            self.error.set(f'The description "{long}" does not exist in the database!')
            return self.error
        short = self.short[long.lower()]
        del self.long[short.lower()]
        del self.short[long.lower()]
        db = self.bot.db
        db.query(f"DELETE FROM #___shortcuts WHERE long_desc = '{db.real_escape_string(long)}'")
        return f'The description "{long}" and the corresponding shortcut "{short}" were deleted!'

    def delete_id(self, entry_id: int) -> str | BotError:
        rows = self.bot.db.select(f"SELECT shortcut, long_desc FROM #___shortcuts WHERE id = {entry_id}")
        if not rows:
            self.error.set(f"No entry with the ID {entry_id} exists!")
            return self.error
        shortcut, long_desc = rows[0]
        # See the faithful-port note in the module docstring: these two lines
        # match the PHP original's (seemingly buggy) key choice verbatim.
        self.long.pop(long_desc.lower(), None)
        self.short.pop(shortcut.lower(), None)
        self.bot.db.query(f"DELETE FROM #___shortcuts WHERE id = {entry_id}")
        return f"The entry with the ID {entry_id} has been deleted. Shortcut: {shortcut}, long description: {long_desc}."
