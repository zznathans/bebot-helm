from bebot.commodities.base import BotError
from bebot.main_modules.auto_user_add import AutoUserAdd
from bebot.main_modules.tools import Tools
from bebot.main_modules.user import User
from fakes import FakeSettings, RecordingModule


class _FakeSettingsWithCreate(FakeSettings):
    """FakeSettings doesn't implement create()/exists()/del_setting() -- both
    AutoUserAdd.__init__ and User.__init__ need create(), and User also needs
    exists()/del_setting() for its outdated-AutoInvite-setting cleanup.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.created: list[tuple] = []

    def create(self, module, setting, value, longdesc, defaultoptions="", hidden=False, disporder=1):
        self.created.append((module, setting, value, longdesc))
        self._values.setdefault((module, setting), value)

    def exists(self, module, setting) -> bool:
        return False

    def del_setting(self, module, setting=None):
        pass


class FakePlayer:
    """id() returns int for known names, BotError for unknown ones -- matches
    the real Player module's contract that main_modules/user.py relies on.
    """

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

    def buddy_exists(self, uid) -> bool:
        return uid in self.buddies

    def buddy_add(self, uid) -> None:
        self.added.append(uid)
        self.buddies.add(uid)

    def buddy_remove(self, uid) -> None:
        self.buddies.discard(uid)


class FakeOnline:
    def logoff(self, name) -> None:
        pass


class FakeNotify:
    def __init__(self):
        self.update_cache_calls = 0

    def update_cache(self) -> None:
        self.update_cache_calls += 1


def make_auto_user_add(
    bot,
    monkeypatch,
    enabled=True,
    private=False,
    notify=False,
    ids=None,
    rows_by_query=None,
    use_real_user=True,
) -> AutoUserAdd:
    """Builds an AutoUserAdd wired to the real User module (per the porting
    brief: core("user") is already ported, so exercise the real thing rather
    than faking it) plus lightweight fakes for User's own dependencies.
    """
    settings = _FakeSettingsWithCreate(
        {
            ("Autouseradd", "Enabled"): enabled,
            ("Autouseradd", "Private"): private,
            ("Autouseradd", "Notify"): notify,
            ("Members", "Mark_notify"): False,
            ("Members", "Notify_level"): 2,
        }
    )
    Tools(bot)
    bot.register_module(settings, "settings")
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

    if use_real_user:
        User(bot)
    return AutoUserAdd(bot)


# -- construction -------------------------------------------------------------

def test_registers_as_autouseradd_module(bot, monkeypatch):
    module = make_auto_user_add(bot, monkeypatch)
    assert bot.core("autouseradd") is module


def test_creates_default_settings(bot, monkeypatch):
    make_auto_user_add(bot, monkeypatch)
    settings = bot.core("settings")
    names = [c[1] for c in settings.created if c[0] == "Autouseradd"]
    assert set(names) == {"Enabled", "Private", "Notify"}


def test_prefills_checked_from_existing_members(bot, monkeypatch):
    module = make_auto_user_add(
        bot, monkeypatch, rows_by_query={"user_level = 2": [("Existingmember",)]}
    )
    assert module.checked == {"Existingmember": True}


# -- gmsg() / settings gate ----------------------------------------------------

def test_gmsg_disabled_does_nothing(bot, monkeypatch):
    module = make_auto_user_add(bot, monkeypatch, enabled=False, ids={"Newguy": 111})
    module.gmsg("Newguy", "org", "some message")
    assert "Newguy" not in module.checked
    assert bot.core("chat").added == []


def test_gmsg_first_sighting_adds_user(bot, monkeypatch):
    module = make_auto_user_add(bot, monkeypatch, ids={"Newguy": 111})
    module.gmsg("Newguy", "org", "some message")
    assert module.checked["Newguy"] is True
    inserts = [q for q in bot.db.queries if q.startswith("INSERT INTO #___users")]
    assert len(inserts) == 1
    assert "'111'" in inserts[0]
    assert "'Newguy'" in inserts[0]


def test_gmsg_second_sighting_does_not_readd(bot, monkeypatch):
    module = make_auto_user_add(bot, monkeypatch, ids={"Newguy": 111})
    module.gmsg("Newguy", "org", "one")
    module.gmsg("Newguy", "org", "two")
    inserts = [q for q in bot.db.queries if q.startswith("INSERT INTO #___users")]
    assert len(inserts) == 1


def test_gmsg_existing_row_with_member_level_is_not_readded(bot, monkeypatch):
    module = make_auto_user_add(
        bot,
        monkeypatch,
        ids={"Already": 222},
        rows_by_query={"nickname = 'Already'": [(2,)]},
    )
    module.gmsg("Already", "org", "hi")
    assert bot.db.queries == [] or all(
        not q.startswith("INSERT INTO #___users") for q in bot.db.queries
    )


def test_gmsg_existing_row_with_non_member_level_is_readded(bot, monkeypatch):
    module = make_auto_user_add(bot, monkeypatch, ids={"Guestguy": 333})

    def fake_select(sql, *a, **kw):
        # Only AutoUserAdd's own pre-check query sees an existing non-member
        # row; User.add()'s subsequent lookups see a clean slate (fresh add).
        if sql == "SELECT user_level FROM #___users WHERE nickname = 'Guestguy'":
            return [(1,)]
        return []

    monkeypatch.setattr(bot.db, "select", fake_select)
    module.gmsg("Guestguy", "org", "hi")
    inserts = [q for q in bot.db.queries if q.startswith("INSERT INTO #___users")]
    assert len(inserts) == 1


# -- pgjoin() -------------------------------------------------------------------

def test_pgjoin_ignored_when_private_disabled(bot, monkeypatch):
    module = make_auto_user_add(bot, monkeypatch, private=False, ids={"Newguy": 111})
    module.pgjoin("Newguy")
    assert "Newguy" not in module.checked


def test_pgjoin_delegates_to_gmsg_when_private_enabled(bot, monkeypatch):
    module = make_auto_user_add(bot, monkeypatch, private=True, ids={"Newguy": 111})
    module.pgjoin("Newguy")
    assert module.checked["Newguy"] is True
    inserts = [q for q in bot.db.queries if q.startswith("INSERT INTO #___users")]
    assert len(inserts) == 1


# -- add_user() / delegation to core("user").add() -----------------------------

def test_add_user_delegates_to_real_user_module_silent_by_default(bot, monkeypatch):
    module = make_auto_user_add(bot, monkeypatch, notify=False, ids={"Newguy": 111})
    module.add_user("Newguy")
    # Notify defaults to False -> silent=1 -> no send_tell attempted (would
    # otherwise require a running event loop via bot.aoc.send_tell()).
    inserts = [q for q in bot.db.queries if q.startswith("INSERT INTO #___users")]
    assert len(inserts) == 1
    assert "'2'" in inserts[0]  # user_level = MEMBER


def test_add_user_calls_registered_hooks(bot, monkeypatch):
    module = make_auto_user_add(bot, monkeypatch, ids={"Newguy": 111})
    hook = RecordingModule("hook")
    module.register(hook)
    module.add_user("Newguy")
    assert hook.calls == [("new_user", ("Newguy",), {})]


def test_register_appends_multiple_hooks(bot, monkeypatch):
    module = make_auto_user_add(bot, monkeypatch, ids={"Newguy": 111})
    hook1 = RecordingModule("hook1")
    hook2 = RecordingModule("hook2")
    module.register(hook1)
    module.register(hook2)
    module.add_user("Newguy")
    assert hook1.calls == [("new_user", ("Newguy",), {})]
    assert hook2.calls == [("new_user", ("Newguy",), {})]


# -- end-to-end wiring through Bot.register_event ------------------------------

def test_bot_register_event_gmsg_org_wires_into_real_module(bot, monkeypatch):
    module = make_auto_user_add(bot, monkeypatch)
    assert type(module).__name__ in bot.commands.get("gmsg", {}).get("org", {})


def test_bot_register_event_pgjoin_wires_into_real_module(bot, monkeypatch):
    module = make_auto_user_add(bot, monkeypatch)
    assert bot.commands.get("pgjoin", {}).get(type(module).__name__) is module
