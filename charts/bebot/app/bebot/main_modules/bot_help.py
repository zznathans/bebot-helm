"""Ported from Main/15_BotHelp.php."""
from __future__ import annotations

from ..commodities.base import BaseActiveModule
from .security import ANONYMOUS, GUEST, MEMBER, LEADER, ADMIN, SUPERADMIN, OWNER

_LEVEL_ORDER = [ANONYMOUS, GUEST, MEMBER, LEADER, ADMIN, SUPERADMIN, OWNER]
_LEVEL_NAMES = ["ANONYMOUS", "GUEST", "MEMBER", "LEADER", "ADMIN", "SUPERADMIN", "OWNER"]


class BotHelp(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("help")
        self.register_command("all", "help", "GUEST")
        self.help["description"] = "The bot help system."
        self.help_cache: dict[str, dict[str, str]] = {}

    def command_handler(self, name, msg, origin):
        if not self.help_cache:
            self.update_cache()
        parts = msg.split(" ")
        if len(parts) < 2 or not parts[1]:
            return self.show_help_menu(name, "source", origin)
        if parts[1] in ("tell", "gc", "pgmsg"):
            return self.show_help_menu(name, parts[1])
        return self.show_help(name, parts[1])

    def show_help_menu(self, name, section="source", origin=False):
        channel = origin if section == "source" else section
        window = self.get_commands(name, channel)
        return self.bot.core("tools").make_blob("Help", window)

    def get_commands(self, name, channel: str) -> str:
        channel = channel.lower()
        level = self.bot.core("security").get_access_name(self.bot.core("security").get_access_level(name))
        return ":: BeBot Help ::\n\n" + self.help_cache.get(channel, {}).get(level, "")

    def update_cache(self) -> None:
        for channel in ("tell", "pgmsg", "gc"):
            self.make_help_blobs(channel)

    def make_help_blobs(self, channel: str) -> None:
        channel = channel.lower()
        cache = {lvl: "" for lvl in _LEVEL_NAMES}
        commands = self.bot.commands.get(channel, {})
        for command in sorted(commands):
            module = commands[command]
            if getattr(module, "help", None):
                cmdstr = self.bot.core("tools").chatcmd(f"help {command}", command) + " "
            else:
                cmdstr = command + " "
            min_level = self.bot.core("access_control").get_min_access_level(command, channel)
            for level_value, level_name in zip(_LEVEL_ORDER, _LEVEL_NAMES):
                if level_value >= min_level:
                    cache[level_name] += cmdstr
        self.help_cache[channel] = cache

    def show_help(self, name, command: str) -> str:
        if not self.bot.core("access_control").check_for_access(name, command):
            return f"##highlight##{command}##end## does not exist or you do not have access to it."
        module = None
        for channel in ("tell", "gc", "pgmsg"):
            module = self.bot.commands.get(channel, {}).get(command)
            if module:
                break
        if not module:
            return f"##highlight##{command}##end## does not exist or you do not have access to it."
        window = f"##blob_title## ::::: HELP ON {command.upper()} :::::##end##<br><br>"
        help_data = getattr(module, "help", None) or {}
        if help_data.get("description"):
            window += f"{help_data['description']}<br><br>"
        for cmd, desc in help_data.get("command", {}).items():
            window += f"##highlight##{cmd}##end##: {desc}<br>"
        if help_data.get("notes"):
            window += f"<br>{help_data['notes']}"
        return self.bot.core("tools").make_blob(command, window)
