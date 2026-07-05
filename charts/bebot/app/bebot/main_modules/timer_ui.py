"""Ported from Modules/TimerUi.php (class `TimerGUI`).

Chat-command UI for creating, listing and removing timers, on top of the
already-ported (but heavily reduced) `core("timer")`
(`bebot/main_modules/timer_core.py`), plus `core("time")` (duration
parsing/formatting), `core("alts")` (main/alt resolution for delete
permission) and `core("security")` (admin-delete permission).

`timer_core.py`'s own docstring explains it only keeps the *contract*
`Bot.cron()` depends on: an in-memory `add_timer(owner, seconds, data) ->
id` / `del_timer(id)` scheduler that calls back into a module registered
via `register_event("timer", name)` when a timer fires. It does not carry
over the PHP's `#___timer` DB table, per-timer name/owner/channel/repeat
columns, the multi-stage "timer class" notification-chain system
(`#___timer_classes`/`#___timer_class_entries`/`#___timer_class_settings`,
`create_class_setting()`/`get_class_setting()`/`update_class_setting()`),
channel-broadcast widening (`Timer/GuestChannel`, `Timer/Global`), or
cross-bot relay of new timers (`Timer/Relay` + `core("relay")`). None of
that exists to port against, so this module is a from-scratch chat-command
layer built directly on the minimal scheduler:

  * This module registers itself as a `"timer_ui"` timer callback
    (`register_event("timer", "timer_ui")` -> `timer_core.register_callback`)
    and is the sole creator of every timer it schedules, so it keeps its own
    `self._timers` dict (id -> {owner, name, channel, repeat, endtime}) as
    the source of truth for `show_timer()`'s listing and `remtimer`'s
    permission checks -- the equivalent of the PHP's `#___timer` table rows,
    just in-memory (matching timer_core.py's "not persisted across
    restarts" trade-off).
  * `timer_core.del_timer(id)` unconditionally deletes with no permission
    checks at all (unlike the PHP core's `del_timer($deleter, $id,
    $silent)`, which only lets the owner, one of the owner's alts, or
    someone with `Timer/DeleteRank` access delete someone else's timer,
    optionally notifying the owner). That permission logic + the
    owner-notify-on-admin-delete behavior is reimplemented here directly
    against `self._timers`, since there's nowhere else for it to live.
  * `Timer/DeleteRank` and `Timer/MinRepeatInterval` normally get created by
    Core/15_TimerCore.php's constructor (not ported); this module creates
    both itself since it's now their only consumer. `Timer/GuestChannel`,
    `Timer/Global`, `Timer/Relay`, `Timer/DefaultClass` and
    `Timer/RecoveryCheckInterval` are NOT created -- nothing here reads
    them, since the behavior they gated (channel widening, relay
    replication, timer classes, DB-failure recovery) isn't ported.
  * The `[class]` argument PHP's `timer`/`rtimer` commands accept
    (`get_class_setting("PublicTimer"/"PrivateTimer")`, `tset` for viewing
    the settings) is dropped entirely along with the class system --
    there's no notion of a timer "class" to select between anymore. The
    `timer`/`rtimer` regexes are simplified accordingly (no optional
    leading class-name token), and the `tset`/`timersettings`/`tsettings`
    command and `show_timer_settings()`/`change_timer_setting()`/
    `update_timer_setting()` are not ported at all.
  * A fired timer sends a single flat "##highlight##<name>##end##[,
    ##highlight##<owner>##end##]!" message to its channel -- the PHP's
    class-based multi-stage warnings ("has 10 seconds left" / "has one
    minute left" / ...) before the final expiry message don't exist without
    a class system to drive them.
  * The `global`/`both` channel-widening PHP does for `Timer/GuestChannel`
    == "both" (org/pgroup timers becoming visible in both channels) and
    `Timer/Global` (every timer visible everywhere) is dropped: a timer here
    is only ever visible/fires in the exact channel it was created in
    (`show_timer()` filters by exact channel match, or by owner for
    `channel == "tell"`, same as the PHP's un-widened base case).
"""
from __future__ import annotations

import re
import time

from ..commodities.base import BaseActiveModule


class TimerUi(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("timer_ui")

        self.register_command("all", "timer", "GUEST")
        self.register_command("all", "rtimer", "GUEST")
        self.register_alias("timer", "timers")
        self.register_command("all", "remtimer", "GUEST")
        self.register_command("all", "ptimer", "GUEST")
        self.register_alias("ptimer", "publictimer")
        self.register_alias("ptimer", "ptimers")
        self.register_alias("ptimer", "publictimers")

        self.register_event("timer", "timer_ui")

        self.bot.core("settings").create(
            "Timer", "DeleteRank", "ADMIN",
            "Minimal access level to remove timer of other players.",
            "ANONYMOUS;GUEST;MEMBER;LEADER;ADMIN;SUPERADMIN;OWNER",
        )
        self.bot.core("settings").create(
            "Timer", "MinRepeatInterval", 30,
            "What's the minimal repeat interval for repeating timers (in seconds)? "
            "This is used to prevent annoying spam.",
            "5;10;15;20;25;30;45;60",
        )

        # timer_id -> {"owner", "name", "channel", "repeat", "endtime"}
        self._timers: dict[int, dict] = {}

        self.help["description"] = "Setting and removing of timers.."
        self.help["command"] = {
            "timer": "Lists all current timer for the bot and offers support to delete them.",
            "timer #[mshd] title": (
                "Adds a timer for # minutes (m), seconds (s), hours (h) or days (d). "
                "If no time unit is added it's # seconds."
            ),
            "timer 0:0:0:0 title": (
                "Adds a timer using the format days:hours:minutes:seconds, with the lowest time unit "
                "always being seconds (so 1:20 means 1min 20secs, 1:03:05 means 1hour 3mins 5secs). "
                "On every : there have to follow exactly two numbers. You don't have to enter all numbers."
            ),
            "rtimer <dur>[mshd] <repeat>[mshd] title": (
                "Adds a repeating timer for <dur> minutes (m), seconds (s), hours (h) or days (d). "
                "If no time unit is added it's <dur> seconds. <repeat> is the time between repetitions "
                "of the timer, the same rules as for <dur> apply."
            ),
            "rtimer <dur>0:0:0:0 <repeat>0:0:0:0 title": (
                "Adds a timer using the format days:hours:minutes:seconds, with the lowest time unit "
                "always being seconds. <repeat> is the time between repetitions of the timer, the same "
                "rules as for <dur> apply."
            ),
            "ptimer": (
                "Lists and creates timers in the org chat, disregarding the originating channel. "
                "Syntax otherwise exactly as the syntax of the timer command, read there for more information."
            ),
        }

    # -- dispatch ---------------------------------------------------------------

    def command_handler(self, name, msg, channel):
        command = msg.split(" ", 1)
        rest = command[1] if len(command) > 1 else ""
        head = command[0].lower()

        if head == "timer":
            return self._handle_timer(name, msg, channel)
        if head == "rtimer":
            return self._handle_rtimer(name, msg, channel)
        if head == "remtimer":
            if rest and _is_numeric(rest):
                return self.rem_timer(name, rest)
            return "No timer id provided."
        if head == "ptimer":
            if rest:
                return self.command_handler(name, f"timer {rest}", "gc")
            return self.command_handler(name, "timer", "gc")
        return False

    def _handle_timer(self, name, msg, channel):
        match = re.match(r"^timer ([1-9][0-9]*[mshd]?) (.*)", msg, re.I)
        if match:
            return self.add_timer(name, match.group(1), match.group(2), 0, channel)
        match = re.match(r"^timer ([0-9]+(?::[0-9][0-9]){0,3}) (.*)", msg, re.I)
        if match:
            return self.add_timer(name, match.group(1), match.group(2), 0, channel)
        if re.match(r"^timer$", msg, re.I):
            return self.show_timer(name, channel)
        return (
            "Correct Format: ##highlight##<pre>timer #[mshd] title##end## or "
            "##highlight##<pre>timer #[:##[:##[:##]]] title##end##"
        )

    def _handle_rtimer(self, name, msg, channel):
        match = re.match(r"^rtimer ([1-9][0-9]*[mshd]?) ([1-9][0-9]*[mshd]?) (.*)", msg, re.I)
        if match:
            return self.add_timer(name, match.group(1), match.group(3), match.group(2), channel)
        match = re.match(
            r"^rtimer ([0-9]+(?::[0-9][0-9]){0,3}) ([0-9]+(?::[0-9][0-9]){0,3}) (.*)", msg, re.I
        )
        if match:
            return self.add_timer(name, match.group(1), match.group(3), match.group(2), channel)
        return (
            "Correct Format: ##highlight##<pre>rtimer <dur>[mshd] <repeat>[mshd] title##end## or "
            "##highlight##<pre>rtimer <dur>[:##[:##[:##]]] <repeat>[:##[:##[:##]]] title##end##"
        )

    # -- creation -----------------------------------------------------------------

    def add_timer(self, owner, timestr, name, repeatstr, channel) -> str:
        time_core = self.bot.core("time")
        duration = time_core.parse_time(timestr)
        repeat = time_core.parse_time(repeatstr) if repeatstr else 0
        if repeat != 0:
            min_repeat = self.bot.core("settings").get("Timer", "MinRepeatInterval")
            if repeat < min_repeat:
                return f"The repeat interval must be at least##highlight## {min_repeat}##end## seconds!"

        timer_id = self.bot.core("timer").add_timer(
            "timer_ui", duration, {"owner": owner, "name": name, "channel": channel, "repeat": repeat}
        )
        self._timers[timer_id] = {
            "owner": owner, "name": name, "channel": channel, "repeat": repeat,
            "endtime": time.time() + duration,
        }

        msg = (
            f"Timer ##highlight##{name} ##end##with ##highlight##"
            f"{time_core.format_seconds(duration)} ##end##runtime started!"
        )
        if repeat > 0:
            msg += f" The timer has a repeat interval of##highlight## {time_core.format_seconds(repeat)} ##end##"
        return msg

    # -- timer_core callback (fired when a scheduled timer is due) ----------------

    def timed_event(self, timer_id, data) -> None:
        meta = self._timers.pop(timer_id, None) or data
        owner, name, channel, repeat = meta["owner"], meta["name"], meta["channel"], meta.get("repeat", 0)

        msg = f"##highlight##{name}##end##"
        if channel != "tell":
            msg += f", ##highlight##{owner}##end##"
        msg += "!"
        self.bot.send_output(owner, msg, channel)

        if repeat > 0:
            new_id = self.bot.core("timer").add_timer(
                "timer_ui", repeat, {"owner": owner, "name": name, "channel": channel, "repeat": repeat}
            )
            self._timers[new_id] = {
                "owner": owner, "name": name, "channel": channel, "repeat": repeat,
                "endtime": time.time() + repeat,
            }

    # -- listing ------------------------------------------------------------------

    def show_timer(self, name, channel) -> str:
        if channel == "tell":
            entries = [
                (tid, m) for tid, m in self._timers.items()
                if m["channel"] == channel and m["owner"] == name
            ]
        else:
            entries = [(tid, m) for tid, m in self._timers.items() if m["channel"] == channel]
        if not entries:
            return "No timers defined!"

        entries.sort(key=lambda kv: kv[1]["endtime"])
        thistime = time.time()
        time_core = self.bot.core("time")
        tools = self.bot.core("tools")

        listing = ""
        for tid, meta in entries:
            listing += f"\n##blob_text##Timer ##end##{meta['name']} ##blob_text##has ##end##"
            listing += time_core.format_seconds(int(meta["endtime"] - thistime))
            listing += " ##blob_text##remaining"
            if meta["repeat"] > 0:
                listing += (
                    " and is repeated every ##end##" + time_core.format_seconds(meta["repeat"]) + "##blob_text##"
                )
            listing += f". Owner:##end## {meta['owner']} "
            listing += tools.chatcmd(f"remtimer {tid}", "[DELETE]")

        return tools.make_blob("Current timers", f"##blob_title##Timers for <botname>:##end##\n{listing}")

    # -- removal ------------------------------------------------------------------

    def rem_timer(self, name, timer_id):
        if timer_id is None or not _is_numeric(timer_id):
            return "Timer id is missing"
        return self._del_timer(name, int(timer_id), silent=False)

    def _del_timer(self, deleter, timer_id: int, silent: bool = True):
        meta = self._timers.get(timer_id)
        if meta is None:
            self.error.set("Invalid timer ID!")
            return self.error

        owner = meta["owner"]
        alts = self.bot.core("alts")
        do_delete = False
        admin = False
        if deleter.capitalize() == owner.capitalize():
            do_delete = True
        elif alts.main(deleter) == alts.main(owner):
            do_delete = True
        elif self.bot.core("security").check_access(deleter, self.bot.core("settings").get("Timer", "DeleteRank")):
            do_delete = True
            admin = True

        if not do_delete:
            self.error.set("You are not allowed to delete this timer!")
            return self.error

        self.bot.core("timer").del_timer(timer_id)
        self._timers.pop(timer_id, None)
        if admin and not silent:
            msg = f"Your timer ##highlight##{meta['name']}##end## was deleted by##highlight## {deleter}##end##!"
            self.bot.send_output(owner, msg, "tell")
        return f"The timer ##highlight##{meta['name']}##end## was deleted!"


def _is_numeric(value) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False
