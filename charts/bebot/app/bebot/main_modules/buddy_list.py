"""Ported from Core/BuddyList.php.

Registers as "buddy" (`self.bot.core("buddy")`). Translates a raw AO buddy
logon/logoff event -- surfaced by the game connection as a numeric
character id plus an online flag -- into the "buddy" event fan-out that
other modules subscribe to via `register_event("buddy")` (see
main_modules/logon_notifies.py and main_modules/online.py, both of which
already expose a `buddy(name, msg)` handler stored in `bot.commands["buddy"]`
by `Bot.register_event()`). `on_buddy_onoff(uid, online)` below is this
module's public entry point for that raw event and is the direct
equivalent of the PHP class's `buddy_ao($args)`.

Scope cuts vs. the PHP original:
  * Age of Conan support (`buddy_aoc($args)`, and the constructor's
    `strtolower($this->bot->game) == 'aoc'` branch that would have wired it
    up instead of `buddy_ao`) is dropped. `Bot.game` is hardcoded to `"Ao"`
    in this port (see bot.py's docstring: "AoC support ... [is] not
    ported"), so the AoC branch could never fire -- `buddy_aoc`'s Whois
    lookups, `#___craftingclass` query, and LFG/AFK status-change bitmask
    logic (all AoC-only machinery) are therefore out of scope here too.
  * The PHP constructor connects directly to the now-dropped sfEvent
    dispatcher (`$this->bot->dispatcher->connect('Core.on_buddy_onoff',
    ...)` -- see aochat/protocol.py's docstring: "the sfEvent dispatcher
    ... [is] intentionally not ported"). There is currently no code path in
    this port's AOChat.on_packet() that calls `on_buddy_onoff()` when an
    `AOCP_BUDDY_LOGONOFF` packet arrives (it just updates
    `AOChat.buddies` -- see aochat/protocol.py). Wiring that dispatch is
    left to whichever future pass wires up the connection layer; this
    module still exposes the correct public method/behavior for that wiring
    to call into, matching the "direct call instead of dispatcher" pattern
    used elsewhere in this port (see aochat/protocol.py's docstring).
  * PHP's `$this->bot->glob["online"]` (an ad-hoc registry with no
    equivalent anywhere in this port's `Bot` class -- see main_modules/
    online.py's docstring, which drops the same thing) is replaced with an
    instance attribute (`self.online`) local to this module. It serves the
    exact same "is this user already marked online" dedup/guard purpose.
  * The PHP module iterates `$this->bot->commands["buddy"]` directly and
    calls `->buddy($user, $online)` on each entry. This port instead uses
    `self.bot.commands.get("buddy", {})`, which is the exact same dict
    `Bot.register_event("buddy", ...)` populates -- so any module that
    called `self.register_event("buddy")` (see BasePassiveModule) is
    dispatched to identically.
  * "Using aoc -> buddy_remove() here is an exception" in the PHP source
    (calling `$this->bot->aoc->buddy_remove()` directly instead of going
    through `core("chat")`) is replaced with `self.bot.core("chat")
    .buddy_remove(user)`, matching the established call pattern already
    used by main_modules/notify.py and main_modules/user.py for the same
    operation (main_modules/aochat_wrapper.py's `ChatWrapper.buddy_remove`
    wraps `bot.aoc.buddy_remove()` in `asyncio.ensure_future` either way,
    so the net effect on the connection is identical).
  * No DB schema/schema-version migration logic exists in the original for
    this module (it's pure in-memory state plus event fan-out), so nothing
    was dropped there.
"""
from __future__ import annotations

from ..commodities.base import BasePassiveModule


class BuddyList(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("buddy")
        self.online: dict[str, str] = {}

    # -- raw buddy on/off event entry point (PHP: buddy_ao($args)) ------------
    def on_buddy_onoff(self, uid, online) -> None:
        user = self.bot.core("player").name(uid)
        if not user:
            self.bot.log("DEBUG", "BuddyList", "on_buddy_onoff() got empty user")
            self.bot.log("DEBUG", "BuddyList", self.bot.debug_bt())
            return

        member = self.bot.core("notify").check(user)

        # Only cache members/guests on notify to avoid !is and other buddy
        # actions misbehaving for non-members.
        if member:
            if online == 1:
                if user in self.online:
                    # Buddy logged on despite already being marked online -- ignore.
                    return
                self.online[user] = user
            else:
                if user not in self.online:
                    # Buddy logged off with no prior logon on record -- ignore.
                    return
                self.online.pop(user, None)

        if not member:
            end = " (not on notify)"
            # Exception to the rule: this bypasses any higher-level buddy_remove()
            # checks since none of them are needed here (mirrors the PHP comment).
            self.bot.core("chat").buddy_remove(user)
        else:
            security = self.bot.core("security")
            end = f" ({security.get_access_name(security.get_access_level(user))})"

        state = "on" if online == 1 else "off"
        self.bot.log("BUDDY", "LOG", f"{user} logged [{state}]{end}")

        for module in list(self.bot.commands.get("buddy", {}).values()):
            if module is not None:
                module.buddy(user, online)
