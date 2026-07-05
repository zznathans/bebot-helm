from bebot.commodities.base import BotError
from bebot.main_modules.notify import Notify
from bebot.main_modules.tools import Tools
from bebot.main_modules.user import User
from fakes import FakeSettings


class FakePlayer:
    def __init__(self, ids: dict[str, int] | None = None):
        self._ids = dict(ids or {})

    def id(self, name):
        if name in self._ids:
            return self._ids[name]
        return BotError(None, "player")


class FakeChat:
    def __init__(self):
        self.added: list[int] = []
        self.removed: list[int] = []

    def buddy_add(self, uid) -> None:
        self.added.append(uid)

    def buddy_remove(self, uid) -> None:
        self.removed.append(uid)


class RecordingUser:
    """Fake for core("user") used to isolate Notify tests from real User."""

    def __init__(self):
        self.add_calls: list[tuple] = []

    def add(self, source, user, id=0, user_level=0, silent=0):
        self.add_calls.append((source, user, id, user_level, silent))


def make_notify(bot, monkeypatch, ids=None, notify_rows=None, users_rows=None) -> Notify:
    Tools(bot)
    bot.register_module(FakePlayer(ids or {}), "player")
    bot.register_module(FakeChat(), "chat")
    bot.register_module(RecordingUser(), "user")

    notify_rows = notify_rows if notify_rows is not None else []
    users_rows = users_rows or {}

    def fake_select(sql, *a, **kw):
        if "WHERE notify = 1" in sql:
            return notify_rows
        for needle, rows in users_rows.items():
            if needle in sql:
                return rows
        return []

    monkeypatch.setattr(bot.db, "select", fake_select)
    return Notify(bot)


# -- construction / update_cache ----------------------------------------------

def test_registers_as_notify_module(bot, monkeypatch):
    module = make_notify(bot, monkeypatch)
    assert bot.core("notify") is module


def test_construction_populates_cache_from_db(bot, monkeypatch):
    module = make_notify(bot, monkeypatch, notify_rows=[("Alice",), ("bob",)])
    assert module.check("Alice") is True
    assert module.check("BOB") is True
    assert module.check("charlie") is False


def test_update_cache_rebuilds_from_db(bot, monkeypatch):
    module = make_notify(bot, monkeypatch, notify_rows=[("Alice",)])
    assert module.check("Alice") is True
    module.cache = {}  # simulate staleness
    module.update_cache()
    assert module.check("Alice") is True


def test_update_cache_replaces_rather_than_merges(bot, monkeypatch):
    module = make_notify(bot, monkeypatch, notify_rows=[("Alice",)])
    module.cache["Extra"] = True
    module.update_cache()
    assert "Extra" not in module.cache


# -- check ----------------------------------------------------------------------

def test_check_normalizes_case(bot, monkeypatch):
    module = make_notify(bot, monkeypatch, notify_rows=[("alice",)])
    assert module.check("ALICE") is True
    assert module.check("alice") is True
    assert module.check("Alice") is True


def test_check_unknown_name_false(bot, monkeypatch):
    module = make_notify(bot, monkeypatch)
    assert module.check("Nobody") is False


# -- add ----------------------------------------------------------------------

def test_add_invalid_character_returns_error(bot, monkeypatch):
    module = make_notify(bot, monkeypatch, ids={})
    result = module.add("Admin", "Ghost")
    assert isinstance(result, BotError)
    assert "no valid character" in result.get()


def test_add_unknown_user_calls_core_user_add_then_marks_notify(bot, monkeypatch):
    module = make_notify(bot, monkeypatch, ids={"Newguy": 42}, users_rows={"WHERE nickname = 'Newguy'": []})
    result = module.add("Admin", "newguy")
    assert result == "Newguy added to notify list!"
    fake_user = bot.core("user")
    assert fake_user.add_calls == [("Admin", "Newguy", 0, 0, 1)]
    assert module.check("Newguy") is True
    assert 42 in bot.core("chat").added
    update_queries = [q for q in bot.db.queries if q.startswith("UPDATE #___users SET notify = 1")]
    assert update_queries


def test_add_already_on_notify_returns_error(bot, monkeypatch):
    module = make_notify(
        bot, monkeypatch, ids={"Existing": 5}, users_rows={"WHERE nickname = 'Existing'": [(1,)]}
    )
    result = module.add("Admin", "existing")
    assert isinstance(result, BotError)
    assert "already on the notify list" in result.get()


def test_add_existing_user_not_on_notify_marks_notify(bot, monkeypatch):
    module = make_notify(
        bot, monkeypatch, ids={"Existing": 5}, users_rows={"WHERE nickname = 'Existing'": [(0,)]}
    )
    result = module.add("Admin", "existing")
    assert result == "Existing added to notify list!"
    fake_user = bot.core("user")
    assert fake_user.add_calls == []  # already in users table -- User.add() not invoked
    assert module.check("Existing") is True
    assert 5 in bot.core("chat").added


# -- delete ---------------------------------------------------------------------

def test_delete_invalid_character_returns_error(bot, monkeypatch):
    module = make_notify(bot, monkeypatch, ids={})
    result = module.delete("Ghost")
    assert isinstance(result, BotError)
    assert "no valid character" in result.get()


def test_delete_zero_id_returns_error(bot, monkeypatch):
    module = make_notify(bot, monkeypatch, ids={"Zero": 0})
    result = module.delete("Zero")
    assert isinstance(result, BotError)
    assert "no valid character" in result.get()


def test_delete_not_in_users_table_returns_error(bot, monkeypatch):
    module = make_notify(bot, monkeypatch, ids={"Guy": 5}, users_rows={"WHERE nickname = 'Guy'": []})
    result = module.delete("Guy")
    assert isinstance(result, BotError)
    assert "not on notify list" in result.get()


def test_delete_not_on_notify_returns_error(bot, monkeypatch):
    module = make_notify(bot, monkeypatch, ids={"Guy": 5}, users_rows={"WHERE nickname = 'Guy'": [(0,)]})
    result = module.delete("Guy")
    assert isinstance(result, BotError)
    assert "not on notify list" in result.get()


def test_delete_success_removes_from_cache_and_buddy_list(bot, monkeypatch):
    module = make_notify(
        bot,
        monkeypatch,
        ids={"Guy": 5},
        notify_rows=[("Guy",)],
        users_rows={"WHERE nickname = 'Guy'": [(1,)]},
    )
    assert module.check("Guy") is True
    result = module.delete("Guy")
    assert result == "Guy removed from notify list!"
    assert module.check("Guy") is False
    assert 5 in bot.core("chat").removed
    online_updates = [q for q in bot.db.queries if q.startswith("UPDATE #___online")]
    assert online_updates


# -- list_cache / clear_cache / get_all ----------------------------------------

def test_list_cache_reports_count_and_uses_make_blob(bot, monkeypatch):
    module = make_notify(
        bot, monkeypatch, notify_rows=[("Alice",)], users_rows={"WHERE nickname = 'Alice'": [(1,)]}
    )
    result = module.list_cache()
    assert result.startswith("1 members in <botname>'s notify cache")
    assert "Alice" in result


def test_list_cache_flags_mismatch_between_cache_and_db(bot, monkeypatch):
    module = make_notify(
        bot, monkeypatch, notify_rows=[("Alice",)], users_rows={"WHERE nickname = 'Alice'": [(0,)]}
    )
    result = module.list_cache()
    assert "MISMATCH" in result


def test_clear_cache_empties_cache_and_reports_count(bot, monkeypatch):
    module = make_notify(bot, monkeypatch, notify_rows=[("Alice",), ("Bob",)])
    result = module.clear_cache()
    assert result == "Removed 2 members from <botname>'s notify cache."
    assert module.get_all() == {}


def test_get_all_returns_cache(bot, monkeypatch):
    module = make_notify(bot, monkeypatch, notify_rows=[("Alice",)])
    assert module.get_all() == {"Alice": True}


# -- integration: real User + real Notify ------------------------------------

class _FakeChatWithExists(FakeChat):
    def buddy_exists(self, uid):
        return uid in self.added


class _FakeOnline:
    def logoff(self, name):
        pass


def _register_common_fakes(bot, mark_notify: bool):
    Tools(bot)
    settings = FakeSettings({("Members", "Mark_notify"): mark_notify, ("Members", "Notify_level"): 2})
    settings.create = lambda *a, **kw: None
    settings.exists = lambda module, setting: False
    settings.del_setting = lambda module, setting=None: None
    bot.register_module(settings, "settings")
    bot.register_module(_FakeOnline(), "online")
    chat = _FakeChatWithExists()
    bot.register_module(chat, "chat")
    return chat


def test_integration_user_add_updates_real_notify_cache(bot, monkeypatch):
    chat = _register_common_fakes(bot, mark_notify=True)
    bot.register_module(FakePlayer({"Newguy": 42}), "player")

    notified: set[str] = set()

    def fake_select(sql, *a, **kw):
        if "WHERE notify = 1" in sql:
            return [(name,) for name in sorted(notified)]
        return []

    def fake_query(sql, *a, **kw):
        bot.db.queries.append(sql)
        if "INSERT INTO #___users" in sql and "'Newguy'" in sql:
            notified.add("Newguy")
        return True

    monkeypatch.setattr(bot.db, "select", fake_select)
    monkeypatch.setattr(bot.db, "query", fake_query)

    user = User(bot)
    notify = Notify(bot)  # Notify.__init__ registers itself as core("notify")

    result = user.add("Admin", "newguy", user_level=2)
    assert "has been added to the bot" in result
    # Mark_notify + Notify_level satisfied -> User.add() called notify.update_cache()
    # and chat.buddy_add() directly (buddy wasn't already on the list).
    assert 42 in chat.added
    assert notify.check("Newguy") is True


def test_integration_notify_check_reflects_user_delete(bot, monkeypatch):
    _register_common_fakes(bot, mark_notify=True)
    bot.register_module(FakePlayer({"Guy": 5}), "player")

    notified = {"Guy"}
    users_row = [(5, "Guy", 2)]

    def fake_select(sql, *a, **kw):
        if "WHERE notify = 1" in sql:
            return [(name,) for name in sorted(notified)]
        if "WHERE nickname = 'Guy'" in sql:
            return users_row
        return []

    def fake_query(sql, *a, **kw):
        bot.db.queries.append(sql)
        if "char_id = '5'" in sql and "notify = '0'" in sql:
            notified.discard("Guy")
        return True

    monkeypatch.setattr(bot.db, "select", fake_select)
    monkeypatch.setattr(bot.db, "query", fake_query)

    user = User(bot)
    notify = Notify(bot)

    assert notify.check("Guy") is True
    user.delete("Admin", "Guy")
    assert notify.get_all() == {}  # update_cache() re-read the table and found notify cleared
