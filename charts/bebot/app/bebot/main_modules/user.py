"""Ported from Core/User.php.

Registers as "user". Depends on core("settings"), core("security"),
core("player"), core("chat"), core("tools"), core("online"), and
core("notify") -- the last is circularly dependent (Notify.php calls back
into core("user").add()), which is why user.py and notify.py were ported
together in one pass; see notify.py for the other half of the contract.

The `#___users` table itself is NOT created here: Main/03_Security.php
already creates it (main_modules/security.py, loaded earlier in the fixed
load order) with the final schema this module reads/writes, so there is
nothing to migrate or duplicate.

Scope cuts vs. the PHP original:
  * `core("whois")->lookup($name)` (AO-specific whois-cache warm-up when
    adding a user) is dropped, matching the precedent already established
    in main_modules/player.py's docstring: there is no Core/Ao/Whois.php
    port, and no synchronous blocking-socket equivalent exists in this
    asyncio port. The call site is simply omitted (it was fire-and-forget
    in the original, its return value was never used).
  * `core("security")->cache_mgr("add"/"rem", cache, name)` calls are
    dropped. The ported Security module (main_modules/security.py) has no
    such method -- it computes access levels live from the `#___users` /
    `#___security_*` tables on every check instead of maintaining an
    explicit in-memory group cache that needs manual invalidation, so
    there is nothing for this port to invalidate.
  * The AOC-specific "buddy list about to hit the 1k friend limit, hand
    the notify job to the next slave bot in the chain" branch in `add()`
    (`$this->bot->slave`, `strtolower($this->bot->game)=="aoc"`) is
    dropped: `Bot.game` is hardcoded to `"Ao"` in this port (see bot.py)
    and there is no `Bot.slave`/multi-bot-chain concept implemented, so
    this branch could never fire.

`del()` is renamed `delete()` since `del` is a Python reserved word,
matching the same rename already applied to PlayerNotes.del in
main_modules/player_notes.py.

Faithful-port note: PHP's `if ($new_id = core("player")->id($name))` relies
on PHP's "any object is truthy" semantics -- `core("player")->id()` can
return a `BotError` object on lookup failure, which is truthy in PHP (and
also truthy in Python, since BotError doesn't override `__bool__`), so a
lookup failure still takes the "we have a sane id" branch rather than the
`else` (deleted-character) branch. That looks like an upstream quirk, but
this port preserves it exactly rather than silently fixing it, since
diverging behavior here isn't part of this port's task.
"""
from __future__ import annotations

import time

from ..commodities.base import BasePassiveModule, BotError

_ACCESS_NAMES = {1: "a guest", 2: "a member", 3: "an admin"}
_ADMIN_GROUP_NAMES = {4: "owner", 3: "superadmin", 2: "admin", 1: "raidleader"}
_ADMIN_GROUP_LEVELS = {"owner": 4, "superadmin": 3, "admin": 2, "raidleader": 1}


def _normalize_name(name: str) -> str:
    name = name or ""
    return name[:1].upper() + name[1:].lower() if name else name


class User(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("user")
        defnot = bool(self.bot.guildbot)
        self.bot.core("settings").create(
            "Members", "Mark_notify", defnot, "Are members or guests automatically put on notify?"
        )
        self.bot.core("settings").create(
            "Members",
            "Notify_level",
            2,
            "Are only members (2) or guests too (1) automatically put on notify if Mark_notify is true?",
            "1;2",
        )
        if self.bot.core("settings").exists("Members", "AutoInvite"):
            # Remove the outdated autoinvite setting if it still exists, this is handled via preferences now:
            self.bot.core("settings").del_setting("Members", "AutoInvite")
        self.bot.core("settings").create(
            "Members",
            "AutoInviteGroup",
            "guests",
            "Which user group(s) should be automatically marked for autoinvite if AutoInvite is set to On?",
            "none;members;guests;both",
        )

    # -- add / delete / erase --------------------------------------------------

    def add(self, source: str, name: str, id=False, user_level: int = 0, silent: int = 0):
        change_level = False
        name = _normalize_name(name)
        if not name:
            self.error.set("You have to give a character to be added.")
            return self.error
        if isinstance(self.bot.core("player").id(name), BotError):
            self.error.set(f"{name} is not a valid character!")
            return self.error
        if not id:
            id = self.bot.core("player").id(name)
        if not id or isinstance(id, BotError):
            self.error.set(f"Player ##highlight##{name}##end## does not exist")
            return self.error

        db = self.bot.db
        result = db.select(f"SELECT nickname, user_level FROM #___users WHERE char_id = '{id}'")
        if result:
            if result[0][1] == -1 and not self.bot.guildbot:
                self.error.set(f"##highlight##{result[0][0]}##end## is already a member.")
                return self.error
            if result[0][1] != user_level and user_level > 0:
                change_level = True
            else:
                self.error.set(f"##highlight##{result[0][0]}##end## is already a member.")
                # Make sure correct name is in the table, same ID may have different names after name change.
                if name != result[0][0]:
                    db.query(f"UPDATE #___users SET nickname = '{name}' where char_id = '{id}'")
                return self.error

        result = db.select(f"SELECT char_id, user_level FROM #___users WHERE nickname = '{name}'")
        if result:
            if result[0][1] == -1 and not self.bot.guildbot:
                self.error.set(f"##highlight##{name}##end## is banned and cannot be added.")
                return self.error
            # Ok, we already have someone with the same name, double check userid's and erase the
            # old user to avoid problems.
            if id != result[0][0]:
                self.erase("", name, True, result[0][0])
        else:
            # Make sure we have a valid access level for the user.
            if user_level < 0:
                self.error.set(
                    f"##highlight##{user_level}##end## is not a valid access level. "
                    "The plugin trying to add a user might be broken."
                )
                return self.error

        members = {"id": id, "nickname": name}

        # Mark members for notify in org bots, otherwise no notify as default
        if self.bot.core("settings").get("Members", "Mark_notify") and user_level >= self.bot.core(
            "settings"
        ).get("Members", "Notify_level"):
            notifystate = 1
        else:
            notifystate = 0

        if change_level:
            db.query(
                f"UPDATE #___users SET user_level = '{user_level}', notify = '{notifystate}', "
                f"added_by = '{db.real_escape_string(source)}' WHERE char_id = '{members['id']}'"
            )
        else:
            db.query(
                "INSERT INTO #___users (char_id, nickname, added_by, added_at, user_level, notify) "
                f"VALUES('{members['id']}', '{members['nickname']}', '{db.real_escape_string(source)}', "
                f"'{int(time.time())}', '{user_level}', '{notifystate}')"
            )
        # If character is on notify add to buddy list
        if notifystate == 1 and not self.bot.core("chat").buddy_exists(members["id"]):
            self.bot.core("notify").update_cache()
            self.bot.core("chat").buddy_add(members["id"])
        # Tell them they have been added.
        if silent == 0:
            self.bot.send_tell(name, f"##highlight##{source}##end## has added you to the bot.")
        return f"Player ##highlight##{name}##end## has been added to the bot as {self.access_name(user_level)}"

    def delete(self, source: str, name: str, id: int = 0, silent: int = 0):
        reroll = 0
        name = _normalize_name(name)
        if not name:
            self.error.set("You have to give a character to be deleted.")
            return self.error
        db = self.bot.db
        result = db.select(f"SELECT char_id, nickname, user_level FROM #___users WHERE nickname = '{name}'")
        if not result:
            self.error.set(f"##highlight##{name}##end## is not in the user table, and cannot be deleted.")
            return self.error
        if result[0][2] == 0:
            self.error.set(f"##highlight##{name}##end## is not a member.")
            return self.error
        if result[0][2] == -1:
            self.error.set(f"##highlight##{name}##end## is banned and cannot be deleted.")
            return self.error

        new_id = self.bot.core("player").id(name)
        if new_id:
            if id == 0:
                id = result[0][0]
            elif id != new_id:
                reroll = 1
        else:
            self.erase("Automated delete for invalid userid", name)
            self.error.set(
                f"##highlight##{name}##end## does not appear to be a valid character. "
                "You might want to erase this user."
            )
            return self.error

        if reroll == 1:
            db.query(
                f"UPDATE #___users SET char_id = '{id}', user_level = '0', "
                f"deleted_by = '{db.real_escape_string(source)}', deleted_at = '{int(time.time())}', "
                f"notify = '0' WHERE nickname = '{name}'"
            )
        else:
            db.query(
                "UPDATE #___users SET user_level = '0', "
                f"deleted_by = '{db.real_escape_string(source)}', deleted_at = '{int(time.time())}', "
                f"notify = '0' WHERE char_id = '{id}'"
            )
            self.bot.core("chat").buddy_remove(id)
        if reroll != 1 and silent == 0:
            self.bot.send_tell(name, f"##highlight##{source}##end## has removed you from the bot.")
        # Make sure the usr isnt left on the online list
        db.query(
            f"UPDATE #___online SET status_gc = 0 WHERE botname = '{self.bot.botname}' AND nickname = '{name}'"
        )
        self.bot.core("online").logoff(name)
        self.bot.core("notify").update_cache()
        return f"##highlight##{name}##end## has been removed from member list."

    def erase(self, source: str, name: str, silent: int = 0, id: int = 0):
        reroll = 0
        deleted = 0
        if not name:
            self.error.set("You have to give a character name to be erased.")
            return self.error
        db = self.bot.db
        result = db.select(f"SELECT char_id, nickname, user_level FROM #___users WHERE nickname = '{name}'")
        if not result:
            self.error.set(f"##highlight##{name}##end## is not in the user table, and cannot be erased.")
            return self.error
        if result[0][1] == -1:
            self.error.set(f"##highlight##{name}##end## is banned and cannot be deleted.")
            return self.error

        new_id = self.bot.core("player").id(name)
        if new_id:
            if id == 0:
                id = result[0][0]
            elif id != new_id:
                reroll = 1
        else:
            deleted = 1

        if reroll == 1 or deleted == 1:
            db.query(f"DELETE FROM #___users WHERE nickname = '{name}'")
        else:
            db.query(f"DELETE FROM #___users WHERE char_id = {id}")
            self.bot.core("chat").buddy_remove(id)
        if deleted != 1 and reroll != 1 and silent == 0:
            self.bot.send_tell(name, f"##highlight##{source}##end## has removed you from the bot.")
        self.bot.core("online").logoff(name)
        self.bot.core("notify").update_cache()
        return f"##highlight##{name}##end## has been erased from member list."

    # -- misc helpers -----------------------------------------------------------

    def access_name(self, level) -> str:
        return _ACCESS_NAMES.get(int(level), "Error, unknown level")

    def admin_group_name(self, level) -> str | None:
        return _ADMIN_GROUP_NAMES.get(int(level))

    def admin_group_level(self, name: str) -> int:
        return _ADMIN_GROUP_LEVELS.get(str(name).lower(), 0)

    def get_db_uid(self, name: str) -> int:
        result = self.bot.db.select(f"SELECT char_id FROM #___users WHERE nickname = '{name}'")
        if result:
            return result[0][0]
        return 0
