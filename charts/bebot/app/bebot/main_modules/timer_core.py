"""Ported (heavily reduced) from Main/15_TimerCore.php.

The original is a full DB-backed timer system with named "timer classes"
and an in-game UI for creating/chaining recurring events (Modules/Countdown,
Rally, etc. build on it). None of that admin/UI layer is ported. What's
kept is the actual contract Bot.cron() depends on: `check_timers()` must
exist and not error, and modules must be able to register a named
callback via `register_event("timer", name)` -> `register_callback`.
Timers registered this way are in-memory only (not persisted across
restarts).
"""
from __future__ import annotations

import time

from ..commodities.base import BasePassiveModule


class TimerCore(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("timer")
        self._callbacks: dict[str, object] = {}
        self._timers: list[dict] = []  # {"id", "due", "owner", "data"}
        self._next_id = 1

    def register_callback(self, name: str, module) -> None:
        self._callbacks[name] = module

    def unregister_callback(self, name: str):
        self._callbacks.pop(name, False)
        return False

    def add_timer(self, owner: str, seconds: float, data=None) -> int:
        timer_id = self._next_id
        self._next_id += 1
        self._timers.append({"id": timer_id, "due": time.time() + seconds, "owner": owner, "data": data})
        return timer_id

    def del_timer(self, timer_id: int) -> bool:
        before = len(self._timers)
        self._timers = [t for t in self._timers if t["id"] != timer_id]
        return len(self._timers) != before

    def check_timers(self) -> None:
        if not self._timers:
            return
        now = time.time()
        due = [t for t in self._timers if t["due"] <= now]
        if not due:
            return
        self._timers = [t for t in self._timers if t["due"] > now]
        for timer in due:
            callback = self._callbacks.get(timer["owner"])
            if callback is not None and hasattr(callback, "timed_event"):
                callback.timed_event(timer["id"], timer["data"])
