"""Tests for main_modules/buddy_queue.py (ported from Core/BuddyQueue.php)."""
from __future__ import annotations

from bebot.main_modules.buddy_queue import BuddyQueue
from bebot.main_modules.queue import Queue
from bebot.main_modules.settings import Settings

from tests.fakes import FakePlayer


class FakeChat:
    def __init__(self, existing=None):
        self.existing = set(existing or [])
        self.added: list = []
        self.removed: list = []

    def buddy_exists(self, uid) -> bool:
        return uid in self.existing

    def buddy_add(self, uid) -> None:
        self.added.append(uid)
        self.existing.add(uid)

    def buddy_remove(self, uid) -> None:
        self.removed.append(uid)
        self.existing.discard(uid)


class FakeOnline:
    def __init__(self):
        self.logoffs: list = []

    def logoff(self, name) -> None:
        self.logoffs.append(name)


def make_buddy_queue(bot, chat=None, online=None, player=None) -> BuddyQueue:
    bot.register_module(Settings(bot), "settings")
    bot.register_module(Queue(bot), "queue")
    bot.register_module(chat or FakeChat(), "chat")
    bot.register_module(online or FakeOnline(), "online")
    bot.register_module(player or FakePlayer(), "player")
    return BuddyQueue(bot)


# -- construction / settings wiring -------------------------------------------

def test_registers_as_buddy_queue_module(bot):
    module = make_buddy_queue(bot)
    assert bot.core("buddy_queue") is module


def test_registers_with_queue_at_default_rate(bot):
    module = make_buddy_queue(bot)
    queue = bot.core("queue")
    assert queue.link["buddy"] is module
    assert queue.delay["buddy"] == 1  # 1 / rate(1)
    assert queue.max["buddy"] == 2  # rate(1) * 2


def test_settings_callback_updates_queue_rate(bot):
    module = make_buddy_queue(bot)
    queue = bot.core("queue")
    module.settings("", "buddy_queue", "rate", 5, 1)
    assert queue.delay["buddy"] == 1 / 5
    assert queue.max["buddy"] == 10


# -- do_add ---------------------------------------------------------------------

def test_do_add_adds_buddy_that_does_not_exist(bot):
    chat = FakeChat()
    module = make_buddy_queue(bot, chat=chat)
    module.do_add(123)
    assert chat.added == [123]
    assert 123 in chat.existing


def test_do_add_skips_buddy_that_already_exists(bot):
    chat = FakeChat(existing={123})
    module = make_buddy_queue(bot, chat=chat)
    module.do_add(123)
    assert chat.added == []


def test_do_add_ignores_invalid_uid(bot):
    chat = FakeChat()
    module = make_buddy_queue(bot, chat=chat)
    module.do_add(0)
    module.do_add(-1)
    module.do_add(None)
    assert chat.added == []


# -- do_delete --------------------------------------------------------------------

def test_do_delete_removes_existing_buddy_and_logs_offline(bot):
    chat = FakeChat(existing={123})
    online = FakeOnline()
    player = FakePlayer(names={123: "Someuser"})
    module = make_buddy_queue(bot, chat=chat, online=online, player=player)
    module.do_delete(123)
    assert chat.removed == [123]
    assert 123 not in chat.existing
    assert online.logoffs == ["Someuser"]


def test_do_delete_skips_buddy_that_does_not_exist(bot):
    chat = FakeChat()
    online = FakeOnline()
    module = make_buddy_queue(bot, chat=chat, online=online)
    module.do_delete(123)
    assert chat.removed == []
    assert online.logoffs == []


def test_do_delete_ignores_invalid_uid(bot):
    chat = FakeChat()
    module = make_buddy_queue(bot, chat=chat)
    module.do_delete(0)
    module.do_delete(-1)
    assert chat.removed == []


# -- queue() dispatch -------------------------------------------------------------

def test_queue_dispatches_to_do_add_when_type_true(bot):
    chat = FakeChat()
    module = make_buddy_queue(bot, chat=chat)
    module.queue("buddy", [123, True])
    assert chat.added == [123]


def test_queue_dispatches_to_do_delete_when_type_false(bot):
    chat = FakeChat(existing={123})
    module = make_buddy_queue(bot, chat=chat)
    module.queue("buddy", [123, False])
    assert chat.removed == [123]


# -- check_queue / into_queue -----------------------------------------------------

def test_check_queue_true_when_buddy_queue_disabled(bot):
    module = make_buddy_queue(bot)
    bot.core("settings").save("Buddy_Queue", "Enabled", False)
    assert module.check_queue() is True


def test_check_queue_exhausts_burst_allowance_then_denies(bot):
    module = make_buddy_queue(bot)
    assert bot.core("settings").get("Buddy_Queue", "Enabled") is True
    # Default rate (1/sec) registers a burst allowance (max == 2 == rate * 2).
    # Called back-to-back (~0 elapsed real time), the first two calls consume
    # that burst and the third is denied until the bucket refills.
    assert module.check_queue() is True
    assert module.check_queue() is True
    assert module.check_queue() is False


def test_into_queue_enqueues_uid_and_type(bot):
    module = make_buddy_queue(bot)
    queue = bot.core("queue")
    module.into_queue(123, True)
    assert queue.queue["buddy"] == [[123, True]]


def test_into_queue_then_cron_drains_via_do_add(bot):
    chat = FakeChat()
    module = make_buddy_queue(bot, chat=chat)
    queue = bot.core("queue")
    module.into_queue(123, True)
    assert chat.added == []  # not yet dispatched, still queued
    queue.cron()
    assert chat.added == [123]
    assert queue.queue.get("buddy") == []
