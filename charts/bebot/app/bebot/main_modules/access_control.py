"""Ported from Main/09_AccessControl.php.

Schema-migration code (update_table's version-1/2/3 ALTERs) is dropped --
we always create the current schema directly. The `access_control` chat
command / settings-UI to change levels in-game is not ported (see
security.py's docstring for the same cut); create()/create_subcommand()/
check_rights()/get_min_rights() -- the mechanism every register_command()
call relies on -- are fully ported.
"""
from __future__ import annotations

from ..commodities.base import BasePassiveModule
from .security import OWNER, level_value

ACCESS_LEVELS = ["ANONYMOUS", "GUEST", "MEMBER", "LEADER", "ADMIN", "SUPERADMIN", "OWNER", "DISABLED", "DELETED"]
SECURITY_LEVELS = ACCESS_LEVELS[:7]
DENY_LEVELS = {"DISABLED"}
CHANNELS = {"tell", "pgmsg", "gc", "extpgmsg", "all"}


class AccessControl(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        db = bot.db
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('access_control', True)} ("
            "command varchar(50) NOT NULL default '', subcommand varchar(50) NOT NULL default '*', "
            "channel varchar(20) NOT NULL default '', "
            "minlevel enum('ANONYMOUS','GUEST','MEMBER','LEADER','ADMIN','SUPERADMIN','OWNER','DISABLED','DELETED') "
            "default 'DISABLED', PRIMARY KEY (command, subcommand, channel))"
        )
        self.register_module("access_control")
        self.register_event("cron", "1hour")
        bot.core("settings").create(
            "AccessControl", "DefaultLevel", "SUPERADMIN",
            "Minimal access level granted to new commands by default.",
            "ANONYMOUS;GUEST;MEMBER;LEADER;ADMIN;SUPERADMIN;OWNER;DISABLED",
        )
        bot.core("settings").create("AccessControl", "LockGc", False, "Lock all commands in guild chat?", "On;Off", True)
        bot.core("settings").create("AccessControl", "LockPgroup", False, "Lock all commands in the private group?", "On;Off", True)
        self._startup = True
        self.access_cache: dict[str, dict[str, dict[str, str]]] = {}
        self.create_access_cache()

    def cron(self, duration=None) -> None:
        if self._startup:
            self._startup = False
            channels = ["tell", "pgmsg", "extpgmsg"] + (["gc"] if self.bot.guildbot else [])
            for channel in channels:
                for command in list(self.bot.commands.get(channel, {})):
                    rights = self.bot.db.select(
                        f"SELECT * FROM #___access_control WHERE command = '{command}' AND channel = '{channel}'"
                    )
                    if not rights:
                        level = self.bot.core("settings").get("Accesscontrol", "Defaultlevel")
                        self.bot.db.query(
                            "INSERT INTO #___access_control (command, subcommand, channel, minlevel) "
                            f"VALUES ('{command}', '*', '{channel}', '{level}')"
                        )
        self.create_access_cache()
        self.bot.core("help").update_cache()

    def create_access_cache(self) -> None:
        self.access_cache = {}
        rows = self.bot.db.select("SELECT * FROM #___access_control") or []
        for command, subcommand, channel, minlevel in rows:
            self.access_cache.setdefault(command.lower(), {}).setdefault(subcommand.lower(), {})[channel.lower()] = minlevel.upper()

    # -- runtime checks ---------------------------------------------------------
    def _do_check(self, user, command: str, subcommand: str, channel: str) -> bool:
        level = self.access_cache[command.lower()][subcommand.lower()][channel.lower()]
        if level in DENY_LEVELS:
            return False
        return self.bot.core("security").check_access(user, level)

    def check_rights(self, user, command: str, msg: str, channel: str) -> bool:
        if (channel == "gc" and self.bot.core("settings").get("AccessControl", "LockGc")) or \
                (channel == "pgmsg" and self.bot.core("settings").get("AccessControl", "LockPgroup")):
            return False
        command_l = command.lower()
        entry = self.access_cache.get(command_l, {})
        if " " not in msg:
            if "$" in entry and channel.lower() in entry["$"]:
                return self._do_check(user, command, "$", channel)
            if "*" in entry and channel.lower() in entry["*"]:
                return self._do_check(user, command, "*", channel)
            return False
        parts = msg.split(" ", 2)
        sub = parts[1]
        if sub in ("*", "$"):
            if "*" in entry and channel.lower() in entry["*"]:
                return self._do_check(user, command, "*", channel)
            return False
        sub_l = sub.lower()
        if sub_l in entry and channel.lower() in entry[sub_l]:
            if entry[sub_l][channel.lower()] != "DELETED":
                return self._do_check(user, command, sub_l, channel)
        if "*" in entry and channel.lower() in entry["*"]:
            return self._do_check(user, command, "*", channel)
        return False

    def _do_min_check(self, command: str, subcommand: str, channel: str) -> int:
        level = self.access_cache[command.lower()][subcommand.lower()][channel.lower()]
        if level in DENY_LEVELS:
            return OWNER + 1
        return level_value(level)

    def get_min_rights(self, command: str, msg: str, channel: str) -> int:
        if (channel == "gc" and self.bot.core("settings").get("AccessControl", "LockGc")) or \
                (channel == "pgmsg" and self.bot.core("settings").get("AccessControl", "LockPgroup")):
            return OWNER + 1
        command_l = command.lower()
        entry = self.access_cache.get(command_l, {})
        if " " not in msg:
            if "$" in entry and channel.lower() in entry["$"]:
                return self._do_min_check(command, "$", channel)
            if "*" in entry and channel.lower() in entry["*"]:
                return self._do_min_check(command, "*", channel)
            return OWNER + 1
        parts = msg.split(" ", 2)
        sub = parts[1]
        if sub in ("*", "$"):
            if "*" in entry and channel.lower() in entry["*"]:
                return self._do_min_check(command, "*", channel)
            return OWNER + 1
        sub_l = sub.lower()
        if sub_l in entry and channel.lower() in entry[sub_l]:
            if entry[sub_l][channel.lower()] != "DELETED":
                return self._do_min_check(command, sub_l, channel)
        if "*" in entry and channel.lower() in entry["*"]:
            return self._do_min_check(command, "*", channel)
        return OWNER + 1

    # -- definition -----------------------------------------------------------
    def create(self, channel: str, command: str, defaultlevel: str) -> None:
        command, channel, defaultlevel = command.lower(), channel.lower(), defaultlevel.upper()
        if defaultlevel not in ACCESS_LEVELS or defaultlevel == "DELETED":
            self.bot.log("ACCESS", "ERROR", f"Illegal default level {defaultlevel} for {command} in {channel}!")
            return
        if channel not in CHANNELS:
            self.bot.log("ACCESS", "ERROR", f"Illegal channel {channel} for {command}!")
            return
        chans = ["tell", "pgmsg", "gc"] if channel == "all" else [channel]
        for chan in chans:
            self.bot.db.query(
                "INSERT IGNORE INTO #___access_control (command, subcommand, channel, minlevel) "
                f"VALUES ('{command}', '*', '{chan}', '{defaultlevel}')"
            )
            self.access_cache.setdefault(command, {}).setdefault("*", {})
            self.access_cache[command]["*"].setdefault(chan, defaultlevel)

    def create_subcommand(self, channel: str, command: str, sub: str, defaultlevel: str) -> None:
        command, sub, channel, defaultlevel = command.lower(), sub.lower(), channel.lower(), defaultlevel.upper()
        if defaultlevel not in ACCESS_LEVELS:
            self.bot.log("ACCESS", "ERROR", f"Illegal default level {defaultlevel} for {command} {sub} in {channel}!")
            return
        if channel not in CHANNELS or sub == "*":
            return
        chans = ["tell", "pgmsg", "gc"] if channel == "all" else [channel]
        for chan in chans:
            self.bot.db.query(
                "INSERT IGNORE INTO #___access_control (command, subcommand, channel, minlevel) "
                f"VALUES ('{command}', '{sub}', '{chan}', '{defaultlevel}')"
            )
            self.access_cache.setdefault(command, {}).setdefault(sub, {})
            self.access_cache[command][sub].setdefault(chan, defaultlevel)

    def update_access(self, command: str, channel: str, newlevel: str) -> None:
        command, channel, newlevel = command.lower(), channel.lower(), newlevel.upper()
        if command == "commands" and newlevel == "DISABLED":
            return
        self.bot.db.query(
            "INSERT INTO #___access_control (command, subcommand, channel, minlevel) "
            f"VALUES ('{command}', '*', '{channel}', '{newlevel}') ON DUPLICATE KEY UPDATE minlevel = '{newlevel}'"
        )
        self.access_cache.setdefault(command, {}).setdefault("*", {})[channel] = newlevel
        self.bot.core("help").update_cache()

    def get_access_levels(self) -> list[str]:
        return ACCESS_LEVELS

    def get_min_access_level(self, command: str, channel: str | None = None) -> int:
        command = command.lower()
        channel = channel.lower() if channel else None
        entry = self.access_cache.get(command)
        if not entry:
            return OWNER + 1
        min_level = OWNER + 1
        for sub, chans in entry.items():
            for chan, level in chans.items():
                if level in SECURITY_LEVELS and (channel is None or channel == chan):
                    min_level = min(min_level, level_value(level))
        return min_level

    def check_for_access(self, name, command: str) -> bool:
        min_level = self.get_min_access_level(command.lower())
        if min_level == OWNER + 1:
            return False
        return self.bot.core("security").check_access(name, min_level)
