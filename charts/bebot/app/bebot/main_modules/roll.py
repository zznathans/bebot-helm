"""Ported from Modules/Roll.php (class `Roll`).

Lets players roll a number in a range (`roll <min> <max> [item]`), flip a
coin (`flip [item]`), and re-display a past roll/flip result for
verification (`verify <num>`, tell-channel only, ANONYMOUS access -- so
anyone whispering the bot, even players it hasn't seen before, can look up
a roll id). Depends on `core("settings")` (the `Roll/RollTime` per-player
cooldown) and `core("tools")` (`my_rand()` for the actual roll/flip).

`roll_info` (the flat, ever-growing list of past rolls *and* flips --
`do_flip()` appends to the same list `do_roll()` does) and `lastroll`
(per-name cooldown timestamps, shared between `roll` and `flip`) are kept
as plain instance state, same as the PHP's `$roll_info`/`$lastroll`
member arrays -- there's no persistence across bot restarts in the
original either.

Scope notes / intentional deviations from the PHP:
  * `do_roll()`'s debug `echo "Debug: " . ...` (a raw stdout print of the
    roll result, guarded by nothing -- always fires) is dropped; it was
    never wired to the module's own logger and produced no user-visible
    output.
  * The min/max integer-ness check (PHP: `($max != (int)$max) || $min !=
    (int)$min`, exploiting PHP's numeric-string loose comparison) is
    ported as a plain "is this a base-10 integer literal" regex check
    (`^-?[0-9]+$`). This is behaviorally identical for realistic input
    (chat users type plain integers) and only differs from PHP's exact
    loose-comparison edge cases for inputs like `"5.0"` (which PHP's loose
    comparison would accept as "the same as" `5`); such inputs are not
    expected from real chat commands.
  * `verify()`'s local rebind of `$name` to an already-`##highlight##`-
    wrapped string, which then gets wrapped in `##highlight##...##end##`
    *again* a few lines later (`"Roller: ##highlight##{$name}##end##"`),
    double-nests the highlight markup around the roller's name. This is
    preserved verbatim -- it's a real quirk of the original template
    string construction, not a Python-side bug, and is harmless (nested
    tags just render as a single highlight in every client observed).
  * `verify()`'s PHP bound check (`$num < 0 || $num > count(...)`) would in
    principle let `num == 0` through to index `$roll_info[-1]`, but that
    path is actually unreachable: the only way to reach it with `num == 0`
    is a user typing `verify 0`, and PHP's `empty($num)` (checked first)
    treats the *string* `"0"` as empty just like `""`/`null`, so it's
    redirected to "show the latest roll" before the bound check ever runs.
    This port keeps that same empty()-first behavior (`"0"` is folded into
    "show latest", same as `""`), so there is no case where a 0 index is
    ever actually built -- nothing to additionally guard against.
"""
from __future__ import annotations

import re
import time

from ..commodities.base import BaseActiveModule, BotError

_INT_RE = re.compile(r"^-?[0-9]+$")


def _is_int_literal(text: str) -> bool:
    return bool(_INT_RE.match(text or ""))


class Roll(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.roll_info: list[dict] = []
        self.lastroll: dict[str, float] = {}

        self.register_command("all", "roll", "GUEST")
        self.register_command("all", "flip", "GUEST")
        self.register_command("tell", "verify", "ANONYMOUS")
        self.register_module("roll")

        self.help["description"] = "Throws a dice and shows the result."
        self.help["command"] = {
            "roll <min> <max> [item]": (
                "Rolls a number between <min> and <max> and shows the result. You can provide "
                "an optional [item] to record what the dice is being rolled for."
            ),
            "flip [item]": (
                "Flips a coin and shows the result. You can provide an optional [item] to record "
                "what the coin is being flipped for."
            ),
            "verify <num>": "Shows the result of roll <num>",
        }

        self.bot.core("settings").create(
            "Roll",
            "RollTime",
            30,
            "How many seconds must someone wait before they can roll again?",
            "5;10;20;30;45;60;120;300;600",
        )

    # -- dispatch ---------------------------------------------------------------
    def command_handler(self, name, msg, origin):
        com, _, rest = msg.partition(" ")
        com = com.lower()

        if com == "roll":
            min_str, _, remainder = rest.partition(" ")
            max_str, _, item = remainder.partition(" ")
            if not max_str:
                max_str, min_str = min_str, "1"
            return self.do_roll(name, min_str, max_str, item)
        if com == "flip":
            return self.do_flip(name, rest)
        if com == "verify":
            return self.verify(rest)

        self.bot.send_help(name)
        return None

    # -- verification -------------------------------------------------------------
    def verify(self, num):
        # Mirrors PHP's empty($num): "", "0", and 0 are all "empty" (PHP's
        # empty() treats the *string* "0" as empty, same as 0/None/"").
        if num in (None, "", "0", 0):
            num = len(self.roll_info)
        else:
            try:
                num = int(num)
            except (TypeError, ValueError):
                num = 0
        if num < 1 or num > len(self.roll_info):
            self.error.set("Invalid verification ID")
            return self.error

        roll = self.roll_info[num - 1]
        name = f"##highlight##{roll['name']}##end##"
        if roll.get("item"):
            item_line = f"Target: ##highlight##'{roll['item']}'##end##\n"
        else:
            item_line = "..."
        elapsed = int(time.time() - roll["time"])
        window = f"##blob_title##::: Roll verification: {num} :::##end##\n\n"
        window += f"Roller: ##highlight##{name}##end##\n"
        window += f"Time: ##highlight##{elapsed} seconds ago##end##\n"
        window += item_line
        window += "-----------------\n"
        window += f"Range: {roll['range']}\n"
        window += f"Result: {roll['result']}\n"
        window += "-----------------\n"
        return self.bot.core("tools").make_blob(
            f"Roll result: {roll['result']}. Verify id: {num}", window
        )

    # -- roll -----------------------------------------------------------------------
    def do_roll(self, name, min_str, max_str, item):
        roll_time = self.bot.core("settings").get("Roll", "RollTime")
        last = self.lastroll.get(name)
        if last is not None and last >= time.time() - roll_time:
            return f"You may only roll once every {roll_time} seconds."

        if not max_str:
            self.error.set("You need to specify a maximum value")
            return self.error
        if not _is_int_literal(max_str) or not _is_int_literal(min_str):
            self.error.set("The min and max values need to be an integer.")
            return self.error
        max_val = int(max_str)
        if max_val < 2:
            self.error.set("There is no point in rolling for less than one person.")
            return self.error

        result = {
            "name": name,
            "time": time.time(),
            "range": f"{min_str} - {max_str}",
            "result": self.bot.core("tools").my_rand(int(min_str), max_val),
            "item": item,
        }
        self.lastroll[name] = time.time()
        self.roll_info.append(result)
        return self.verify(len(self.roll_info))

    # -- flip -----------------------------------------------------------------------
    def do_flip(self, name, item):
        roll_time = self.bot.core("settings").get("Roll", "RollTime")
        last = self.lastroll.get(name)
        if last is not None and last >= time.time() - roll_time:
            return f"You may only flip once every {roll_time} seconds."

        result = {
            "name": name,
            "time": time.time(),
            "range": "heads/tails",
            "result": "heads" if self.bot.core("tools").my_rand(0, 1) else "tails",
            "item": item,
        }
        self.lastroll[name] = time.time()
        self.roll_info.append(result)
        return self.verify(len(self.roll_info))
