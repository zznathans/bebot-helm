"""Core bot engine, ported from Sources/Bot.php.

Scope cut vs. the PHP original:
  * AoC support, IRC/relay/websocket bridges, and the Symfony-style event
    dispatcher are not ported (see conversation/README for rationale).
  * `load_files()`'s dynamic directory-scan + per-module ini enable/disable
    is replaced by `main_modules.ALL_MODULES`, a fixed list instantiated by
    `run.py` -- there's no Core/ or Modules/ plugin loading yet.
  * cut_size() (blob pagination for oversized tells) is not yet ported;
    send_tell/send_gc/send_pgroup will just send the message unpaginated.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time

from .aochat.protocol import AOChat
from .commodities.base import BasePassiveModule
from .conf import BotConfig
from .mysql import MySQL

CHAT_ALL_CHANNELS = ("gc", "tell", "pgmsg")


class Bot:
    def __init__(self, config: BotConfig):
        self.config = config
        self.botname = config.bot_name.capitalize()
        self.dimension = config.dimension
        self.game = "Ao"
        self.server = config.server
        self.port = config.port
        self.username = config.ao_username
        self.password = config.ao_password
        self.guildbot = config.guildbot
        self.guildid = config.guild_id
        self.guildname = config.guild
        self.owner = config.owner.capitalize() if config.owner else config.owner
        self.super_admin = dict(config.super_admin)
        self.other_bots = dict(config.other_bots)
        self.commpre = config.command_prefix
        self.crondelay = config.cron_delay
        self.telldelay = config.tell_delay
        self.maxsize = config.max_blobsize
        self.reconnecttime = config.reconnect_time
        self.accessallbots = config.accessallbots
        self.log_mode = config.log
        self.log_path = os.path.join(
            config.log_path, f"{self.botname.lower()}@RK{config.dimension}"
        )
        self.log_timestamp = config.log_timestamp
        self.log_format = config.log_format
        os.makedirs(self.log_path, exist_ok=True)

        self.debug = False
        self.starttime = time.time()
        self.connected_time: float | None = None
        self.banmsgout: dict[str, float] = {}
        self.command_error_text: str | None = None

        self.commands: dict[str, dict] = {}
        self._module_links: dict[str, BasePassiveModule] = {}
        self._cron_times: dict[int, int] = {}
        self._cron_jobs: dict[int, dict[str, object]] = {}
        self._cron_job_timer: dict[int, float] = {}
        self._cron_job_active: dict[int, bool] = {}
        self._settings_callbacks: dict[tuple[str, str], dict[str, object]] = {}
        self._startup_time = 0.0
        self.cron_activated = False

        self.aoc = AOChat(self)
        self.db = MySQL(
            self,
            dbase=config.db_name,
            user=config.db_user,
            password=config.db_password,
            server=config.db_server,
            table_prefix=config.table_prefix,
            master_tablename=config.master_tablename,
            no_underscore=config.no_underscore,
        )

    # -- module / command registry -------------------------------------------
    def register_module(self, module, name: str) -> None:
        name = name.lower()
        if name in self._module_links:
            self.log(
                "CORE", "ERROR",
                f"Module '{name}' has already been registered by "
                f"{type(self._module_links[name]).__name__} so cannot be registered by {type(module).__name__}.",
            )
            return
        self._module_links[name] = module

    def unregister_module(self, name: str) -> None:
        self._module_links.pop(name.lower(), None)

    def exists_module(self, name: str) -> bool:
        return name.lower() in self._module_links

    def core(self, name: str):
        module = self._module_links.get(name.lower())
        if module is not None:
            return module
        dummy = _DummyModule(self, name)
        self.log("CORE", "ERROR", f"Module '{name}' does not exist or is not loaded.")
        return dummy

    def register_command(self, channel: str, command: str, module) -> None:
        channel = channel.lower()
        command = command.lower()
        if channel == "all":
            for ch in CHAT_ALL_CHANNELS:
                self.commands.setdefault(ch, {})[command] = module
        else:
            self.commands.setdefault(channel, {})[command] = module

    def unregister_command(self, channel: str, command: str) -> None:
        channel = channel.lower()
        command = command.lower()
        channels = CHAT_ALL_CHANNELS if channel == "all" else (channel,)
        for ch in channels:
            self.commands.get(ch, {}).pop(command, None)

    def exists_command(self, channel: str, command: str) -> bool:
        channel = channel.lower()
        command = command.lower()
        if channel == "all":
            return all(command in self.commands.get(ch, {}) for ch in CHAT_ALL_CHANNELS)
        return command in self.commands.get(channel, {})

    def get_command_handler(self, channel: str, command: str) -> str:
        channel = channel.lower()
        command = command.lower()
        module = self.commands.get(channel, {}).get(command)
        return type(module).__name__ if module else ""

    def register_event(self, event: str, target, module) -> str | bool:
        event = event.lower()
        valid = {
            "connect", "disconnect", "pgjoin", "pginvite", "pgleave", "extpgjoin",
            "extpgleave", "cron", "settings", "timer", "logon_notify", "buddy",
            "privgroup", "gmsg", "tells", "extprivgroup", "irc",
        }
        if event not in valid:
            return f"Event '{event}' is invalid. Not registering."
        if event == "gmsg":
            if not target:
                return "No channel specified for gmsg. Not registering."
            self.commands.setdefault("gmsg", {}).setdefault(target, {})[type(module).__name__] = module
            return False
        if event == "cron":
            try:
                interval = int(target)
            except (TypeError, ValueError):
                interval = _parse_cron_interval(target)
            if not interval or interval <= 0:
                return f"Cron time '{target}' is invalid. Not registering."
            self._cron_job_active.setdefault(interval, False)
            self._cron_job_timer.setdefault(interval, max(time.time(), self._startup_time))
            self._cron_times[interval] = interval
            self._cron_jobs.setdefault(interval, {})[type(module).__name__] = module
            return False
        if event == "timer":
            if not target:
                return "No name for the timer callback given! Not registering."
            self.core("timer").register_callback(target, module)
            return False
        if event == "logon_notify":
            self.core("logon_notifies").register(module)
            return False
        if event == "settings":
            if isinstance(target, dict) and "module" in target and "setting" in target:
                return self.core("settings").register_callback(target["module"], target["setting"], module)
            return "No module and/or setting defined, can't register!"
        if event == "irc":
            return False  # IRC bridge not ported
        self.commands.setdefault(event, {})[type(module).__name__] = module
        return False

    def unregister_event(self, event: str, target, module) -> str | bool:
        event = event.lower()
        if event == "gmsg":
            bucket = self.commands.get("gmsg", {}).get(target, {})
            bucket.pop(type(module).__name__, None)
            return False
        if event == "cron":
            interval = int(target) if str(target).isdigit() else _parse_cron_interval(target)
            self._cron_jobs.get(interval, {}).pop(type(module).__name__, None)
            return False
        if event == "timer":
            return self.core("timer").unregister_callback(target)
        if event == "logon_notify":
            self.core("logon_notifies").unregister(module)
            return False
        if event == "settings":
            if isinstance(target, dict) and "module" in target and "setting" in target:
                return self.core("settings").unregister_callback(target["module"], target["setting"], module)
            return "No module and/or setting defined, can't unregister!"
        self.commands.setdefault(event, {}).pop(type(module).__name__, None)
        return False

    # -- connection lifecycle -----------------------------------------------
    async def connect(self) -> None:
        self.cron_activated = False
        self.log("LOGIN", "STATUS", f"Connecting to {self.game} server {self.server}:{self.port}")
        if not await self.aoc.connect(self.server, self.port):
            self.cron_activated = False
            self.disconnect()
            self.log("CONN", "ERROR", f"Can't connect to server. Retrying in {self.reconnecttime} seconds.")
            await asyncio.sleep(self.reconnecttime)
            raise SystemExit("The bot is restarting.")

        self.log("LOGIN", "STATUS", f"Authenticating {self.username}")
        await self.aoc.authenticate(self.username, self.password)
        self.log("LOGIN", "STATUS", f"Logging in {self.botname}")
        await self.aoc.login(self.botname)

        self.username = None
        self.password = None

        self._create_core_settings()

        for module in list(self.commands.get("connect", {}).values()):
            if module is not None:
                module.connect()

        self._startup_time = time.time() + self.crondelay
        for interval in self._cron_times:
            self._cron_job_timer[interval] = self._startup_time
        self.cron_activated = True
        self.connected_time = time.time()

    def _create_core_settings(self) -> None:
        settings = self.core("settings")
        defaults = [
            ("Core", "RequireCommandPrefixInTells", False,
             "Is the command prefix (in this bot <pre>) required for commands in tells?"),
            ("Core", "LogGCOutput", True, "Log the bot's own guild-chat output?"),
            ("Core", "LogPGOutput", True, "Log the bot's own private-group output?"),
            ("Core", "SimilarCheck", False, "Try to match a similar command if no exact match is found?"),
            ("Core", "SimilarMinimum", 75, "Minimum similarity percentage to consider two commands similar?"),
            ("Core", "CommandErrorTell", False, "Send an access-denied error for tells?"),
            ("Core", "CommandErrorPgMsg", False, "Send an access-denied error for private-group messages?"),
            ("Core", "CommandErrorGc", False, "Send an access-denied error for guild-chat messages?"),
            ("Core", "CommandErrorExtPgMsg", False, "Send an access-denied error for external private groups?"),
            ("Core", "CommandDisabledError", False, "Send a disabled-command error?"),
            ("Core", "DisableGC", False, "Disable command handling in guild chat?"),
            ("Core", "DisablePGMSG", False, "Disable command handling in the bot's private group?"),
            ("Core", "ColorizeTells", True, "Colorize outgoing tells?"),
            ("Core", "ColorizeGC", True, "Colorize outgoing guild-chat messages?"),
            ("Core", "ColorizePGMSG", True, "Colorize outgoing private-group messages?"),
            ("Core", "BanReason", True, "Tell banned users why they're banned?"),
            ("Core", "DisableGCchat", False, "Ignore non-command chat in guild chat?"),
            ("Core", "DisablePGMSGchat", False, "Ignore non-command chat in the private group?"),
        ]
        for module, setting, value, desc in defaults:
            settings.create(module, setting, value, desc)

    def disconnect(self) -> None:
        self.aoc.disconnect()
        for module in list(self.commands.get("disconnect", {}).values()):
            if module is not None:
                module.disconnect()

    async def reconnect(self) -> None:
        self.cron_activated = False
        self.disconnect()
        self.log("CONN", "ERROR", f"Bot has disconnected. Reconnecting in {self.reconnecttime} seconds.")
        await asyncio.sleep(self.reconnecttime)
        raise SystemExit("The bot is restarting.")

    # -- outgoing messages ----------------------------------------------------
    def replace_string_tags(self, msg: str) -> str:
        msg = msg.replace("<botname>", self.botname)
        msg = msg.replace("<guildname>", self.guildname or "")
        msg = msg.replace("<pre>", self.commpre)
        return msg

    def send_help(self, to, command=False) -> None:
        if command is False:
            self.send_tell(to, "/tell <botname> <pre>help")
        else:
            self.send_tell(to, self.core("help").show_help(to, command))

    def send_ban(self, to, msg=False) -> bool | None:
        now = time.time()
        if to in self.banmsgout and self.banmsgout[to] >= now - 300:
            return False
        self.banmsgout[to] = now
        if msg is False:
            msg = "You are banned from <botname>."
        self.send_tell(to, msg)

    def send_permission_denied(self, to, command, kind=0):
        message = f"You do not have permission to access {command}"
        if not kind:
            return message
        self.send_output(to, message, kind)

    def send_tell(self, to, msg: str, low=0, color=True, sizecheck=True, parsecolors=True) -> None:
        if parsecolors:
            msg = self.core("colors").parse(msg)
        msg = self.replace_string_tags(msg)
        if color and self.core("settings").get("Core", "ColorizeTells"):
            msg = self.core("colors").colorize("normal", msg)
        if self.core("chat_queue").check_queue():
            to_name = self.core("player").name(to) if isinstance(to, int) else to
            self.log("TELL", "OUT", f"-> {to_name}: {msg}")
            asyncio.ensure_future(self.aoc.send_tell(to, msg))
        else:
            self.core("chat_queue").into_queue(to, msg, "tell", low)

    def send_pgroup(self, msg: str, group=None, checksize=True, parsecolors=True) -> bool | None:
        if group is None:
            group = self.botname
        if group == self.botname and self.core("settings").get("Core", "DisablePGMSG"):
            return False
        if parsecolors:
            msg = self.core("colors").parse(msg)
        gid = self.core("player").id(group)
        msg = self.replace_string_tags(msg)
        if str(group).lower() == self.botname.lower() and self.core("settings").get("Core", "ColorizePGMSG"):
            msg = self.core("colors").colorize("normal", msg)
        asyncio.ensure_future(self.aoc.send_privgroup(gid, msg))

    def send_gc(self, msg: str, low=0, checksize=True) -> bool | None:
        if self.core("settings").get("Core", "DisableGC"):
            return False
        msg = self.core("colors").parse(msg)
        msg = self.replace_string_tags(msg)
        if self.core("settings").get("Core", "ColorizeGC"):
            msg = self.core("colors").colorize("normal", msg)
        if self.core("chat_queue").check_queue():
            asyncio.ensure_future(self.aoc.send_group(self.guildname, msg))
        else:
            self.core("chat_queue").into_queue(self.guildname, msg, "gc", low)

    def send_output(self, source, msg, kind, low=0) -> None:
        msg = self.core("colors").parse(msg)
        kind = str(kind).lower() if not isinstance(kind, int) else kind
        if kind in ("0", "1", "tell", 0, 1):
            self.send_tell(source, msg, low)
        elif kind in ("2", "pgroup", "pgmsg"):
            self.send_pgroup(msg)
        elif kind in ("3", "gc"):
            self.send_gc(msg, low)
        elif kind in ("4", "both"):
            self.send_gc(msg, low)
            self.send_pgroup(msg)
        else:
            self.log("OUTPUT", "ERROR", f"Broken plugin, type: {kind} is unknown; source: {source}, message: {msg}")

    def send_irc(self, prefix, name, msg) -> None:
        pass  # IRC bridge not ported

    # -- command dispatch -------------------------------------------------------
    def find_similar_command(self, channel: str, cmd: str):
        import difflib
        commands = self.commands.get(channel, {})
        if cmd in commands:
            return [0]
        threshold = self.core("settings").get("Core", "SimilarMinimum")
        best = (0, None)
        for candidate in commands:
            ratio = difflib.SequenceMatcher(None, cmd, candidate).ratio() * 100
            if ratio >= threshold and ratio > best[0]:
                best = (ratio, candidate)
        return [best[0], best[1]] if best[1] else [0]

    def check_access_and_execute(self, user, command, msg, channel, pgname) -> bool:
        module = self.commands.get(channel, {}).get(command)
        if module is None:
            return False
        if self.core("access_control").check_rights(user, command, msg, channel):
            if channel == "extpgmsg":
                getattr(module, channel)(pgname, user, msg)
            else:
                getattr(module, channel)(user, msg)
            return True
        return False

    def handle_command_input(self, user, msg: str, channel: str, pgname=None) -> bool:
        self.command_error_text = None
        if not self.commands.get(channel):
            return False
        if self.core("security").is_banned(user):
            self.send_ban(user)
            return True
        stripped_prefix = self.commpre.replace("\\", "")
        if channel == "tell" and not self.core("settings").get("Core", "RequireCommandPrefixInTells") \
                and self.commpre != "" and (not msg or msg[0] != stripped_prefix):
            msg = stripped_prefix + msg
        match = False
        if self.commpre == "" or (msg and msg[0] == stripped_prefix):
            if self.commpre != "":
                msg = msg[1:]
            msg = self.core("command_alias").replace(msg)
            parts = msg.split(" ", 2)
            parts[0] = parts[0].lower()
            msg = " ".join(parts)
            cmd0 = parts[0]
            if cmd0 in self.commands.get(channel, {}):
                match = True
                if self.check_access_and_execute(user, cmd0, msg, channel, pgname):
                    return True
            elif self.core("settings").get("Core", "SimilarCheck"):
                use = self.find_similar_command(channel, cmd0)
                if use[0] > 0:
                    cmd0 = use[1]
                    rest = msg.split(" ", 1)
                    rest[0] = cmd0
                    msg = " ".join(rest)
                    if cmd0 in self.commands.get(channel, {}):
                        match = True
                        if self.check_access_and_execute(user, cmd0, msg, channel, pgname):
                            return True
            if match and self.core("settings").get("Core", f"CommandError{channel}"):
                minlevel = self.core("access_control").get_min_rights(cmd0, msg, channel)
                self.command_error_text = (
                    f"You're not authorized to use this Command: ##highlight##{msg}##end##, "
                    f"Your Access Level is required to be at least ##highlight##{minlevel}##end##"
                )
        return False

    def hand_to_chat(self, found, user, msg, channel, group=None):
        if found:
            return True
        if channel == "gmsg":
            if group == self.guildname:
                group = "org"
            registered = self.commands.get(channel, {}).get(group, {})
        else:
            registered = self.commands.get(channel, {})
        for module in list(registered.values()):
            if module is None:
                continue
            if channel == "extprivgroup":
                found = found or module.extprivgroup(group, user, msg)
            elif channel == "gmsg":
                found = found or module.gmsg(user, group, msg)
            else:
                found = found or getattr(module, channel)(user, msg)
        return found

    # -- incoming events ---------------------------------------------------------
    def inc_tell(self, args) -> None:
        user = self.core("player").name(args[0])
        if user == self.botname:
            return
        if user in self.other_bots:
            return
        self.log("TELL", "INC", f"{user}: {args[1]}")
        found = self.handle_command_input(user, args[1], "tell")
        found = self.hand_to_chat(found, user, args[1], "tells")
        if self.command_error_text:
            self.send_tell(args[0], self.command_error_text)
        elif not found and self.core("security").check_access(user, "GUEST"):
            self.send_help(args[0])
        elif not found:
            self.send_tell(args[0], f"I only listen to members of {'the guild' if self.guildbot else 'this bot'}.")
        self.command_error_text = None

    def inc_pgjoin(self, args) -> None:
        pgname = self.core("player").name(args[0]) if isinstance(args[0], int) else args[0]
        pgname = pgname or self.botname
        user = self.core("player").name(args[1]) if isinstance(args[1], int) else args[1]
        if str(pgname).lower() == self.botname.lower():
            self.log("PGRP", "JOIN", f"{user} joined privategroup.")
            for module in list(self.commands.get("pgjoin", {}).values()):
                if module is not None:
                    module.pgjoin(user)
        else:
            self.log("PGRP", "JOIN", f"{user} joined the exterior privategroup of {pgname}.")
            for module in list(self.commands.get("extpgjoin", {}).values()):
                if module is not None:
                    module.extpgjoin(pgname, user)

    def inc_pgleave(self, args) -> None:
        pgname = self.core("player").name(args[0]) or self.botname
        user = self.core("player").name(args[1])
        if str(pgname).lower() == self.botname.lower():
            self.log("PGRP", "LEAVE", f"{user} left privategroup.")
            for module in list(self.commands.get("pgleave", {}).values()):
                if module is not None:
                    module.pgleave(user)
        else:
            self.log("PGRP", "LEAVE", f"{user} left the exterior privategroup {pgname}.")
            for module in list(self.commands.get("extpgleave", {}).values()):
                if module is not None:
                    module.extpgleave(pgname, user)

    def inc_pgmsg(self, args) -> None:
        pgname = self.core("player").name(args[0]) or self.botname
        user = self.core("player").name(args[1])
        found = False
        dispgmsg = self.core("settings").get("Core", "DisablePGMSG")
        dispgmsgchat = self.core("settings").get("Core", "DisablePGMSGchat")
        if pgname == self.botname and dispgmsg and dispgmsgchat:
            return
        if str(self.botname).lower() == str(user).lower():
            if self.core("settings").get("Core", "LogPGOutput"):
                self.log("PGRP", "MSG", f"[{pgname}] {user}: {args[2]}")
            return
        self.log("PGRP", "MSG", f"[{pgname}] {user}: {args[2]}")
        if user in self.other_bots:
            return
        if str(pgname).lower() == self.botname.lower():
            if not dispgmsg:
                found = self.handle_command_input(user, args[2], "pgmsg")
            if not dispgmsgchat:
                found = self.hand_to_chat(found, user, args[2], "privgroup")
        else:
            found = self.handle_command_input(user, args[2], "extpgmsg", pgname)
            found = self.hand_to_chat(found, user, args[2], "extprivgroup", pgname)
        if self.command_error_text:
            self.send_pgroup(self.command_error_text, pgname)
        self.command_error_text = None

    def inc_gannounce(self, args) -> None:
        if args[2] == 32772:
            self.guildname = args[1]
            self.log("CORE", "INC_GANNOUNCE", f"Detected org name as: {args[1]}")

    def inc_pginvite(self, args) -> None:
        group = self.core("player").name(args[0])
        for module in list(self.commands.get("pginvite", {}).values()):
            if module is not None:
                module.pginvite(group)

    def inc_gmsg(self, args) -> None:
        found = False
        group = self.core("chat").lookup_group(args[0]) or self.core("chat").get_gname(args[0])
        if group in self.commands.get("gmsg", {}) or group == self.guildname:
            msg = f"[{group}] "
            if args[1] != 0:
                msg += f"{self.core('player').name(args[1])}: "
            msg += args[2]
        else:
            return
        disgc = self.core("settings").get("Core", "DisableGC")
        disgcchat = self.core("settings").get("Core", "DisableGCchat")
        if group == self.guildname and disgc and disgcchat:
            return
        user = "0" if args[1] == 0 else self.core("player").name(args[1])
        if str(self.botname).lower() == str(user).lower():
            if self.core("settings").get("Core", "LogGCOutput"):
                self.log("GROUP", "MSG", msg)
            return
        self.log("GROUP", "MSG", msg)
        if user in self.other_bots:
            return
        if group == self.guildname:
            if not disgc:
                found = self.handle_command_input(user, args[2], "gc")
            if self.command_error_text:
                self.send_gc(self.command_error_text)
            self.command_error_text = None
        if not disgcchat:
            found = self.hand_to_chat(found, user, args[2], "gmsg", group)

    # -- cron -----------------------------------------------------------------
    def cronjob(self, now: float, duration: int) -> None:
        if self._cron_job_timer.get(duration, 0) <= now and not self._cron_job_active.get(duration):
            jobs = self._cron_jobs.get(duration, {})
            if jobs:
                self._cron_job_active[duration] = True
                for module in list(jobs.values()):
                    if module is not None:
                        module.cron(duration)
                self._cron_job_active[duration] = False
            self._cron_job_timer[duration] = time.time() + duration

    def cron(self) -> None:
        if not self.cron_activated:
            return
        now = time.time()
        self.core("timer").check_timers()
        for interval in list(self._cron_times.values()):
            self.cronjob(now, interval)

    # -- logging --------------------------------------------------------------
    def log(self, first: str, second: str, msg, write_to_db: bool = False) -> None:
        msg = str(msg)
        msg = re.sub(r"<font[^>]*>", "", msg)
        msg = msg.replace("</font>", "")
        msg = msg.replace("##end##", "]")
        msg = re.sub(r"##(.+?)##", "[", msg)
        msg = re.sub(r'<a href="[^"]*">', "[link]", msg)
        msg = msg.replace("</a>", "[/link]")
        msg = self.replace_string_tags(msg)

        if self.log_format == "json":
            line = json.dumps({
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "bot": self.botname,
                "first": first,
                "second": second,
                "message": msg,
            }) + "\n"
            print(line, end="")
        else:
            if self.log_timestamp == "date":
                timestamp = f"[{time.strftime('%Y-%m-%d', time.gmtime())}]\t"
            elif self.log_timestamp == "time":
                timestamp = f"[{time.strftime('%H:%M:%S', time.gmtime())}]\t"
            elif self.log_timestamp == "none":
                timestamp = ""
            else:
                timestamp = f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}]\t"

            line = f"{timestamp}[{first}]\t[{second}]\t{msg}\n"
            print(f"{self.botname} {line}", end="")

        if second.lower() == "security":
            if self.guildbot:
                self.send_gc(line)
            else:
                self.send_pgroup(line)
            with open(os.path.join(self.log_path, "security.txt"), "a") as fh:
                fh.write(line)

        if self.log_mode == "all" or (self.log_mode == "chat" and first in ("GROUP", "TELL", "PGRP")):
            path = os.path.join(self.log_path, f"{time.strftime('%Y-%m-%d', time.gmtime())}.txt")
            with open(path, "a") as fh:
                fh.write(line)

        if write_to_db:
            logmsg = msg[:500]
            self.db.query(
                "INSERT INTO #___log_message (message, first, second, timestamp) VALUES "
                f"('{self.db.real_escape_string(logmsg)}','{first}','{second}','{int(time.time())}')"
            )

    def debug_bt(self) -> str:
        return ""


def _parse_cron_interval(target) -> int:
    """Very small subset of PHP's strtotime($target, 0) for cron intervals
    like '1sec' / '1hour' / '12hour' used by register_event('cron', ...)."""
    match = re.match(r"(\d+)\s*(sec|second|min|minute|hour|day)s?$", str(target).strip(), re.I)
    if not match:
        return 0
    amount, unit = int(match.group(1)), match.group(2).lower()
    multiplier = {"sec": 1, "second": 1, "min": 60, "minute": 60, "hour": 3600, "day": 86400}[unit]
    return amount * multiplier


class _DummyModule:
    """Stand-in for BasePassiveModule's __call-catches-everything fallback."""

    def __init__(self, bot, name: str):
        self._bot = bot
        self._name = name

    def __getattr__(self, item):
        def _missing(*args, **kwargs):
            self._bot.log("CORE", "ERROR", f"Undefined function {item}() on missing module '{self._name}'")
            return f"##error##Error: ##end##Module ##highlight##{self._name}##end## is not loaded."
        return _missing

    def __bool__(self):
        return False
