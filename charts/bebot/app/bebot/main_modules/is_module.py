"""Ported from Modules/Is.php (class `Is`).

Named `is_module.py` (not `is.py`, since `is` is a Python reserved word) and
the class is named `IsModule` for the same reason. It still registers as
`"is"` via `register_module("is")`, matching the PHP module identity and the
`ban`/`autouseradd`-style lowercase registration convention used throughout
this port.

Shows whether a player (and, optionally, their alts) is online, by adding
them to the AO buddy list just long enough to observe a logon/logoff packet
(`buddy()`), polling for stragglers and enforcing a timeout via `cron()`,
and rendering the final result via `send()`. Depends on already-ported
Core modules: `core("tools")` (`sanitize_player()`), `core("player")`
(`id()`), `core("alts")` (`main()`/`get_alts()`), `core("chat")`
(`buddy_exists()`/`buddy_online()`/`buddy_add()`/`buddy_remove()`),
`core("online")` (`get_last_seen()`), and `core("settings")` (the `Is/*`
settings below).

Scope notes / intentional deviations from the PHP:
  * `Commodities/01_BaseActiveModule.php`'s `parse_com()` helper (item-
    reference-aware command splitting) isn't ported into `commodities/base.py`
    at all. Matching the precedent already set in main_modules/
    bot_statistics_ui.py and main_modules/player_notes_ui.py (both of whose
    PHP originals also called `parse_com()`), this just does
    `msg.split(" ", 1)` -- there's no itemref substitution to preserve here,
    `is <name>` never contains an item link in practice.
  * `core("tools")->validate_player()` was never ported into main_modules/
    tools.py (only `sanitize_player()` and friends exist there). This port
    substitutes the same inline "sanitize, then confirm the player actually
    exists via `core("player").id()`" pattern already used by
    main_modules/bans_manager_ui.py's `add_ban()`/`del_ban()` and
    main_modules/admins_ui.py's `all_fixer()`, returning the module's own
    `self.error` (a BotError) on failure -- callers check
    `isinstance(..., BotError)` exactly like the PHP checked
    `$player instanceof BotError`.
  * `last_seen()`'s timestamp was rendered via `gmdate($this->bot
    ->core("settings")->get("Time", "FormatString"), ...)` in the PHP.
    Nothing in this port consumes that setting yet (see main_modules/
    time.py's docstring), so -- matching the precedent already set in
    main_modules/alts.py's `make_info_blob()` and main_modules/afk.py's
    `msgs()` -- this renders a fixed UTC "%Y-%m-%d %H:%M:%S" timestamp
    instead.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from ..commodities.base import BaseActiveModule, BotError

_SPECIAL_ENTRIES = ("trg", "tmo", "chn")


def _norm(name) -> str:
    """PHP's `ucfirst(strtolower($x))` -- Python's str.capitalize() matches exactly."""
    return str(name).capitalize()


def _fmt(ts) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class IsModule(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("is")
        self.register_command("all", "is", "GUEST")
        self.register_event("buddy")
        self.register_event("cron", "3sec")

        settings = self.bot.core("settings")
        settings.create(
            "Is", "Errormsg", True,
            "Display error message on invalid username? (Turning this off is reccomended when "
            "you are not using a command prefix.)",
            "On;Off", False, 5,
        )
        settings.create(
            "Is", "Buddy_slots", 20,
            "How big portion of the buddy list should be reserved for lookups?",
            "5;10;15;20;25;30;50",
        )
        settings.create(
            "Is", "Timeout", 15, "How long should we wait for lookups to complete?",
            "10;15;20;25;30;60",
        )
        settings.create("Is", "CheckAlts", True, "Should Alts be Checked?")

        self.help["description"] = "Shows online status for a player."
        self.help["command"] = {"is <name>": "Shows if player <name> is online or offline"}

        # is_queue[user_looking_up]['trg'/'tmo'/'chn'/<alt>] -- see PHP docstring for the shape.
        self.is_queue: dict[str, dict] = {}
        self.queue_counter = 0

    # -- validation (substitutes core("tools")->validate_player(), see docstring) --
    def _validate_player(self, raw):
        name = self.bot.core("tools").sanitize_player(raw)
        if not name:
            self.error.set(f"##highlight##{raw}##end## is no valid character name!", log=False)
            return self.error
        pid = self.bot.core("player").id(name)
        if isinstance(pid, BotError) or pid == 0:
            self.error.set(f"##highlight##{name}##end## is no valid character name!", log=False)
            return self.error
        return name

    # -- dispatch ------------------------------------------------------------------
    def command_handler(self, name, msg, origin):
        if name in self.is_queue:
            return "Please wait until your previous lookup is completed"

        parts = msg.split(" ", 1)
        raw_player = parts[1] if len(parts) > 1 else ""
        player = self._validate_player(raw_player)
        if isinstance(player, BotError):
            return player

        if player == _norm(self.bot.botname):
            return "I'm online!"

        settings = self.bot.core("settings")
        if settings.get("Is", "CheckAlts"):
            alts_mod = self.bot.core("alts")
            main = alts_mod.main(player)
            alts = list(alts_mod.get_alts(main) or [])
            alts.append(main)
        else:
            alts = [player]

        if name in alts:
            return "Why are you asking me if you are online?!"

        self.is_queue[name] = {
            "chn": origin,
            "trg": player,
            "tmo": time.time() + settings.get("Is", "Timeout"),
        }

        chat = self.bot.core("chat")
        remaining = []
        for alt in alts:
            if chat.buddy_exists(alt):
                self.is_queue[name][alt] = "Online" if chat.buddy_online(alt) else "Offline"
            else:
                remaining.append(alt)

        if not remaining:
            self.send(name)
        else:
            buddy_slots = settings.get("Is", "Buddy_slots")
            for alt in remaining:
                if self.queue_counter < buddy_slots:
                    self.is_queue[name][alt] = "Queued"
                    chat.buddy_add(alt)
                    self.queue_counter += 1
                else:
                    self.is_queue[name][alt] = "Waiting"
        return None

    # -- buddy logon/logoff event --------------------------------------------------
    def buddy(self, name, msg) -> None:
        if msg not in (0, 1):
            return
        if not self.is_queue:
            return
        for source in list(self.is_queue.keys()):
            targets = self.is_queue.get(source)
            if targets is None:
                continue
            for player, status in list(targets.items()):
                if name == player:
                    targets[name] = "Online" if msg == 1 else "Offline"
                    # This toon is removed by the incoming buddy-logon handling already;
                    # no buddy_remove() needed here.
                    self.queue_counter -= 1
            complete = True
            for player, status in targets.items():
                if player not in _SPECIAL_ENTRIES and status not in ("Online", "Offline"):
                    complete = False
            if complete:
                self.send(source)
                self.is_queue.pop(source, None)

    # -- cron: promote waiters / enforce timeouts ----------------------------------
    def cron(self, duration=None) -> None:
        if not self.is_queue:
            return
        settings = self.bot.core("settings")
        chat = self.bot.core("chat")
        now = time.time()
        for source in list(self.is_queue.keys()):
            targets = self.is_queue[source]
            timeout = targets["tmo"]
            if timeout > now:
                buddy_slots = settings.get("Is", "Buddy_slots")
                for player, status in list(targets.items()):
                    if targets[player] == "Waiting" and self.queue_counter < buddy_slots:
                        targets[player] = "Queued"
                        chat.buddy_add(player)
                        self.queue_counter += 1
            else:
                for player, status in list(targets.items()):
                    if status in ("Waiting", "Queued"):
                        targets[player] = "Timeout"
                        if chat.buddy_exists(player):
                            chat.buddy_remove(player)
                            self.queue_counter -= 1
                self.send(source)

    # -- output --------------------------------------------------------------------
    def send(self, name) -> None:
        targets = self.is_queue.get(name)
        if targets is None:
            return
        online_list = [player for player, status in targets.items() if status == "Online"]
        timeout_list = [player for player, status in targets.items() if status == "Timeout"]
        if not online_list:
            reply = f"{targets['trg']} is ##red##Offline##end##"
            reply += self.last_seen(targets["trg"])
        else:
            online = ", ".join(online_list)
            reply = f"{targets['trg']} is ##lime##Online##end## with {online}."
        if timeout_list:
            timeout = ", ".join(timeout_list)
            reply += f"\n ##red##WARNING:##end## The following entries timed out: {timeout}."
        self.bot.send_output(name, reply, targets["chn"])
        self.is_queue.pop(name, None)

    def last_seen(self, name) -> str:
        seen = self.bot.core("online").get_last_seen(name, self.bot.core("settings").get("Is", "CheckAlts"))
        if not seen:
            return ""
        if self.bot.core("settings").get("Is", "CheckAlts"):
            ts, who = seen
            return f", last seen at ##highlight##{_fmt(ts)}##end## on ##highlight##{who}##end##"
        return f", last seen at ##highlight##{_fmt(seen)}##end##"
