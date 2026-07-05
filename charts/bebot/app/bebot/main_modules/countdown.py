"""Ported (adapted) from Modules/Countdown.php.

The PHP original builds a persistent, DB-backed "Countdown" timer class
via `core("timer")->create_timer_class()`/`create_timer_class_entry()`
(a chain of named entries fired at increasing offsets from a single
`add_timer(false, "countdown", 6, ..., "Countdown")` call) -- an
admin/UI layer over Main/15_TimerCore.php that main_modules/timer_core.py
deliberately does not port (see its docstring: "heavily reduced ... None
of that admin/UI layer is ported. What's kept is the actual contract
Bot.cron() depends on"). The ported `TimerCore.add_timer(owner, seconds,
data)` is a single one-shot callback, not a chain of staged entries.

This port reproduces the same user-visible behaviour -- a
5, 4, 3, 2, 1, GO GO GO countdown, red for the early steps fading to
orange then green at "GO" -- by scheduling six one-shot timers directly
(one per step, via `timer.add_timer("countdown", <seconds>, <payload>)`),
firing at t=1..6 seconds after the command, instead of chaining through a
timer-class/timer-class-entry mechanism that no longer exists. The
absolute firing order and displayed text/colours at each second exactly
match the PHP original's class-entry table (offset 0 -> "GO GO GO" was
the *last* entry to fire, at the full 6-second delay; offsets 1..5 fired
at 5..1 seconds before that).
"""
from __future__ import annotations

from ..commodities.base import BaseActiveModule, BotError

# (delay in seconds from the "countdown" command, display text)
_STEPS = (
    (1, "[##red##--------> 5 <-------##end##]"),
    (2, "[##red##--------> 4 <-------##end##]"),
    (3, "[##orange##--------> 3 <-------##end##]"),
    (4, "[##orange##--------> 2 <-------##end##]"),
    (5, "[##orange##--------> 1 <-------##end##]"),
    (6, "[##lightgreen##--> GO GO GO <--##end##]"),
)


class Countdown(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("countdown")
        self.register_command("all", "countdown", "LEADER")
        self.register_alias("countdown", "cd")
        self.register_event("timer", "countdown")

        self.bot.core("settings").create(
            "Countdown",
            "Channel",
            "both",
            "In which channel should a countdown be shown? In the channel of origin, or in both gc and pgmsg?",
            "both;gc;pgmsg;origin",
        )

        self.help["description"] = "A simple countdown plugin."
        self.help["command"] = {"countdown": "Counts down to zero."}
        self.help["notes"] = "<pre>cd is a synonym for <pre>countdown."

    # -- dispatch -----------------------------------------------------------------
    def command_handler(self, name, msg, origin):
        timer = self.bot.core("timer")
        for delay, text in _STEPS:
            timer.add_timer("countdown", delay, {"name": name, "origin": origin, "text": text})
        return "Countdown started!"

    # -- timer callback -------------------------------------------------------------
    def timed_event(self, timer_id, data):
        name = data["name"]
        origin = data["origin"]
        text = data["text"]
        out = self.bot.core("settings").get("Countdown", "Channel")
        if isinstance(out, BotError):
            out = "both"
        if str(out).lower() == "origin":
            self.bot.send_output(name, text, origin)
        else:
            self.bot.send_output(name, text, out)
