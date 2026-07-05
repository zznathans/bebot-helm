"""Tests for main_modules/notify_ui.py (ported from Modules/Notify.php).

See the module docstring for why this is `notify_ui`/`"notify_ui"` rather
than `notify`/`"notify"` -- that name is already owned by
`main_modules/notify.py` (ported from a different PHP file), which this
module depends on via `core("notify")`.
"""
from __future__ import annotations

from bebot.main_modules.notify_ui import NotifyUi
from bebot.main_modules.tools import Tools


class FakeColors:
    def colorize(self, color, text):
        return text


class FakeNotify:
    def __init__(self):
        self.checked: list[str] = []
        self.added: list[tuple] = []
        self.deleted: list[str] = []
        self.cache_cleared = False
        self.cache_updated = False
        self.in_list: set[str] = set()

    def check(self, name):
        self.checked.append(name)
        return name in self.in_list

    def add(self, source, user):
        self.added.append((source, user))
        return f"{user} added to notify list!"

    def delete(self, user):
        self.deleted.append(user)
        return f"{user} removed from notify list!"

    def clear_cache(self):
        self.cache_cleared = True
        return "Removed 0 members from <botname>'s notify cache."

    def update_cache(self):
        self.cache_updated = True

    def list_cache(self):
        return "0 members in <botname>'s notify cache :: blob"


def make_module(bot, notify=None) -> NotifyUi:
    Tools(bot)
    bot.register_module(notify or FakeNotify(), "notify")
    bot.register_module(FakeColors(), "colors")
    return NotifyUi(bot)


# -- construction / registration ------------------------------------------------

def test_registers_as_notify_ui_module(bot):
    module = make_module(bot)
    assert bot.core("notify_ui") is module
    assert bot.core("notify_ui").module_name != "notify"


def test_does_not_collide_with_notify_module_name(bot):
    real_notify = FakeNotify()
    module = make_module(bot, notify=real_notify)
    assert bot.core("notify") is real_notify
    assert bot.core("notify_ui") is module
    assert bot.core("notify") is not module


def test_registers_notify_command_on_all_channels(bot):
    module = make_module(bot)
    for channel in ("tell", "gc", "pgmsg"):
        assert bot.commands[channel]["notify"] is module


# -- on / off ---------------------------------------------------------------------

def test_notify_on_delegates_to_core_notify_add(bot):
    notify = FakeNotify()
    module = make_module(bot, notify=notify)
    result = module.command_handler("Admin", "notify on Bob", "tell")
    assert result == "Bob added to notify list!"
    assert notify.added == [("Admin", "Bob")]


def test_notify_off_delegates_to_core_notify_delete(bot):
    notify = FakeNotify()
    module = make_module(bot, notify=notify)
    result = module.command_handler("Admin", "notify off Bob", "tell")
    assert result == "Bob removed from notify list!"
    assert notify.deleted == ["Bob"]


def test_wrong_order_on_is_reinterpreted(bot):
    notify = FakeNotify()
    module = make_module(bot, notify=notify)
    # "notify Bob on" -- user typed player name before on/off.
    module.command_handler("Admin", "notify Bob on", "tell")
    assert notify.added == [("Admin", "Bob")]


def test_wrong_order_off_is_reinterpreted(bot):
    notify = FakeNotify()
    module = make_module(bot, notify=notify)
    module.command_handler("Admin", "notify Bob off", "tell")
    assert notify.deleted == ["Bob"]


# -- check ------------------------------------------------------------------------

def test_check_in_list(bot):
    notify = FakeNotify()
    notify.in_list.add("Bob")
    module = make_module(bot, notify=notify)
    result = module.command_handler("Admin", "notify check Bob", "tell")
    assert result == "Bob is in notify list."


def test_check_not_in_list(bot):
    notify = FakeNotify()
    module = make_module(bot, notify=notify)
    result = module.command_handler("Admin", "notify check Bob", "tell")
    assert result == "Bob is not in notify list."


# -- cache ------------------------------------------------------------------------

def test_cache_clear(bot):
    notify = FakeNotify()
    module = make_module(bot, notify=notify)
    result = module.command_handler("Admin", "notify cache clear", "tell")
    assert notify.cache_cleared is True
    assert "Removed" in result


def test_cache_update(bot):
    notify = FakeNotify()
    module = make_module(bot, notify=notify)
    result = module.command_handler("Admin", "notify cache update", "tell")
    assert notify.cache_updated is True
    assert result == "Updating notify cache."


def test_cache_default_lists(bot):
    notify = FakeNotify()
    module = make_module(bot, notify=notify)
    result = module.command_handler("Admin", "notify cache", "tell")
    assert "notify cache" in result


# -- count / list -------------------------------------------------------------------

def test_count_reads_from_db(bot, monkeypatch):
    module = make_module(bot)
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [(3,)])
    result = module.command_handler("Admin", "notify count", "tell")
    assert result == "3 player(s) currently in notify list."


def test_list_empty(bot, monkeypatch):
    module = make_module(bot)
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [])
    result = module.command_handler("Admin", "notify", "tell")
    assert result == "Nobody on notify!"


def test_list_categorizes_by_user_level(bot, monkeypatch):
    module = make_module(bot)

    def fake_select(sql, *a, **kw):
        return [("Suzy", 2), ("Guesty", 1), ("Anony", 0)]

    monkeypatch.setattr(bot.db, "select", fake_select)
    result = module.command_handler("Admin", "notify list", "tell")
    assert "3 Characters on notify" in result
    assert "1 Member" in result
    assert "1 Guests" in result
    assert "1 Others" in result


# -- unknown subcommand -------------------------------------------------------------

def test_unknown_subcommand_returns_error(bot):
    module = make_module(bot)
    result = module.command_handler("Admin", "notify bogus", "tell")
    assert "Unknown Sub Command" in result
    assert "bogus" in result


def test_over_subcommand_not_supported(bot):
    """The AOC-only multi-bot-slave overflow relay isn't ported (no
    bot.slave / multi-instance relay in this codebase) -- 'over' now falls
    through to the generic unknown-subcommand branch."""
    module = make_module(bot)
    result = module.command_handler("Admin", "notify over Admin@Bob", "tell")
    assert "Unknown Sub Command" in result
