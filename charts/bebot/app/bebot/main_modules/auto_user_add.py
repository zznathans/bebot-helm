"""Ported from Modules/AutoUserAdd.php.

Registers as "autouseradd". This module automatically adds new users it
notices in guild/org chat (and, optionally, the private channel) to the
user database via `core("user").add(...)`.

The PHP constructor pre-fills `$this->checked` with every current member
(`user_level = 2`) so those users aren't redundantly re-added the first
time they're seen talking; this is ported as-is via a startup query
against `#___users`.

`register(&$module)` lets other modules (per the PHP docstring: BansManagerUi
in a later port wave, matching its `core("autouseradd")` dependency) hook
into `add_user()`'s completion by exposing a `new_user(name)` method --
ported faithfully as `register()`/`self.hooks`.

Scope cuts vs. the PHP original:
  * `core("whois")->lookup($name)`-style AO-specific lookups don't appear in
    this module at all (nothing to cut there -- the PHP original doesn't
    call whois either).
  * The AOC-only game-check gate around `register_event("pgjoin")` (PHP:
    `if(strtolower($this->bot->game)=='ao') $this->register_event("pgjoin")`)
    is dropped in the sense that it's no longer conditional: `Bot.game` is
    hardcoded to `"Ao"` in this port (see bot.py), so the condition is
    always true and `pgjoin` is registered unconditionally, matching the
    only reachable behavior of the original.
"""
from __future__ import annotations

from ..commodities.base import BasePassiveModule
from .security import MEMBER


class AutoUserAdd(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("autouseradd")
        self.register_event("gmsg", "org")
        self.register_event("pgjoin")

        self.bot.core("settings").create(
            "Autouseradd", "Enabled", True, "Should Ao/Aoc bot users be added to the Bot?"
        )
        self.bot.core("settings").create(
            "Autouseradd", "Private", False, "Should Ao private channel be included in user detection?"
        )
        self.bot.core("settings").create(
            "Autouseradd", "Notify", False, "Should the User be Notified that he was added to the Bot?"
        )

        self.hooks: list = []
        # Fill checked with current members so we don't re-add them.
        self.checked: dict[str, bool] = {}
        rows = self.bot.db.select("SELECT nickname FROM #___users WHERE user_level = 2") or []
        for row in rows:
            self.checked[row[0]] = True

    # -- module (un)registration, called by other modules (e.g. BansManagerUi) --
    def register(self, module) -> None:
        self.hooks.append(module)

    # -- event handlers -----------------------------------------------------------
    def pgjoin(self, name) -> None:
        if self.bot.core("settings").get("Autouseradd", "Private"):
            self.gmsg(name, "private", "join")

    def gmsg(self, name, group, msg) -> None:
        if not self.bot.core("settings").get("Autouseradd", "Enabled"):
            return
        # Add all characters when they are noticed in chat the first time.
        if not self.checked.get(name):
            self.checked[name] = True
            result = self.bot.db.select(f"SELECT user_level FROM #___users WHERE nickname = '{name}'")
            if result:
                if result[0][0] != 2:
                    self.add_user(name)
            else:
                self.add_user(name)

    # -- custom functions -----------------------------------------------------------
    def add_user(self, name) -> None:
        silent = 0 if self.bot.core("settings").get("Autouseradd", "Notify") else 1
        self.bot.core("user").add(self.bot.botname, name, 0, MEMBER, silent)
        for hook in list(self.hooks):
            hook.new_user(name)
