"""Ported from Modules/Scripts.php.

Lets chat users browse and view small text "scripts" (snippets of admin
notes/macros bundled with the bot) stored under `Extras/Scripts` relative
to the process's working directory, same as the PHP original.

Scope notes / intentional deviations from the PHP:
  * `make_script()` adds a path-traversal guard (rejects any script name
    containing a path separator or resolving outside `Extras/Scripts`).
    The PHP original passed the raw chat argument straight into
    `fopen($dir."/".$script, "r")` with `register_command('all', 'script',
    'GUEST')` -- i.e. any guest could read arbitrary files off disk with
    `script ../../../etc/passwd`. That's a real vulnerability, not a
    behavior worth preserving, so this port closes it rather than
    reproducing it verbatim.
  * `parse_com()` (no Python equivalent ported) is replaced with plain
    string splitting on the command prefix, same approach already used by
    every other ported *Ui module in this codebase.
  * Missing `Extras/Scripts` directory is handled as "0 scripts found"
    rather than letting `scandir()`'s PHP warning propagate -- there is
    nothing for a warning to usefully do here.
"""
from __future__ import annotations

from pathlib import Path

from ..commodities.base import BaseActiveModule


class Scripts(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("scripts")
        self.register_command("all", "scripts", "GUEST")
        self.register_command("all", "script", "GUEST")

        self.help["description"] = "Shows code popup of scripts. Scripts are shared by bot owner only."
        self.help["command"] = {}
        self.help["command"]["scripts"] = "Shows the list of all available scripts."
        self.help["command"]["script <scriptname>"] = "Shows a specific script code to be copied-pasted."

        self.path = Path("Extras/Scripts")

    def command_handler(self, name, msg, origin):
        self.error.reset()
        parts = msg.split(" ", 1)
        arg = parts[1].strip() if len(parts) > 1 else ""
        if not arg:
            return self.make_list()
        return self.make_script(arg)

    def make_list(self) -> str:
        if not self.path.is_dir():
            return f"0 script(s) found : no file currently available in expected path ({self.path})."
        content = ""
        total = 0
        for entry in sorted(self.path.iterdir(), key=lambda p: p.name):
            if entry.is_dir() or entry.name == ".gitkeep":
                continue
            content += self.bot.core("tools").chatcmd(f"scripts {entry.name}", entry.name) + " \n"
            total += 1
        if total == 0:
            return f"0 script(s) found : no file currently available in expected path ({self.path})."
        return f"{total} script(s) found : " + self.bot.core("tools").make_blob("click to view", content)

    def make_script(self, script: str) -> str:
        if script == ".gitkeep" or "/" in script or "\\" in script or ".." in script:
            return "Specified script not found ..."
        candidate = self.path / script
        try:
            resolved = candidate.resolve()
            base_resolved = self.path.resolve()
        except OSError:
            return "Specified script not found ..."
        if base_resolved not in resolved.parents and resolved != base_resolved:
            return "Specified script not found ..."
        if not resolved.is_file():
            return "Specified script not found ..."
        content = resolved.read_text(errors="replace")
        content = f"<b>:::: Script [{script}] ::::</b>\n\n{content}"
        return f"Script ({script}):: " + self.bot.core("tools").make_blob("click to view", content)
