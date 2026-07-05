"""Ported from Core/BuddyQueue.php: a rate-limited queue for adding and
removing AO buddies, built the same way ChatQueue rate-limits outgoing
tells/gc -- as a thin registrant on top of the generic core("queue")
leaky-bucket module (see main_modules/queue.py).

Scope note: the PHP original calls `$this->bot->aoc->buddy_add($uid)` /
`$this->bot->aoc->buddy_remove($uid)` directly. In this port `bot.aoc`'s
buddy_add()/buddy_remove() are coroutines, so instead of duplicating the
asyncio.ensure_future() dispatch here, do_add()/do_delete() route through
core("chat").buddy_add()/buddy_remove() (main_modules/aochat_wrapper.py),
which already wraps that dispatch for exactly this purpose -- functionally
identical to the PHP, just going through the already-ported wrapper
instead of touching `bot.aoc` a second time in this codebase.

The PHP do_add()'s error-log message ("Tried to add X as a buddy when
they already are one") is logged on the *invalid uid* branch (empty/0/-1),
not on the "buddy already exists" branch -- that's a quirk/copy-paste bug
in the original text, ported faithfully (message text kept as-is) since
changing behavior wasn't asked for.
"""
from __future__ import annotations

from ..commodities.base import BasePassiveModule


class BuddyQueue(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("buddy_queue")

        settings = self.bot.core("settings")
        settings.create(
            "Buddy_Queue",
            "Enabled",
            True,
            "Should buddies be queued or added as requested? (Queueing buddies may slow down the bot.)",
        )
        settings.create(
            "Buddy_Queue",
            "Rate",
            1,
            "How many buddy add and removes should be done per second?",
            "1;2;3;4;5;6;7;8;9;10",
        )
        settings.register_callback("Buddy_Queue", "Rate", self)
        self.settings(
            False,
            False,
            False,
            settings.get("Buddy_Queue", "Rate"),
            False,
        )

    def settings(self, user, module, setting, new, old) -> None:
        rate = 1 / new
        max_burst = new * 2
        self.bot.core("queue").register(self, "buddy", rate, max_burst)

    def do_add(self, uid) -> None:
        chat = self.bot.core("chat")
        if uid and uid != 0 and uid != -1:
            if not chat.buddy_exists(uid):
                chat.buddy_add(uid)
                self.bot.log("BUDDY QUEUE", "BUDDY-ADD", self.bot.core("player").name(uid))
        else:
            self.bot.log(
                "BUDDY QUEUE",
                "BUDDY-ERROR",
                f"Tried to add {self.bot.core('player').name(uid)} as a buddy when they already are one.",
            )

    def do_delete(self, uid) -> None:
        if uid and uid != 0 and uid != -1:
            chat = self.bot.core("chat")
            if chat.buddy_exists(uid):
                chat.buddy_remove(uid)
                self.bot.core("online").logoff(self.bot.core("player").name(uid))
                self.bot.log("BUDDY QUEUE", "BUDDY-DEL", self.bot.core("player").name(uid))
            else:
                self.bot.log(
                    "BUDDY QUEUE",
                    "BUDDY-ERROR",
                    f"Tried to remove {self.bot.core('player').name(uid)} as a buddy when they are not one.",
                )

    def queue(self, module, info) -> None:
        uid, add = info
        if add:
            self.do_add(uid)
        else:
            self.do_delete(uid)

    def check_queue(self) -> bool:
        if not self.bot.core("settings").get("Buddy_Queue", "Enabled"):
            return True
        return self.bot.core("queue").check_queue("buddy")

    def into_queue(self, uid, type_) -> None:
        info = [uid, type_]
        return self.bot.core("queue").into_queue("buddy", info)
