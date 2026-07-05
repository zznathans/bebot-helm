"""Ported from Main/15_Notify.php.

Registers as "notify". Maintains an in-memory cache (nickname -> True) of
`#___users` rows with `notify = 1`, mirrored from the `#___users` table
that main_modules/security.py creates (see user.py's docstring -- neither
module creates that table itself).

This closes the gap main_modules/logon_notifies.py's docstring called out:
`LogonNotifies.buddy()` calls `self.bot.core("notify").check(name)`, and
`Notify.check(name)` below implements exactly that signature, so the call
now does a real notify-list lookup instead of hitting Bot's dummy-module
fallback.

Circular dependency with user.py: `Notify.add()` calls
`self.bot.core("user").add(source, user, 0, 0, 1)` (silently add an unknown
name as an anonymous, unlisted user before marking it for notify) exactly
as Main/15_Notify.php does, and `User.add/delete/erase` call back into
`self.bot.core("notify").update_cache()` to keep this module's cache in
sync whenever `#___users.notify` changes underneath it.

No scope cuts: this module has no whois/online/security touch points in
the original, and no schema-version migration logic to drop (pure
in-memory cache plus reads/writes against the already-existing
`#___users` table).
"""
from __future__ import annotations

from ..commodities.base import BasePassiveModule, BotError


def _normalize_name(name: str) -> str:
    name = name or ""
    return name[:1].upper() + name[1:].lower() if name else name


class Notify(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("notify")
        self.cache: dict[str, bool] = {}
        self.update_cache()

    def update_cache(self) -> None:
        self.cache = {}
        rows = self.bot.db.select("SELECT nickname FROM #___users WHERE notify = 1") or []
        for row in rows:
            self.cache[_normalize_name(row[0])] = True

    def check(self, name: str) -> bool:
        return _normalize_name(name) in self.cache

    def add(self, source: str, user: str):
        user = self.bot.core("tools").sanitize_player(user)
        id = self.bot.core("player").id(user)
        if isinstance(id, BotError):
            self.error.set(f"{user} is no valid character name!")
            return self.error
        db = self.bot.db
        usr = db.select(f"SELECT notify FROM #___users WHERE nickname = '{user}'")
        if not usr:
            # Need to add $user to users table as anonymous and silent
            self.bot.core("user").add(source, user, 0, 0, 1)
        else:
            if usr[0][0] == 1:
                self.error.set(f"{user} is already on the notify list!")
                return self.error
        db.query(f"UPDATE #___users SET notify = 1 WHERE nickname = '{user}'")
        self.cache[user] = True
        self.bot.core("chat").buddy_add(id)
        return f"{user} added to notify list!"

    def delete(self, user: str):
        user = self.bot.core("tools").sanitize_player(user)
        id = self.bot.core("player").id(user)
        if not isinstance(id, int) or id == 0:
            self.error.set(f"{user} is no valid character name!")
            return self.error
        db = self.bot.db
        usr = db.select(f"SELECT notify FROM #___users WHERE nickname = '{user}'")
        if not usr:
            self.error.set(f"{user} is not on notify list!")
            return self.error
        if usr[0][0] == 0:
            self.error.set(f"{user} is not on notify list!")
            return self.error
        db.query(f"UPDATE #___users SET notify = 0 WHERE nickname = '{user}'")
        self.cache.pop(user, None)
        self.bot.core("chat").buddy_remove(id)
        db.query(
            f"UPDATE #___online SET status_gc = 0 WHERE nickname = '{user}' "
            f"AND botname = '{self.bot.botname}'"
        )
        return f"{user} removed from notify list!"

    def list_cache(self) -> str:
        count = 0
        msg = ""
        for key, value in self.cache.items():
            notify_db = self.bot.db.select(f"SELECT notify FROM #___users WHERE nickname = '{key}'")
            db_value = notify_db[0][0] if notify_db else None
            msg += key
            if value:
                msg += " [##green##Cache##end##]"
            else:
                msg += " [##red##Cache##end##]"
            if db_value == 1:
                msg += "[##green##DB##end##]"
            else:
                msg += "[##red##DB##end##]"
            if bool(db_value) != value:
                msg += " ##yellow##MISMATCH##end##\n"
            else:
                msg += "\n"
            count += 1
        return f"{count} members in <botname>'s notify cache :: " + self.bot.core("tools").make_blob(
            "click to view", msg
        )

    def clear_cache(self) -> str:
        count = len(self.cache)
        self.cache = {}
        return f"Removed {count} members from <botname>'s notify cache."

    def get_all(self) -> dict[str, bool]:
        return self.cache
