"""Ported from Modules/nroll.php (class `Nroll`).

A distinct, simpler alternative to `roll.py`'s `!roll`/`!flip`: `nroll
<keywords>` picks one of several comma- (or, if no commas are present,
space-) separated options at random, and `nverify <id>` re-displays a past
pick for verification. This is not a duplicate of Roll.php -- it has its
own independent verify-log (`verifyresult`/`verifytime`/`verifyname`) and,
notably, its own indexing scheme (see below). Depends on `core("tools")`
(`my_rand()`, replacing the PHP's raw `array_rand()` with this port's
central RNG helper -- the same substitution `roll.py` makes for its own
random picks).

Scope notes / intentional deviations from the PHP:
  * **Verify ids here are 0-based**, unlike `roll.py`'s `verify`, which is
    1-based. The PHP computes the displayed id via `end($this->verifyresult);
    key($this->verifyresult)` -- the *array key* of the just-appended
    element, which for a plain 0-indexed PHP array is `count() - 1`, not
    `count()`. So the very first `nroll` ever run displays "nverify 0", not
    "nverify 1". This is a real difference between the two modules'
    behavior, not a copy-paste slip in this port -- preserved faithfully.
  * `nverify <id>`'s PHP `isset($this->verifyresult[$info[1]])` relies on
    PHP auto-casting a numeric-looking string key (e.g. `"0"`) to an
    integer array index; non-numeric input just misses (`isset()` is
    false). Ported as a plain `int(id)` parse with a `try/except` falling
    through to the same "Results not found" message on failure.
  * The PHP's commented-out `$this->bot->send_output(...)` calls in both
    branches were already dead code (commented out) upstream -- not
    ported. `command_handler()` simply returns the built string, same as
    every other message in this branch, and the base class's own reply
    plumbing sends it.
"""
from __future__ import annotations

import re
import time

from ..commodities.base import BaseActiveModule


class Nroll(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.verifyresult: list[str] = []
        self.verifytime: list[float] = []
        self.verifyname: list[str] = []

        self.register_command("all", "nroll", "GUEST")
        self.register_command("all", "nverify", "GUEST")
        self.register_module("nroll")

        self.help["description"] = "Randomly choose one of several options."
        self.help["command"] = {
            "nroll keywords": (
                "Randomly choose one of several keywords, seperated by commas or if no "
                "commas are present, by spaces."
            ),
            "nverify #": "Verify a previous nroll.",
        }

    # -- dispatch ---------------------------------------------------------------
    def command_handler(self, name, msg, origin):
        match = re.match(r"^nroll (.+)$", msg, re.I)
        if match:
            return self._do_nroll(name, match.group(1))

        match = re.match(r"^nverify (.+)$", msg, re.I)
        if match:
            return self._do_nverify(match.group(1))

        return ""

    def _do_nroll(self, name: str, options_str: str) -> str:
        if "," in options_str:
            options = options_str.split(",")
        else:
            options = options_str.split(" ")

        tools = self.bot.core("tools")
        result = options[tools.my_rand(0, len(options) - 1)]

        self.verifyresult.append(result)
        self.verifytime.append(time.time())
        self.verifyname.append(name)
        index = len(self.verifyresult) - 1

        return (
            f"I choose <font color=yellow>{result}</font>.  To verify, "
            f"/tell <botname> <pre>nverify {index}"
        )

    def _do_nverify(self, id_str: str) -> str:
        try:
            index = int(id_str)
        except ValueError:
            index = -1
        if 0 <= index < len(self.verifyresult):
            elapsed = int(time.time() - self.verifytime[index])
            return (
                f"I chose <font color=yellow>{self.verifyresult[index]}</font> for "
                f"<font color=green>{self.verifyname[index]}</font> "
                f"<font color=red>{elapsed}</font> seconds ago."
            )
        return (
            "Results not found.  Please check your query and try again.  "
            "If that doesn't work, give up, it ain't worth it."
        )
