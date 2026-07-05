"""Ported (redesigned) from Modules/TimerRelay.php.

Despite the name and despite what the PHP source does, this is **not** a
network bridge in this port. The original wired together two things this
codebase never ported:
  * `extpgmsg` handling of a wire-format string
    (`relaytimer class:.. endtime:.. owner:.. repeat:.. channel:.. name:..`)
    coming from *another* bot instance over a shared private group -- the
    multi-bot relay bridge concept (`core("relay")`, a "Relay"/"Status" +
    "Relay"/"Relay" settings pair naming the trusted relay-source bot).
    No such bridge/settings pair exists anywhere in this codebase (`grep`
    confirms no other ported module creates a "Relay" settings group), so
    that input could never legitimately arrive here.
  * `core("timer")`'s *old* full DB-backed named "timer classes" API
    (`add_timer(true, $owner, $endtime, $name, $channel, $repeat, $class)`).
    The ported `main_modules/timer_core.py` deliberately dropped that whole
    layer -- see its docstring -- and only kept `add_timer(owner, seconds,
    data)` / the `register_event("timer", name)` callback contract.

So this module is reduced to the one behavior that still makes sense on
top of what's actually ported: a SUPERADMIN can schedule a plain relative
timer via chat (`relaytimer <seconds> <name>`), and when it fires this
module is notified through `core("timer")`'s callback contract and
announces completion to chat (gc + pgroup, or a quiet tell to the
requester if `TimerRelay/QuietRelay` is on). Dependencies are therefore
only `core("settings")` and `core("timer")`, as intended.
"""
from __future__ import annotations

import re

from ..commodities.base import BaseActiveModule

_CALLBACK_NAME = "timer_relay"


class TimerRelay(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("timer_relay")
        self.register_command("tell", "relaytimer", "SUPERADMIN")

        self.help["description"] = "Schedules a timer and announces its completion to chat."
        self.help["command"] = {}
        self.help["command"]["relaytimer <seconds> <name>"] = (
            "Schedules <name> to be announced to chat after <seconds> seconds."
        )

        self.bot.core("settings").create(
            "TimerRelay", "QuietRelay", False,
            "Announce completed relay timers quietly (tell the requester only) instead of to gc/pg?",
        )
        self.register_event("timer", _CALLBACK_NAME)
        self._pending: dict[int, dict] = {}

    def command_handler(self, name, msg, origin):
        match = re.match(r"^relaytimer\s+(\d+)\s+(.+)$", msg, re.I)
        if not match:
            self.bot.send_help(name)
            return False
        seconds = int(match.group(1))
        timer_name = match.group(2).strip()
        info = {"name": timer_name, "requester": name}
        timer_id = self.bot.core("timer").add_timer(_CALLBACK_NAME, seconds, info)
        self._pending[timer_id] = info
        return f"Timer '{timer_name}' scheduled to be announced in {seconds} second(s)."

    def timed_event(self, timer_id, data) -> None:
        info = self._pending.pop(timer_id, None)
        if info is None:
            info = data if isinstance(data, dict) else {}
        timer_name = info.get("name", "Unknown")
        msg = f"Timer '##highlight##{timer_name}##end##' has completed!"
        if self.bot.core("settings").get("TimerRelay", "QuietRelay"):
            requester = info.get("requester")
            if requester:
                self.bot.send_tell(requester, msg)
        else:
            self.bot.send_gc(msg)
            self.bot.send_pgroup(msg)
