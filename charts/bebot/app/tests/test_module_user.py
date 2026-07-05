from bebot.commodities.base import BotError
from bebot.main_modules.notify import Notify
from bebot.main_modules.tools import Tools
from bebot.main_modules.user import User
from fakes import FakeSettings


class _FakeSettingsWithCreate(FakeSettings):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.created: list[tuple] = []
        self.deleted: list[tuple] = []
        self._existing: set[tuple] = set()

    def create(self, module, setting, value, longdesc, defaultoptions="", hidden=False, disporder=1):
        self.created.append((module, setting, value, longdesc, defaultoptions))
        self._values.setdefault((module, setting), value)

    def exists(self, module, setting) -> bool:
        return (module, setting) in self._existing

    def del_setting(self, module, setting=None):
        self.deleted.append((module, setting))


class FakePlayer:
    """id() returns int for known names, BotError for unknown ones."""

    def __init__(self, ids: dict[str, int] | None = None):
        self._ids = dict(ids or {})

    def id(self, name):
        if name in self._ids:
            return self._ids[name]
        return BotError(None, "player")


class FakeChat:
    def __init__(self, buddies: set[int] | None = None):
        self.buddies = set(buddies or set())
        self.added: list[int] = []
        self.removed: list[int] = []

    def buddy_exists(self, uid) -> bool:
        return uid in self.buddies

    def buddy_add(self, uid) -> None:
        self.added.append(uid)
        self.buddies.add(uid)

    def buddy_remove(self, uid) -> None:
        self.removed.append(uid)
        self.buddies.discard(uid)


class FakeOnline:
    def __init__(self):
        self.logoffs: list[str] = []

    def logoff(self, name) -> None:
        self.logoffs.append(name)


class FakeNotify:
    def __init__(self):
        self.update_cache_calls = 0

    def update_cache(self) -> None:
        self.update_cache_calls += 1


def make_user(bot, monkeypatch, ids=None, rows_by_query=None, guildbot=None) -> User:
    Tools(bot)
    bot.register_module(_FakeSettingsWithCreate({
        ("Members", "Mark_notify"): False,
        ("Members", "Notify_level"): 2,
    }), "settings")
    bot.register_module(FakePlayer(ids or {}), "player")
    bot.register_module(FakeChat(), "chat")
    bot.register_module(FakeOnline(), "online")
    bot.register_module(FakeNotify(), "notify")

    rows_by_query = rows_by_query or {}

    def fake_select(sql, *a, **kw):
        for needle, rows in rows_by_query.items():
            if needle in sql:
                return rows
        return []

    monkeypatch.setattr(bot.db, "select", fake_select)
    if guildbot is not None:
        bot.guildbot = guildbot
    return User(bot)


# -- construction -------------------------------------------------------------

def test_registers_as_user_module(bot, monkeypatch):
    module = make_user(bot, monkeypatch)
    assert bot.core("user") is module


def test_creates_default_settings(bot, monkeypatch):
    module = make_user(bot, monkeypatch)
    settings = bot.core("settings")
    names = [c[1] for c in settings.created]
    assert "Mark_notify" in names
    assert "Notify_level" in names
    assert "AutoInviteGroup" in names


def test_removes_outdated_autoinvite_setting_if_present(bot, monkeypatch):
    settings = _FakeSettingsWithCreate()
    settings._existing.add(("Members", "AutoInvite"))
    Tools(bot)
    bot.register_module(settings, "settings")
    bot.register_module(FakePlayer(), "player")
    bot.register_module(FakeChat(), "chat")
    bot.register_module(FakeOnline(), "online")
    bot.register_module(FakeNotify(), "notify")
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [])
    User(bot)
    assert ("Members", "AutoInvite") in settings.deleted


def test_does_not_remove_autoinvite_setting_if_absent(bot, monkeypatch):
    module = make_user(bot, monkeypatch)
    settings = bot.core("settings")
    assert settings.deleted == []


# -- add ----------------------------------------------------------------------

def test_add_empty_name_returns_error(bot, monkeypatch):
    module = make_user(bot, monkeypatch)
    result = module.add("Source", "")
    assert isinstance(result, BotError)
    assert "have to give a character" in result.get()


def test_add_invalid_character_returns_error(bot, monkeypatch):
    module = make_user(bot, monkeypatch, ids={})
    result = module.add("Source", "Nobody")
    assert isinstance(result, BotError)
    assert "not a valid character" in result.get()


def test_add_new_user_inserts_and_returns_success(bot, monkeypatch):
    module = make_user(bot, monkeypatch, ids={"Newguy": 123})
    result = module.add("Admin", "newguy", user_level=2)
    assert result == "Player ##highlight##Newguy##end## has been added to the bot as a member"
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___users")]
    assert len(insert_queries) == 1
    assert "'123'" in insert_queries[0]
    assert "'Newguy'" in insert_queries[0]


def test_add_already_member_returns_error(bot, monkeypatch):
    module = make_user(
        bot,
        monkeypatch,
        ids={"Existing": 5},
        rows_by_query={"WHERE char_id = '5'": [("Existing", 2)]},
    )
    result = module.add("Admin", "existing", user_level=0)
    assert isinstance(result, BotError)
    assert "already a member" in result.get()


def test_add_banned_returns_error(bot, monkeypatch):
    module = make_user(
        bot,
        monkeypatch,
        ids={"Banned": 5},
        rows_by_query={"WHERE char_id = '5'": [("Banned", -1)]},
        guildbot=False,
    )
    result = module.add("Admin", "banned", user_level=0)
    assert isinstance(result, BotError)
    assert "already a member" in result.get()


def test_add_change_level_updates_existing_row(bot, monkeypatch):
    module = make_user(
        bot,
        monkeypatch,
        ids={"Existing": 5},
        rows_by_query={"WHERE char_id = '5'": [("Existing", 1)]},
    )
    result = module.add("Admin", "existing", user_level=2)
    assert "has been added to the bot as a member" in result
    update_queries = [q for q in bot.db.queries if q.startswith("UPDATE #___users SET user_level")]
    assert len(update_queries) == 1


def test_add_negative_level_with_no_existing_user_returns_error(bot, monkeypatch):
    module = make_user(bot, monkeypatch, ids={"Newguy": 123})
    result = module.add("Admin", "newguy", user_level=-1)
    assert isinstance(result, BotError)
    assert "not a valid access level" in result.get()


def test_add_marks_notify_and_adds_buddy_when_settings_say_so(bot, monkeypatch):
    module = make_user(bot, monkeypatch, ids={"Newguy": 123})
    bot.core("settings").set("Members", "Mark_notify", True)
    bot.core("settings").set("Members", "Notify_level", 2)
    module.add("Admin", "newguy", user_level=2)
    chat = bot.core("chat")
    notify = bot.core("notify")
    assert 123 in chat.added
    assert notify.update_cache_calls == 1


def test_add_does_not_notify_when_already_buddy(bot, monkeypatch):
    module = make_user(bot, monkeypatch, ids={"Newguy": 123})
    bot.core("chat").buddies.add(123)
    bot.core("settings").set("Members", "Mark_notify", True)
    bot.core("settings").set("Members", "Notify_level", 2)
    module.add("Admin", "newguy", user_level=2)
    assert bot.core("chat").added == []


def test_add_sends_tell_unless_silent(bot, monkeypatch):
    module = make_user(bot, monkeypatch, ids={"Newguy": 123})
    sent = []
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))
    module.add("Admin", "newguy", user_level=2, silent=0)
    assert sent
    sent.clear()
    module.add("Admin", "newguy2", user_level=2, silent=1)


def test_add_silent_suppresses_tell(bot, monkeypatch):
    module = make_user(bot, monkeypatch, ids={"Newguy": 123})
    sent = []
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))
    module.add("Admin", "newguy", user_level=2, silent=1)
    assert sent == []


# -- delete ---------------------------------------------------------------------

def test_delete_empty_name_returns_error(bot, monkeypatch):
    module = make_user(bot, monkeypatch)
    result = module.delete("Admin", "")
    assert isinstance(result, BotError)


def test_delete_unknown_user_returns_error(bot, monkeypatch):
    module = make_user(bot, monkeypatch, rows_by_query={})
    result = module.delete("Admin", "Ghost")
    assert isinstance(result, BotError)
    assert "not in the user table" in result.get()


def test_delete_non_member_returns_error(bot, monkeypatch):
    module = make_user(
        bot, monkeypatch, rows_by_query={"WHERE nickname = 'Guy'": [(5, "Guy", 0)]}
    )
    result = module.delete("Admin", "Guy")
    assert isinstance(result, BotError)
    assert "is not a member" in result.get()


def test_delete_banned_returns_error(bot, monkeypatch):
    module = make_user(
        bot, monkeypatch, rows_by_query={"WHERE nickname = 'Guy'": [(5, "Guy", -1)]}
    )
    result = module.delete("Admin", "Guy")
    assert isinstance(result, BotError)
    assert "banned" in result.get()


def test_delete_success_removes_buddy_and_updates_caches(bot, monkeypatch):
    module = make_user(
        bot,
        monkeypatch,
        ids={"Guy": 5},
        rows_by_query={"WHERE nickname = 'Guy'": [(5, "Guy", 2)]},
    )
    result = module.delete("Admin", "Guy")
    assert "has been removed from member list" in result
    assert 5 in bot.core("chat").removed
    assert "Guy" in bot.core("online").logoffs
    assert bot.core("notify").update_cache_calls == 1


def test_delete_reroll_updates_char_id_instead_of_removing_buddy(bot, monkeypatch):
    module = make_user(
        bot,
        monkeypatch,
        ids={"Guy": 99},
        rows_by_query={"WHERE nickname = 'Guy'": [(5, "Guy", 2)]},
    )
    result = module.delete("Admin", "Guy", id=5)
    assert "has been removed from member list" in result
    # reroll path does not call buddy_remove
    assert bot.core("chat").removed == []
    # Faithful port of a PHP quirk: the reroll UPDATE writes back the
    # *passed-in* id (5), not the newly looked-up id (99).
    reroll_updates = [q for q in bot.db.queries if "char_id = '5'" in q and "UPDATE" in q]
    assert reroll_updates


def test_delete_player_lookup_failure_still_falls_through_normally(bot, monkeypatch):
    """Faithful-port quirk (see user.py docstring): core("player").id() returning
    a BotError is truthy in both PHP and Python, so a lookup failure takes the
    "sane id" branch rather than the "invalid character" branch -- delete()
    proceeds normally using the id already on file in #___users.
    """
    module = make_user(
        bot,
        monkeypatch,
        ids={},  # player.id("Guy") -> BotError, which is still truthy
        rows_by_query={"WHERE nickname = 'Guy'": [(5, "Guy", 2)]},
    )
    result = module.delete("Admin", "Guy")
    assert "has been removed from member list" in result
    assert 5 in bot.core("chat").removed


def test_delete_id_literally_falsy_takes_the_erase_branch(bot, monkeypatch):
    """If core("player").id() ever did return a literal falsy value (as
    opposed to a truthy BotError) -- which the current Player port never
    does, but the PHP `else` branch was clearly written to handle -- delete()
    erases the row instead of updating it, matching the PHP `else` branch."""
    module = make_user(
        bot,
        monkeypatch,
        ids={"Guy": 0},
        rows_by_query={"WHERE nickname = 'Guy'": [(5, "Guy", 2)]},
    )
    result = module.delete("Admin", "Guy")
    assert isinstance(result, BotError)
    assert "does not appear to be a valid character" in result.get()
    erase_queries = [q for q in bot.db.queries if q.startswith("DELETE FROM #___users WHERE nickname")]
    assert erase_queries


# -- erase ----------------------------------------------------------------------

def test_erase_empty_name_returns_error(bot, monkeypatch):
    module = make_user(bot, monkeypatch)
    result = module.erase("Admin", "")
    assert isinstance(result, BotError)


def test_erase_unknown_user_returns_error(bot, monkeypatch):
    module = make_user(bot, monkeypatch)
    result = module.erase("Admin", "Ghost")
    assert isinstance(result, BotError)
    assert "not in the user table" in result.get()


def test_erase_success_deletes_row_and_updates_caches(bot, monkeypatch):
    module = make_user(
        bot,
        monkeypatch,
        ids={"Guy": 5},
        rows_by_query={"WHERE nickname = 'Guy'": [(5, "Guy", 2)]},
    )
    result = module.erase("Admin", "Guy")
    assert "has been erased from member list" in result
    delete_queries = [q for q in bot.db.queries if q.startswith("DELETE FROM #___users WHERE char_id")]
    assert delete_queries
    assert 5 in bot.core("chat").removed
    assert "Guy" in bot.core("online").logoffs
    assert bot.core("notify").update_cache_calls == 1


def test_erase_player_lookup_failure_still_falls_through_normally(bot, monkeypatch):
    """Same BotError-is-truthy quirk as delete() (see user.py docstring): a
    lookup failure does not divert erase() into the "deleted" branch."""
    module = make_user(
        bot,
        monkeypatch,
        ids={},  # player.id("Guy") -> BotError, which is still truthy
        rows_by_query={"WHERE nickname = 'Guy'": [(5, "Guy", 2)]},
    )
    result = module.erase("Admin", "Guy")
    assert "has been erased from member list" in result
    assert 5 in bot.core("chat").removed


def test_erase_id_literally_falsy_deletes_by_nickname(bot, monkeypatch):
    module = make_user(
        bot,
        monkeypatch,
        ids={"Guy": 0},
        rows_by_query={"WHERE nickname = 'Guy'": [(5, "Guy", 2)]},
    )
    result = module.erase("Admin", "Guy")
    assert "has been erased from member list" in result
    delete_queries = [q for q in bot.db.queries if "DELETE FROM #___users WHERE nickname" in q]
    assert delete_queries
    # deleted-character path does not touch the buddy list
    assert bot.core("chat").removed == []


def test_erase_sends_tell_unless_silent(bot, monkeypatch):
    module = make_user(
        bot,
        monkeypatch,
        ids={"Guy": 5},
        rows_by_query={"WHERE nickname = 'Guy'": [(5, "Guy", 2)]},
    )
    sent = []
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))
    module.erase("Admin", "Guy", silent=0)
    assert sent


# -- misc helpers -----------------------------------------------------------

def test_access_name(bot, monkeypatch):
    module = make_user(bot, monkeypatch)
    assert module.access_name(1) == "a guest"
    assert module.access_name(2) == "a member"
    assert module.access_name(3) == "an admin"
    assert module.access_name(99) == "Error, unknown level"


def test_admin_group_name(bot, monkeypatch):
    module = make_user(bot, monkeypatch)
    assert module.admin_group_name(4) == "owner"
    assert module.admin_group_name(3) == "superadmin"
    assert module.admin_group_name(2) == "admin"
    assert module.admin_group_name(1) == "raidleader"
    assert module.admin_group_name(0) is None


def test_admin_group_level(bot, monkeypatch):
    module = make_user(bot, monkeypatch)
    assert module.admin_group_level("owner") == 4
    assert module.admin_group_level("superadmin") == 3
    assert module.admin_group_level("admin") == 2
    assert module.admin_group_level("raidleader") == 1
    assert module.admin_group_level("nonsense") == 0


def test_get_db_uid_found_and_missing(bot, monkeypatch):
    module = make_user(
        bot, monkeypatch, rows_by_query={"WHERE nickname = 'Guy'": [(7,)]}
    )
    assert module.get_db_uid("Guy") == 7
    assert module.get_db_uid("Ghost") == 0


# -- integration: real User + real Notify -----------------------------------

def test_integration_notify_add_creates_user_via_real_user_module(bot, monkeypatch):
    Tools(bot)
    bot.register_module(_FakeSettingsWithCreate({
        ("Members", "Mark_notify"): False,
        ("Members", "Notify_level"): 2,
    }), "settings")
    bot.register_module(FakePlayer({"Newguy": 42}), "player")
    chat = FakeChat()
    bot.register_module(chat, "chat")
    bot.register_module(FakeOnline(), "online")

    rows_by_query = {"WHERE notify = 1": []}

    def fake_select(sql, *a, **kw):
        for needle, rows in rows_by_query.items():
            if needle in sql:
                return rows
        return []

    monkeypatch.setattr(bot.db, "select", fake_select)

    user = User(bot)
    notify = Notify(bot)

    result = notify.add("Admin", "newguy")
    assert result == "Newguy added to notify list!"
    # Notify.add() called back into the real User.add() for the unknown name.
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___users")]
    assert insert_queries
    assert 42 in chat.added
    assert notify.check("newguy") is True
