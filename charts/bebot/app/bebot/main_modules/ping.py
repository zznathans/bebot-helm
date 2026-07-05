"""Ported from Modules/Ping.php (class `ping`).

Lets the bot owner ping (`ping`) or traceroute (`tracert`) the chat server
it is currently connected to, and shows the raw command output in a blob.
Depends on `core("settings")` (`Ping/Server` -- Windows vs. Linux/Unix,
which selects the ping/traceroute command's flags -- and `Ping/PingCount`)
and `core("tools")` (`make_blob()`).

Scope notes / intentional deviations from the PHP:
  * `select_dimension()` (a hardcoded `$this->bot->dimension` switch
    mapping dimension numbers to `chat.d[t1].funcom.com` hostnames) is
    dropped in favor of just reading `self.bot.server` -- `conf.py`
    (`BotConfig.server`/`SERVER_LIST`/`_DIMENSION_ALIASES`) already
    resolves the bot's dimension to its chat server hostname once, at
    config-load time, for the bot to actually connect to. Re-deriving the
    same mapping a second time here (as the PHP did) would risk the two
    falling out of sync; reusing the one the bot already computed is
    simpler and can't drift.
  * The PHP's `system()`/`exec()` calls (which build a raw shell command
    string by interpolating `$host`/`$count` and rely on the preceding
    `preg_replace` sanitization to keep that safe) are ported as
    `subprocess.run()` with an argument *list* (no shell string
    interpolation at all), via the small `_execute()` helper -- a strictly
    safer equivalent of the same sanitize-then-run idea, and easy for
    tests to monkeypatch. The `[^A-Za-z0-9.-]`/`[^0-9]` sanitization of
    host/count is kept as well, purely as defense in depth.
  * `system("killall ping")` / `system("killall -q traceroute")` (cleanup
    of any stray/hung ping processes on Linux, run unconditionally after
    every ping/tracert regardless of whether the one just run was still
    alive) is not ported -- `subprocess.run()` with a timeout already
    waits for the child to exit or kills it itself, so there is nothing
    left running to clean up.
"""
from __future__ import annotations

import re
import subprocess

from ..commodities.base import BaseActiveModule

_HOST_RE = re.compile(r"[^A-Za-z0-9.-]")
_DIGITS_RE = re.compile(r"[^0-9]")


class Ping(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_command("all", "ping", "OWNER")
        self.register_command("all", "tracert", "OWNER")
        self.register_module("ping")

        self.help["description"] = (
            "Runs a ping or trace route to chat server that the bot is currently running on."
        )
        self.help["command"] = {
            "ping": "Pings the current chat server and shows the result.",
            "tracert": "Runs a trace route to the current chat server and shows the result.",
        }

        settings = self.bot.core("settings")
        settings.create("Ping", "Server", "Windows", "Is the server running Windows or Linux/Unix?", "Windows;Linux")
        settings.create("Ping", "PingCount", 4, "How many times should we ping the server?", "1;2;3;4;5;7;10")

    # -- dispatch ---------------------------------------------------------------
    def command_handler(self, name, msg, origin):
        if re.match(r"^ping$", msg, re.I):
            return self.ping_server()
        if re.match(r"^tracert$", msg, re.I):
            return self.tracert_server()
        return None

    # -- helpers ----------------------------------------------------------------------
    def _host(self) -> str:
        return _HOST_RE.sub("", self.bot.server or "")

    def _count(self) -> str:
        count = str(self.bot.core("settings").get("Ping", "PingCount"))
        return _DIGITS_RE.sub("", count) or "4"

    def _is_linux(self) -> bool:
        return str(self.bot.core("settings").get("Ping", "Server")).lower() == "linux"

    def _execute(self, cmd: list[str]) -> list[str]:
        """Runs cmd, returning its stdout split into non-blank lines (or [] on failure)."""
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as exc:
            self.bot.log("ERROR", self.module_name, f"Failed to run {cmd!r}: {exc}")
            return []
        output = proc.stdout or proc.stderr or ""
        return [line for line in output.splitlines() if line.strip()]

    def _results_blob(self, title: str, host: str, lines: list[str], extra: str = "") -> str:
        msg = f"<b>Server:</b> {host}\n{extra}<b>Results:</b>\n"
        if not lines:
            msg += (
                "Could not find results.  Please check <i>!settings ping</i> and verify you "
                "have the correct system type selected."
            )
        else:
            msg += "\n".join(lines) + "\n"
        return f"{title} :: {self.bot.core('tools').make_blob('click to view', msg)}"

    # -- commands ---------------------------------------------------------------------
    def ping_server(self) -> str:
        count = self._count()
        host = self._host()
        if self._is_linux():
            cmd = ["ping", f"-c{count}", f"-w{count}", host]
        else:
            cmd = ["ping", "-n", count, host]
        lines = self._execute(cmd)
        return self._results_blob("Ping results", host, lines, extra=f"<b>Ping Count:</b> {count}\n\n")

    def tracert_server(self) -> str:
        host = self._host()
        if self._is_linux():
            cmd = ["traceroute", host]
        else:
            cmd = ["tracert", host]
        lines = self._execute(cmd)
        return self._results_blob("Trace route results", host, lines)
