"""Ported from Main/14_Queue.php: a generic leaky-bucket rate limiter used
by ChatQueue (and available for any other module that wants throttled
delivery)."""
from __future__ import annotations

import time

from ..commodities.base import BasePassiveModule


class Queue(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("queue")
        self.register_event("cron", "1sec")
        self.queue: dict[str, list] = {}
        self.queue_low: dict[str, list] = {}
        self.link: dict[str, object] = {}
        self.delay: dict[str, float] = {}
        self.max: dict[str, float] = {}
        self.left: dict[str, float] = {}
        self.last_call: dict[str, float] = {}
        self.filter = True

    def register(self, module, name: str, delay: float, max_burst: float = 0, filter_dupes: bool = True) -> None:
        name = name.lower()
        self.link[name] = module
        self.delay[name] = delay
        self.max[name] = max_burst
        self.filter = bool(filter_dupes)

    def cron(self, duration=None) -> None:
        for name, module in list(self.link.items()):
            if self.queue.get(name):
                self._replenish(name)
                for item in list(self.queue[name]):
                    if self.left.get(name, 0) >= 1:
                        module.queue(name, item)
                        self.queue[name].remove(item)
                        self.left[name] -= 1
            if self.queue_low.get(name) and not self.queue.get(name):
                self._replenish(name)
                for item in list(self.queue_low[name]):
                    if self.left.get(name, 0) >= 1:
                        module.queue(name, item)
                        self.queue_low[name].remove(item)
                        self.left[name] -= 1

    def _replenish(self, name: str) -> None:
        now = time.time()
        last = self.last_call.get(name, 0)
        add = (now - last) / self.delay[name] if self.delay.get(name, 0) > 0 else 0
        if add > 0:
            self.left[name] = self.left.get(name, 0) + add
            self.last_call[name] = now
            if self.max.get(name) and self.left[name] > self.max[name]:
                self.left[name] = self.max[name]

    def check_queue(self, name: str) -> bool:
        name = name.lower()
        self._replenish(name)
        if self.left.get(name, 0) >= 1 and not self.queue.get(name) and not self.queue_low.get(name):
            self.left[name] -= 1
            return True
        return False

    def into_queue(self, name: str, info, priority: int = 0) -> None:
        name = name.lower()
        bucket = self.queue if priority == 0 else self.queue_low
        if self.filter:
            for item in bucket.get(name, []):
                if self.bot.core("tools").compare(info, item):
                    return
        bucket.setdefault(name, []).append(info)
