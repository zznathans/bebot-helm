"""Ported from Modules/AccessControlUi.php.

GUI/chat-command layer over the already-ported access_control.py
(`core("access_control")`): lets SUPERADMIN+ users view and change the
minimal access level required to run any registered command (or
subcommand) in any channel, and lock/unlock guild-chat / private-group
command access entirely.

Scope cuts:
  * `commands save/load/saves/[saves] del|rem <name>` -- the PHP
    original's named "snapshot" backup/restore feature for the whole
    access_control table (backed by a separate `#___access_control_saves`
    table and Core `save()`/`load()` methods). The already-ported
    access_control.py deliberately only carries the mechanism every
    `register_command()` call relies on (create/create_subcommand/
    check_rights/get_min_rights/update_access/get_access_levels/
    get_min_access_level/check_for_access); it has no `save()`/`load()`
    counterpart to call into, and inventing a brand new table plus Core
    methods is out of scope for this UI-only port. Not ported here for
    the same reason.
  * Everything else (viewing per-channel/per-subcommand access levels,
    updating/adding/deleting a command's or subcommand's minimal access
    level in one channel or "all" channels at once, and the guild-chat/
    private-group hard lock toggle) is ported.

Subcommand-level minimal-access updates have no Core method to call into
either (access_control.py's `update_access()` only ever writes the "*"
top-level entry). For that one case this module writes directly to
`#___access_control`, mirroring the same
`INSERT ... ON DUPLICATE KEY UPDATE` pattern `update_access()` itself
uses, then refreshes the Core module's in-memory cache the same way
`update_access()` does.

Nothing here touches Core/Ao/Whois.php, IRC/relay bridges, or the
dynamic Core/Modules/ plugin loader, so there's no cut to note for those.
"""
from __future__ import annotations

import re

from ..commodities.base import BaseActiveModule
from .security import OWNER

_ACCESS_SHORTS = {
    "AN": "ANONYMOUS",
    "G": "GUEST",
    "M": "MEMBER",
    "L": "LEADER",
    "A": "ADMIN",
    "SA": "SUPERADMIN",
    "O": "OWNER",
    "D": "DISABLED",
}
_SHORTCUTS = {v: k for k, v in _ACCESS_SHORTS.items()}
_CHANNEL_COLORS = {"gc": "##green##", "pgmsg": "##white##", "tell": "##seablue##"}


class AccessControlUi(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("access_control_ui")
        ac = self.bot.core("access_control")
        self.access_levels = ac.get_access_levels()
        # Create default access right for "commands" by SUPERADMIN if it is
        # not set or set to DISABLED. You always want to be able to change
        # the rights!
        if ac.get_min_access_level("commands") == OWNER + 1:
            ac.update_access("commands", "tell", "OWNER")
        self.register_command("all", "channel", "SUPERADMIN")
        self.register_command("all", "commands", "SUPERADMIN")
        self.help["description"] = "Allows you to set access controls for all commands in any channel."
        self.help["command"] = {
            "commands": "Shows the GUI for setting access controls",
            "channel": "Shows the current lock status for commands in guild chat and private chat group.",
            "channel [lock|unlock] [gc|pgmsg]": (
                "Locks or unlocks access to commands in guild chat or private chat group."
            ),
        }

    # -- dispatch ---------------------------------------------------------------
    def command_handler(self, name, msg, origin):
        if re.match(r"^commands$", msg, re.I):
            return self.show_channels()
        m = re.match(r"^commands (gc|pgmsg|tell|all|extpgmsg)$", msg, re.I)
        if m:
            return self.show_levels(m.group(1).lower())
        m = re.match(r"^commands subs ([a-z01-9]+)", msg, re.I)
        if m:
            return self.show_sub_levels(m.group(1))
        m = re.match(r"^commands update (gc|pgmsg|tell|extpgmsg|all) ([a-z01-9]+) ([a-zA-Z]+)$", msg, re.I)
        if m:
            return self.update_level(m.group(1), m.group(2), m.group(3))
        m = re.match(
            r"^commands update (gc|pgmsg|tell|extpgmsg|all) ([a-z01-9]+) ([a-z01-9]+) ([a-zA-Z]+)$", msg, re.I
        )
        if m:
            return self.update_level(m.group(1), m.group(2), m.group(4), m.group(3))
        m = re.match(
            r"^commands add (gc|pgmsg|tell|extpgmsg|all) ([a-z01-9]+) ([a-z01-9]+) ([a-zA-Z]+)$", msg, re.I
        )
        if m:
            return self.update_level(m.group(1), m.group(2), m.group(4), m.group(3))
        m = re.match(
            r"^commands (?:del|rem) (gc|pgmsg|tell|extpgmsg|all) ([a-z01-9]+) ([a-z01-9]+)$", msg, re.I
        )
        if m:
            return self.update_level(m.group(1), m.group(2), "DELETED", m.group(3))
        m = re.match(r"^channel (lock|unlock) (gc|pgmsg)$", msg, re.I)
        if m:
            return self.channel_lock(m.group(2), m.group(1).lower() == "lock")
        if re.match(r"^channel$", msg, re.I):
            return self.show_channel_locks()
        return (
            self.bot.core("tools").chatcmd("http://wiki.bebot.link/index.php/Commands", "Help", "start")
            + " for <pre>commands"
        )

    # -- channel/command listing -------------------------------------------------
    def show_channels(self) -> str:
        tools = self.bot.core("tools")
        blob = "##ao_infotext##The following channels contain commands:##end##\n"
        if self.bot.guildbot and self.bot.commands.get("gc"):
            blob += "\n" + tools.chatcmd("commands gc", "Guild Channel")
        if self.bot.commands.get("pgmsg"):
            blob += "\n" + tools.chatcmd("commands pgmsg", "Private Chatgroup")
        if self.bot.commands.get("tell"):
            blob += "\n" + tools.chatcmd("commands tell", "Tells")
        if self.bot.commands.get("gc") or self.bot.commands.get("pgmsg") or self.bot.commands.get("tell"):
            blob += "\n" + tools.chatcmd("commands all", "All")
        if self.bot.commands.get("extpgmsg"):
            blob += "\n\n" + tools.chatcmd("commands extpgmsg", "External chatgroups")
        return tools.make_blob("Select a channel", blob)

    def _registered_in(self, command: str, channel: str) -> bool:
        if channel == "all":
            return any(command in self.bot.commands.get(chan, {}) for chan in ("gc", "pgmsg", "tell"))
        return command in self.bot.commands.get(channel, {})

    def show_levels(self, channel: str) -> str:
        tools = self.bot.core("tools")
        ac = self.bot.core("access_control")
        titles = {
            "gc": "Guild Chat",
            "pgmsg": "Private Chatgroup",
            "tell": "Tells",
            "extpgmsg": "External Chatgroups",
            "all": "All",
        }
        label = titles.get(channel, "")
        title = f"Current access levels for {label}"
        blob = f" ##yellow## ::: ##end## ##ao_infotext##The current access levels for {label} ##yellow## ::: ##end##"
        blob += "<br>Click on an access level to change it for that command##end##<br><br>"
        blob += "List of shortcuts:"
        for short, long in _ACCESS_SHORTS.items():
            blob += f"<br>{short} = {long}"
        blob += "<br>"
        if channel == "all":
            blob += "<br>Color code for channel information:"
            for chan, color in _CHANNEL_COLORS.items():
                blob += f"<br>{color}{chan}##end##"
            blob += "<br>"
        if channel != "all":
            if not self.bot.commands.get(channel):
                return "No commands defined in this channel!"
        else:
            if not (self.bot.commands.get("gc") or self.bot.commands.get("pgmsg") or self.bot.commands.get("tell")):
                return "No commands defined!"

        rows = []
        for command in sorted(ac.access_cache):
            top = ac.access_cache[command].get("*")
            if not top:
                continue
            if not self._registered_in(command, channel):
                continue
            if channel != "all" and (channel not in top or top[channel] == "DELETED"):
                continue
            rows.append(command)
        if not rows:
            chanmsg = "" if channel == "all" else " for this channel"
            return f"No access levels defined{chanmsg}!"
        for command in rows:
            top = ac.access_cache[command]["*"]
            blob += f"<br>##highlight##<pre>{command}##end##:"
            blob += self._make_access_string(command, top, channel)
            subs = [s for s in ac.access_cache[command] if s != "*"]
            if subs:
                blob += "<br>&#8226; " + tools.chatcmd(f"commands subs {command}", f"Subcommands for {command}")
        return tools.make_blob(title, blob)

    def show_sub_levels(self, command: str) -> str:
        command = command.lower()
        tools = self.bot.core("tools")
        ac = self.bot.core("access_control")
        title = f"Current access levels for {command} Subcommands"
        blob = (
            f" ##yellow## ::: ##end## ##ao_infotext##The current access levels for {command} Subcommands"
            " ##yellow## ::: ##end##"
        )
        blob += "<br>Click on an access level to change it for that command##end##<br><br>"
        blob += "List of shortcuts:"
        for short, long in _ACCESS_SHORTS.items():
            blob += f"<br>{short} = {long}"
        blob += "<br>"
        if not any(command in self.bot.commands.get(chan, {}) for chan in ("gc", "pgmsg", "tell")):
            return f"command ##highlight##{command}##end## Does not Exist!"
        entry = ac.access_cache.get(command, {})
        subs = {s: levels for s, levels in entry.items() if s != "*"}
        if not subs:
            return f"No Subcommand access levels defined for ##highlight##{command}##end##!"
        found = False
        for channel in ("gc", "pgmsg", "tell", "extpgmsg"):
            if command not in self.bot.commands.get(channel, {}):
                continue
            chan_subs = {sub: levels[channel] for sub, levels in subs.items() if channel in levels}
            if not chan_subs:
                continue
            found = True
            blob += f"\n:: {channel} ::\n"
            for sub in sorted(chan_subs):
                blob += f"##highlight##{command} {sub}##end##:" + self._make_access_string(
                    f"{command} {sub}", {channel: chan_subs[sub]}, channel
                )
                blob += " [" + tools.chatcmd(f"commands del {channel} {command} {sub}", "DEL") + "]<br>"
        if not found:
            return f"No Subcommand access levels defined for ##highlight##{command}##end##!"
        return tools.make_blob(title, blob)

    def _make_access_string(self, command: str, current_level: dict, channel: str) -> str:
        tools = self.bot.core("tools")
        result = ""
        level = None
        if channel == "all":
            for chan, color in _CHANNEL_COLORS.items():
                if command in self.bot.commands.get(chan, {}) and chan in current_level:
                    result += f"{color} [{_SHORTCUTS[current_level[chan]]}]##end##"
                else:
                    result += f"{color} [N/A]##end##"
        else:
            level = current_level.get(channel)
        result += " [ "
        parts = []
        for lvl in self.access_levels:
            if lvl == "DELETED":
                continue
            if level == lvl:
                parts.append(_SHORTCUTS[lvl])
            else:
                parts.append(
                    tools.chatcmd(f"commands update {channel} {command} {_SHORTCUTS[lvl]}", _SHORTCUTS[lvl])
                )
        result += " | ".join(parts)
        result += " ]"
        return result

    # -- mutation -----------------------------------------------------------------
    def update_level(self, channel: str, command: str, newlevel: str, subcommand: str | None = None) -> str:
        channel = channel.lower()
        command = command.lower()
        newlevel = newlevel.upper()
        subcommand = subcommand.lower() if subcommand else None
        if len(newlevel) <= 2:
            if newlevel not in _ACCESS_SHORTS:
                return "Invalid access level selected!"
            newlevel = _ACCESS_SHORTS[newlevel]
        if newlevel not in self.access_levels:
            return "Invalid access level selected!"
        if channel in ("tell", "all") and command == "commands" and newlevel == "DISABLED":
            return (
                "You cannot disable the commands management at all! You don't want to lock yourself out "
                "from the bot!"
            )
        ac = self.bot.core("access_control")
        channels = ("gc", "tell", "pgmsg") if channel == "all" else (channel,)
        for chan in channels:
            if subcommand:
                self._set_subcommand_level(command, subcommand, chan, newlevel)
            else:
                ac.update_access(command, chan, newlevel)
        where = "All Channels" if channel == "all" else channel
        target = f"{command} {subcommand}" if subcommand else command
        return (
            f"Minimal access level to use##highlight## {target}##end## in##highlight## {where}##end## "
            f"set to##highlight## {newlevel}##end##"
        )

    def _set_subcommand_level(self, command: str, subcommand: str, channel: str, newlevel: str) -> None:
        ac = self.bot.core("access_control")
        db = self.bot.db
        db.query(
            "INSERT INTO #___access_control (command, subcommand, channel, minlevel) "
            f"VALUES ('{command}', '{subcommand}', '{channel}', '{newlevel}') "
            "ON DUPLICATE KEY UPDATE minlevel = VALUES(minlevel)"
        )
        ac.access_cache.setdefault(command, {}).setdefault(subcommand, {})[channel] = newlevel
        self.bot.core("help").update_cache()

    # -- channel locking ------------------------------------------------------------
    def channel_lock(self, channel: str, lock: bool) -> str:
        channel = channel.lower()
        settings = self.bot.core("settings")
        if channel == "gc":
            settings.save("AccessControl", "LockGc", lock)
            target = "guild chat"
        elif channel == "pgmsg":
            settings.save("AccessControl", "LockPgroup", lock)
            target = "private group"
        else:
            return "##error##Error!##end##"
        state = "##red##locked from use##end##!" if lock else "##green##free to be used##end##!"
        return f"All commands in##highlight## {target}##end## are now {state}"

    def show_channel_locks(self) -> str:
        settings = self.bot.core("settings")
        gc_state = "##red##locked##end##. " if settings.get("AccessControl", "LockGc") else "##green##unlocked##end##. "
        pg_state = "##red##locked##end##." if settings.get("AccessControl", "LockPgroup") else "##green##unlocked##end##."
        return (
            f"Access to commands in##highlight## guild chat##end## is {gc_state}"
            f"Access to commands in##highlight## private group##end## is {pg_state}"
        )
