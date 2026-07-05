"""Ported from Modules/CommandAliasUi.php.

Thin chat-command front-end over the already-ported `core("command_alias")`
(Main/15_CommandAlias.php, command_alias.py). All of the actual state --
the alias/alias_sub caches, the `#___command_alias` table -- lives on that
core module; this module only parses `comalias ...` chat commands and
forwards to it.

Scope notes:
  * The PHP original's `get_list()` (listing all top-level aliases with a
    "click to view" blob and a per-row `[DELETE]` chatcmd) lives on
    Main/15_CommandAlias.php's *core* class, not on CommandAliasUi.php.
    That method was intentionally left off command_alias.py's port (its
    public interface is documented as `register`/`replace`/`add`/`exists`/
    `delete` only), so the default/no-subcommand branch here rebuilds the
    same listing directly from the core module's public `alias` dict
    instead of calling a `get_list()` that doesn't exist on the port.
  * Unlike the PHP `get_list()`, which issues a second DB query to decide
    whether to show a `[DELETE]` link per row (only shown for aliases that
    exist in the `#___command_alias` table, as opposed to ones registered
    in-memory via `register()` e.g. from config), this port always shows
    the `[DELETE]` link for every alias and relies on `delete()`'s own
    "cannot be deleted" reply to cover the non-DB-backed case. This avoids
    reaching past the core module's public interface to query the table
    directly, at the cost of an occasionally-clickable link that reports
    failure instead of being hidden outright -- a minor, low-stakes UX
    difference from the original.
"""
from __future__ import annotations

from ..commodities.base import BaseActiveModule


class CommandAliasUi(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("command_alias_ui")
        self.register_command("all", "comalias", "SUPERADMIN")
        self.help["description"] = "Handles Command Aliases."
        self.help["command"] = {
            "comalias add <alias> <command>": "Sets <alias> as an alias of <command>.",
            "comalias del <alias>": "Deletes <alias>.",
            "comalias rem <alias>": "Deletes <alias>.",
            "comalias": "Show All Aliases.",
        }

    def command_handler(self, name, msg, origin):
        parts = msg.split(" ", 2)
        sub = parts[1] if len(parts) > 1 else ""
        if sub == "add":
            return self.bot.core("command_alias").add(parts[2] if len(parts) > 2 else "")
        if sub in ("del", "rem"):
            return self.bot.core("command_alias").delete(parts[2] if len(parts) > 2 else "")
        return self.get_list()

    def get_list(self) -> str:
        command_alias = self.bot.core("command_alias")
        aliases = command_alias.alias
        if not aliases:
            return "No command aliases set!"
        tools = self.bot.core("tools")
        inside = ":: Command aliases ::\n\n"
        for alias, command in aliases.items():
            inside += f"##orange##{alias}##end## is an alias of ##orange##{command}##end##."
            inside += " " + tools.chatcmd(f"comalias del {alias}", "[DELETE]")
            inside += "\n"
        return "Command aliases :: " + tools.make_blob("click to view", inside)
