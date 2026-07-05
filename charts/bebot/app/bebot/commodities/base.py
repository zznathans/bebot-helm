"""Ported from Commodities/BotError.php, 00_BasePassiveModule.php, 01_BaseActiveModule.php.

SAME/TELL/GC/PG/RELAY/IRC/ALL channel-bitmask constants ported from Sources/Bot.php.
"""
from __future__ import annotations

import sys

SAME = 1
TELL = 2
GC = 4
PG = 8
RELAY = 16
IRC = 32
ALL = 255


class BotError:
    def __init__(self, bot, module: str):
        self.bot = bot
        self.source = module
        self.description = ""
        self.is_fatal = False
        self.is_error = False

    def __str__(self) -> str:
        return self.description

    def reset(self) -> None:
        self.is_fatal = False
        self.description = ""
        self.is_error = False

    def set(self, description: str, log: bool = True, fatal: bool = False) -> None:
        self.description = description
        self.is_error = True
        self.is_fatal = fatal
        if log:
            self.bot.log("ERROR", self.source, description)
        if fatal:
            self.bot.log("FATAL", self.source, description)
            sys.exit(1)

    def get(self) -> str:
        return self.description

    def message(self) -> str:
        return (
            f"##error##Error: ##end##The module ##highlight##{self.source}##end## "
            f"returned the error ##error##{self.description}##end##"
        )


class BasePassiveModule:
    """Base class for modules that don't register chat commands."""

    def __init__(self, bot, module_name: str):
        self.bot = bot
        self.module_name = module_name
        self.link_name: str | None = None
        self.error = BotError(bot, module_name)
        self.source = 0

    def register_module(self, name: str) -> None:
        if self.link_name is None:
            self.link_name = name.lower()
            self.bot.register_module(self, self.link_name)

    def unregister_module(self) -> None:
        if self.link_name is not None:
            self.bot.unregister_module(self.link_name)

    def register_event(self, event: str, target=False) -> None:
        err = self.bot.register_event(event, target, self)
        if err:
            self.error.set(err)

    def unregister_event(self, event: str, target=False) -> None:
        err = self.bot.unregister_event(event, target, self)
        if err:
            self.error.set(err)

    def output_destination(self, name, msg, channel=False) -> None:
        if channel is not False:
            if channel & SAME:
                if channel & self.source:
                    channel -= SAME
                else:
                    channel += self.source
        else:
            channel = (channel or 0) + self.source
        if channel & TELL:
            self.bot.send_tell(name, msg)
        if channel & GC:
            self.bot.send_gc(msg)
        if channel & PG:
            self.bot.send_pgroup(msg)
        if channel & RELAY:
            self.bot.core("relay").relay_to_pgroup(name, msg)
        if channel & IRC:
            self.bot.send_irc(self.module_name, name, msg)

    def debug_output(self, title: str) -> None:
        if self.bot.debug and title:
            print(title)


ACCESS_LEVELS = ["ANONYMOUS", "GUEST", "MEMBER", "LEADER", "ADMIN", "SUPERADMIN", "OWNER"]
CHANNELS = ["gc", "pgmsg", "tell", "extpgmsg", "all"]


class BaseActiveModule(BasePassiveModule):
    """Base class for modules that register chat commands (tell/gc/pgmsg handlers)."""

    def __init__(self, bot, module_name: str):
        super().__init__(bot, module_name)
        self.help: dict = {}

    def command_handler(self, name, msg, origin):
        raise NotImplementedError

    def register_command(self, channel: str, command: str, access: str = "SUPERADMIN", subcommands=None) -> None:
        if channel not in CHANNELS or access not in ACCESS_LEVELS:
            self.error.set(f"Illegal channel or access level when registering command '{command}'")
            return
        if not self.bot.exists_command(channel, command):
            self.bot.register_command(channel, command, self)
            self.bot.core("access_control").create(channel, command, access)
            if subcommands:
                for subcommand, subacl in subcommands.items():
                    self.bot.core("access_control").create_subcommand(channel, command, subcommand, subacl)
        else:
            old_module = self.bot.get_command_handler(channel, command)
            self.error.set(
                f"Duplicate command definition! The command '{command}' for channel '{channel}'"
                f" has already been registered by '{old_module}' and is attempted re-registered by {self.module_name}"
            )

    def unregister_command(self, channel: str, command: str) -> None:
        if channel in CHANNELS and self.bot.exists_command(channel, command):
            self.bot.unregister_command(channel, command)

    def register_alias(self, command: str, alias: str) -> None:
        self.bot.core("command_alias").register(command, alias)

    def unregister_alias(self, alias: str) -> None:
        self.bot.core("command_alias").delete(alias)

    def reply(self, name, msg) -> None:
        if msg is False or msg is None:
            return
        if isinstance(msg, BotError):
            self.reply(name, msg.message())
        else:
            self.output_destination(name, f"##normal##{msg}##end##", SAME)

    def tell(self, name, msg) -> None:
        self.source = TELL
        self.error.reset()
        reply = self.command_handler(name, msg, "tell")
        if reply not in (False, ""):
            self.reply(name, reply)

    def gc(self, name, msg) -> None:
        self.source = GC
        self.error.reset()
        reply = self.command_handler(name, msg, "gc")
        if reply not in (False, ""):
            self.reply(name, reply)

    def pgmsg(self, name, msg) -> None:
        self.source = PG
        self.error.reset()
        reply = self.command_handler(name, msg, "pgmsg")
        if reply not in (False, ""):
            self.reply(name, reply)
