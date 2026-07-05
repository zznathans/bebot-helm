"""Ported (reduced) from Main/03_Security.php.

Scope cut: the full group-management admin command set (`admin`, `adduser`,
`deluser`, `addgroup`, `delgroup`, `security levels/groups/whois` chat
commands) is NOT ported -- that's an in-game admin UI on top of the access
system, not something the bot needs to boot and dispatch commands. What
*is* ported is the actual access-level computation everything else in the
bot depends on: owner/superadmin from config, the `#___users` table
(guest/member), the `#___security_groups`/`#___security_members` tables,
and ban checking.

Org-rank-based auto access levels (`#___security_org`, populated from the
guild roster) are not wired up either since Roster (Main/10_Roster.php)
isn't ported yet -- guild members need to be added to `#___users` some
other way (directly in the DB, or a future admin-command port) until then.
"""
from __future__ import annotations

import time

from ..commodities.base import BaseActiveModule, BotError

OWNER = 256
SUPERADMIN = 255
ADMIN = 192
LEADER = 128
MEMBER = 2
GUEST = 1
ANONYMOUS = 0
BANNED = -1

_LEVEL_NAMES = {
    OWNER: "OWNER", SUPERADMIN: "SUPERADMIN", ADMIN: "ADMIN", LEADER: "LEADER",
    MEMBER: "MEMBER", GUEST: "GUEST", ANONYMOUS: "ANONYMOUS", BANNED: "BANNED",
}
_NAME_LEVELS = {v: k for k, v in _LEVEL_NAMES.items()}


def level_value(level) -> int:
    if isinstance(level, str):
        return _NAME_LEVELS.get(level.upper(), ANONYMOUS)
    return int(level)


class Security(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("security")
        self.register_event("connect")

        db = bot.db
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('security_groups', True)} "
            "(gid INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, name VARCHAR(35) UNIQUE, "
            "description VARCHAR(80), access_level TINYINT UNSIGNED NOT NULL DEFAULT 0)"
        )
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('security_members', True)} "
            "(id INT UNIQUE NOT NULL AUTO_INCREMENT, name VARCHAR(50), gid INT, "
            "PRIMARY KEY (name, gid), KEY (id))"
        )
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('users', True)} "
            "(char_id INT, nickname VARCHAR(50) PRIMARY KEY, added_by VARCHAR(50), added_at INT, "
            "deleted_by VARCHAR(50), deleted_at INT, user_level TINYINT DEFAULT 0, updated_at INT, "
            "banned_by VARCHAR(50), banned_at INT, banned_for VARCHAR(255), banned_until INT, notify TINYINT DEFAULT 0)"
        )

        self.owner = (bot.owner or "").capitalize()
        self.super_admin = {k.capitalize(): v for k, v in (bot.super_admin or {}).items()}

    def connect(self) -> None:
        pass

    def command_handler(self, source, msg, msgtype):
        # Admin command UI not ported.
        return False

    # -- access checks --------------------------------------------------------
    def is_banned(self, player: str) -> bool:
        row = self.bot.db.select(
            f"SELECT user_level FROM #___users WHERE nickname = '{self.bot.db.real_escape_string(player)}'"
        )
        return bool(row) and row[0][0] == BANNED

    def get_access_level(self, player: str) -> int:
        player = (player or "").capitalize()
        if not player:
            return ANONYMOUS
        if player == self.owner:
            return OWNER
        if player in self.super_admin:
            return SUPERADMIN
        row = self.bot.db.select(
            f"SELECT user_level FROM #___users WHERE nickname = '{self.bot.db.real_escape_string(player)}'"
        )
        base_level = row[0][0] if row else ANONYMOUS
        if base_level == BANNED:
            return BANNED
        group_rows = self.bot.db.select(
            "SELECT g.access_level FROM #___security_members m "
            "JOIN #___security_groups g ON g.gid = m.gid "
            f"WHERE m.name = '{self.bot.db.real_escape_string(player)}'"
        )
        highest = max([r[0] for r in group_rows], default=0)
        return max(base_level, highest)

    def check_access(self, player, level) -> bool:
        if isinstance(player, BotError):
            return False
        return self.get_access_level(player) >= level_value(level)

    def get_access_name(self, level: int) -> str:
        if level > SUPERADMIN:
            return "OWNER"
        for value in sorted(_LEVEL_NAMES, reverse=True):
            if level >= value:
                return _LEVEL_NAMES[value]
        return "ANONYMOUS"

    def set_ban(self, admin: str, target: str, reason: str = "None given.", endtime: int = 0):
        admin = admin.capitalize()
        target = target.capitalize()
        if self.check_access(target, "OWNER"):
            self.error.set(f"{target} is the bot owner and cannot be banned.")
            return self.error
        db = self.bot.db
        db.query(
            "INSERT INTO #___users (nickname, added_by, added_at, banned_by, banned_at, banned_for, "
            "banned_until, user_level, updated_at) VALUES "
            f"('{db.real_escape_string(target)}', '{db.real_escape_string(admin)}', {int(time.time())}, "
            f"'{db.real_escape_string(admin)}', {int(time.time())}, '{db.real_escape_string(reason)}', "
            f"{int(endtime)}, {BANNED}, {int(time.time())}) "
            "ON DUPLICATE KEY UPDATE banned_by=VALUES(banned_by), banned_at=VALUES(banned_at), "
            "user_level=VALUES(user_level), updated_at=VALUES(updated_at), banned_for=VALUES(banned_for), "
            "banned_until=VALUES(banned_until)"
        )
        return f"Banned {target} from {self.bot.botname}."

    def rem_ban(self, admin: str, target: str):
        target = target.capitalize()
        db = self.bot.db
        db.query(f"UPDATE #___users SET user_level = 0 WHERE nickname = '{db.real_escape_string(target)}'")
        return f"Unbanned {target} from {self.bot.botname}. {target} is now anonymous."

    def add_user(self, admin: str, target: str, level_name: str | None = None):
        admin = admin.capitalize()
        target = target.capitalize()
        if self.is_banned(target):
            self.error.set(f"{target} is banned.")
            return self.error
        level_name = level_name or ("GUEST" if self.bot.guildbot else "MEMBER")
        db = self.bot.db
        db.query(
            "INSERT INTO #___users (nickname, added_by, added_at, user_level, updated_at) VALUES "
            f"('{db.real_escape_string(target)}', '{db.real_escape_string(admin)}', {int(time.time())}, "
            f"{level_value(level_name)}, {int(time.time())}) "
            "ON DUPLICATE KEY UPDATE added_by=VALUES(added_by), added_at=VALUES(added_at), "
            "user_level=VALUES(user_level), updated_at=VALUES(updated_at)"
        )
        return f"Added {target} as a {level_name}."

    def del_user(self, admin: str, target: str):
        target = target.capitalize()
        db = self.bot.db
        db.query(
            f"UPDATE #___users SET user_level = 0, deleted_by = '{db.real_escape_string(admin)}', "
            f"deleted_at = {int(time.time())}, notify = 0 WHERE nickname = '{db.real_escape_string(target)}'"
        )
        return f"{target} has been removed from {self.bot.botname}."
