"""Ported from Main/15_ChatQueue.php -- anti-flood outgoing tell/gc queue,
built on top of Queue."""
from __future__ import annotations

from ..bot import _fire_and_forget
from ..commodities.base import BasePassiveModule


class ChatQueue(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("chat_queue")
        bot.core("queue").register(self, "chat", bot.telldelay / 1000, 4)

    def queue(self, name, info) -> None:
        to, msg, kind = info
        if kind == "tell":
            to_name = self.bot.core("chat").get_uname(to)
            self.bot.log("TELL", "OUT", f"-> {to_name}: {msg}")
            _fire_and_forget(self.bot.aoc.send_tell(to, msg))
        else:
            _fire_and_forget(self.bot.aoc.send_group(to, msg))

    def check_queue(self) -> bool:
        return self.bot.core("queue").check_queue("chat")

    def into_queue(self, to, msg, kind, priority) -> None:
        self.bot.core("queue").into_queue("chat", [to, msg, kind], priority)
