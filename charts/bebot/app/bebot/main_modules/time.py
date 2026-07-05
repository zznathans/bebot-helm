"""Ported from Core/Time.php.

Displays the current time and provides time-related helper functions
(duration parsing/formatting, "time ago" strings) used by other modules.

All PHP gmdate()/time() calls are UTC-based, so the port uses
datetime.now(timezone.utc)/calendar.timegm consistently to match.

Note: this file is named ``time.py`` and lives inside the ``main_modules``
package which is imported all over the codebase; the class itself is named
``TimeCore`` (not ``Time``) to avoid any confusion with the stdlib ``time``
module when reading code elsewhere. Because Python 3 always uses absolute
imports, a plain ``import time`` anywhere in the codebase (including in this
file, if needed) resolves to the stdlib module, never to this one -- cross-
module access to this module goes through ``bot.core("time")`` like every
other module, so there's no ambiguity in practice.

The PHP ``FormatString`` setting (a gmdate() format string used elsewhere in
the original bot for rendering dates) is preserved as a created setting for
parity/back-compat, but nothing in this port currently consumes it since the
"other modules render dates via a shared Time helper" call sites haven't been
ported yet.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone

from ..commodities.base import BaseActiveModule

AO_YEAR_OFFSET = 27474

_LEADING_INT_RE = re.compile(r"\s*([+-]?\d+)")


def _php_intval(value: str) -> int:
    """Mimic PHP's (int) cast on a string: parse a leading integer, else 0.

    e.g. "5m" -> 5, "  -3h" -> -3, "m5" -> 0, "" -> 0.
    """
    match = _LEADING_INT_RE.match(value)
    return int(match.group(1)) if match else 0


class TimeCore(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("time")
        self.register_command("all", "time", "GUEST")
        self.help["description"] = "Shows the time."
        self.help["command"] = {"time": "Shows the current time."}
        self.bot.core("settings").create(
            "Time",
            "FormatString",
            "F jS, Y H:i",
            "The format string used in all gmdate() calls throughout the bot. For more info check the "
            "help to gmdate() in the php manual. WARNING: DO NOT CHANGE THIS IF YOU DON'T KNOW WHAT THIS "
            "MEANS! Wrong entries will break the time display throughout the bot!",
        )

    def command_handler(self, name, msg, origin):
        return self.show_time()

    def show_time(self) -> str:
        now = datetime.now(timezone.utc)
        output = "It is currently " + now.strftime("%H:%M:%S %B ") + str(now.day) + ","
        if str(self.bot.game).lower() == "ao":
            output += f" {self.ao_year()} Rubi-Ka Universal Time. "
            e1 = " from Uncle Pumpkin-head"
            e2 = "Leet"
        else:
            e1 = ""
            e2 = "Conan"
        if now.month == 10 and now.day == 31:  # OMG Pumpkinsheads!
            output += f"##darkorange##Happy Halloween{e1}!!##end##"
        if now.month == 12 and now.day == 25:  # OMG Christmas!
            output += (
                "##red##Merry##end## ##lime##Christmas##end## ##red##from##end## "
                f"##lime##Santa##end## ##red##{e2}!##end##"
            )
        return output

    def ao_year(self) -> int:
        """The fictional AO Year based on the current (UTC) year. AO is set 27,474 years in the future."""
        return AO_YEAR_OFFSET + datetime.now(timezone.utc).year

    def get_dhms(self, seconds: int) -> dict[str, int]:
        """Split a duration in seconds into days/hours/minutes/seconds."""
        days = int(seconds / 86400)
        part_day = seconds - (days * 86400)
        hours = int(part_day / 3600)
        part_hour = part_day - (hours * 3600)
        minutes = int(part_hour / 60)
        secs = part_hour - (minutes * 60)
        return {"days": days, "hours": hours, "minutes": minutes, "seconds": secs}

    def format_seconds(self, totalsec) -> str:
        """Render a duration in seconds as (optionally negative) H:M:S."""
        if totalsec < 0:
            minus = "-"
            totalsec = abs(totalsec)
        else:
            minus = ""
        hours = totalsec // 3600
        rest = totalsec % 3600
        minutes = rest // 60
        seconds = rest % 60
        return f"{minus}{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"

    def parse_time(self, timestr: str) -> int:
        """Parse a duration string ("5m", "2h", "1d", "1:30:00", plain seconds) into seconds.

        Faithful port of the PHP parse_time() -- including its quirk of only
        checking for the presence of 'm'/'h'/'d' anywhere in the string (not
        necessarily as a trailing unit suffix), and the right-to-left,
        colon-separated-field handling.
        """
        lower = timestr.lower()
        timesize = 1
        timeunit = 1
        if "m" in lower:
            timesize = 60
            timeunit = 2
        elif "h" in lower:
            timesize = 60 * 60
            timeunit = 3
        elif "d" in lower:
            timesize = 60 * 60 * 24
            timeunit = 4

        if ":" in timestr:
            timeparts = timestr.split(":")
            numberlength = 0
            for part in reversed(timeparts):
                value = _php_intval(part)
                numberlength += timesize * value
                if timeunit == 1:
                    timesize = 60
                elif timeunit == 2:
                    timesize = 60 * 60
                elif timeunit >= 3:
                    timesize = 24 * 60 * 60
                timeunit += 1
        else:
            numberlength = _php_intval(timestr) * timesize

        return numberlength

    def time_ago(self, when) -> str:
        """Render how long ago `when` (a unix timestamp) was, e.g. "2 days 3 hours 4 mins ago"."""
        diftime = int(time.time()) - when
        diftime = diftime // 60
        timestr = " " + str(diftime % 60) + " mins"
        diftime = diftime // 60
        if diftime > 0:
            if diftime > 24:
                diftimedays = diftime // 24
                timestr = str(diftime % 24) + " hours" + timestr
                return str(diftimedays) + " days " + timestr + " ago"
            else:
                timestr = str(diftime) + " hours" + timestr
                return timestr + " ago"
        return timestr + " ago"
