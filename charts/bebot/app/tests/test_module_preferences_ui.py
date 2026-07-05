from bebot.commodities.base import BotError
from bebot.main_modules.command_alias import CommandAlias
from bebot.main_modules.preferences import Preferences
from bebot.main_modules.preferences_ui import PreferencesUi
from bebot.main_modules.tools import Tools
from fakes import FakeAccessControl, FakePlayer


class _FakeAccessControlWithCreate(FakeAccessControl):
    """FakeAccessControl doesn't implement create()/create_subcommand() --
    register_command() calls both to register the access levels required
    for the "preferences" command and its "default" subcommand."""

    def create(self, channel, command, access):
        pass

    def create_subcommand(self, channel, command, sub, defaultlevel):
        pass


class FakeNotify:
    """Stands in for core("notify"): records check()/add() calls so tests
    can assert on the PHP's special-cased "auto-add to notify list" side
    effect without pulling in the real Notify/User modules."""

    def __init__(self, already_notified: bool = False):
        self.already_notified = already_notified
        self.checked: list[str] = []
        self.added: list[tuple[str, str]] = []

    def check(self, name: str) -> bool:
        self.checked.append(name)
        return self.already_notified

    def add(self, source: str, user: str):
        self.added.append((source, user))
        return f"{user} added to notify list!"


def make_ui(bot, already_notified: bool = False):
    """Builds a PreferencesUi wired to the *real*, already-ported
    Preferences core module (registered as "prefs"), since this module is
    a thin chat-command layer over preferences.py and we want genuine
    integration coverage.
    """
    bot.register_module(_FakeAccessControlWithCreate(), "access_control")
    bot.register_module(FakePlayer(ids={"Testchar": 1, "Otherchar": 2}), "player")
    notify = FakeNotify(already_notified=already_notified)
    bot.register_module(notify, "notify")
    Tools(bot)
    CommandAlias(bot)
    Preferences(bot)
    ui = PreferencesUi(bot)
    return ui, notify


def _select_dispatch(def_cache_rows=None, distinct_modules=None, module_defaults=None, show_prefs_defs=None):
    """A bot.db.select() stand-in dispatching on the distinct query shapes
    preferences.py issues, mirroring the pattern used in
    test_module_settings_ui.py."""

    def fake_select(sql, as_dict=False, *a, **kw):
        if "default_value AS value FROM #___preferences_def" in sql:
            return list(def_cache_rows or [])
        if "SELECT DISTINCT(module) FROM #___preferences_def" in sql:
            return list(distinct_modules or [])
        if "SELECT DISTINCT(name), default_value FROM #___preferences_def WHERE module=" in sql:
            return list(module_defaults or [])
        if "SELECT name, description, default_value, possible_values FROM #___preferences_def WHERE module=" in sql:
            return list(show_prefs_defs or [])
        return []

    return fake_select


# -- construction ---------------------------------------------------------------

def test_registers_as_preferences_ui_module(bot):
    ui, _ = make_ui(bot)
    assert bot.core("preferences_ui") is ui


def test_registers_preferences_command_on_all_channels(bot):
    ui, _ = make_ui(bot)
    for channel in ("tell", "gc", "pgmsg"):
        assert bot.commands[channel]["preferences"] is ui


def test_registers_prefs_alias(bot):
    make_ui(bot)
    assert bot.core("command_alias").exists("prefs")


def test_help_describes_commands_and_notes(bot):
    ui, _ = make_ui(bot)
    assert "preferences" in ui.help["command"]
    assert "default" in ui.help["notes"]


# -- command_handler: no args / show ---------------------------------------------

def test_command_handler_no_args_shows_modules(bot, monkeypatch):
    ui, _ = make_ui(bot)
    monkeypatch.setattr(
        bot.db, "select", _select_dispatch(distinct_modules=[("Autoinv",), ("Mail",)])
    )
    result = ui.command_handler("Testchar", "preferences", "tell")
    assert "preferences show autoinv" in result
    assert "preferences show mail" in result
    assert "Preferences" in result


def test_command_handler_show_no_module_shows_all_modules(bot, monkeypatch):
    ui, _ = make_ui(bot)
    monkeypatch.setattr(
        bot.db, "select", _select_dispatch(distinct_modules=[("Autoinv",)])
    )
    result = ui.command_handler("Testchar", "preferences show", "tell")
    assert "preferences show autoinv" in result


def test_command_handler_show_specific_module(bot, monkeypatch):
    ui, _ = make_ui(bot)
    monkeypatch.setattr(
        bot.db,
        "select",
        _select_dispatch(
            module_defaults=[("receive_auto_invite", "Off")],
            show_prefs_defs=[
                {
                    "name": "receive_auto_invite",
                    "description": "Receive auto invites",
                    "default_value": "Off",
                    "possible_values": "On;Off",
                }
            ],
        ),
    )
    result = ui.command_handler("Testchar", "preferences show autoinv", "tell")
    assert "receive_auto_invite" in result
    assert "Receive auto invites" in result
    assert "preferences set autoinv receive_auto_invite On" in result
    # The current default value gets a green "[D]" marker instead of a link.
    assert "preferences default autoinv receive_auto_invite On" in result
    assert "Preferences for" in result
    assert "autoinv" in result


# -- command_handler: set --------------------------------------------------------

def test_command_handler_set_creates_customised_value(bot, monkeypatch):
    ui, notify = make_ui(bot)
    monkeypatch.setattr(
        bot.db, "select", _select_dispatch(def_cache_rows=[
            {"module": "Autoinv", "name": "receive_auto_invite", "value": "Off"}
        ])
    )
    bot.core("prefs").connect()
    result = ui.command_handler("Testchar", "preferences set autoinv receive_auto_invite On", "tell")
    assert result == "Preference was created for Testchar, autoinv->receive_auto_invite = On"
    assert bot.core("prefs").get(1, "autoinv", "receive_auto_invite") == "On"


def test_command_handler_set_already_at_value_reports_no_change(bot, monkeypatch):
    ui, _ = make_ui(bot)
    monkeypatch.setattr(
        bot.db, "select", _select_dispatch(def_cache_rows=[
            {"module": "Autoinv", "name": "receive_auto_invite", "value": "Off"}
        ])
    )
    bot.core("prefs").connect()
    result = ui.command_handler("Testchar", "preferences set autoinv receive_auto_invite Off", "tell")
    assert result == "Preference for Testchar, autoinv->receive_auto_invite was already set to 'Off'. Nothing changed."


def test_command_handler_set_back_to_default_resets(bot, monkeypatch):
    ui, _ = make_ui(bot)
    monkeypatch.setattr(
        bot.db, "select", _select_dispatch(def_cache_rows=[
            {"module": "Autoinv", "name": "receive_auto_invite", "value": "Off"}
        ])
    )
    bot.core("prefs").connect()
    ui.command_handler("Testchar", "preferences set autoinv receive_auto_invite On", "tell")
    result = ui.command_handler("Testchar", "preferences set autoinv receive_auto_invite Off", "tell")
    assert result == "Preferences for Testchar, autoinv->receive_auto_invite reset to default value 'Off'"
    assert bot.core("prefs").get(1, "autoinv", "receive_auto_invite") == "Off"


def test_command_handler_set_updates_from_one_non_default_to_another(bot, monkeypatch):
    ui, _ = make_ui(bot)
    monkeypatch.setattr(
        bot.db, "select", _select_dispatch(def_cache_rows=[
            {"module": "Autoinv", "name": "receive_auto_invite", "value": "Maybe"}
        ])
    )
    bot.core("prefs").connect()
    ui.command_handler("Testchar", "preferences set autoinv receive_auto_invite On", "tell")
    result = ui.command_handler("Testchar", "preferences set autoinv receive_auto_invite Off", "tell")
    assert result == "Preferences for Testchar, autoinv->receive_auto_invite changed to 'Off'"


# -- command_handler: set / notify side effect -----------------------------------

def test_set_autoinv_receive_on_adds_to_notify_list(bot, monkeypatch):
    ui, notify = make_ui(bot, already_notified=False)
    monkeypatch.setattr(bot.db, "select", _select_dispatch())
    ui.command_handler("Testchar", "preferences set autoinv receive_auto_invite on", "tell")
    assert notify.checked == ["Testchar"]
    assert notify.added == [("Testchar", "Testchar")]


def test_set_mail_logon_notification_yes_adds_to_notify_list(bot, monkeypatch):
    ui, notify = make_ui(bot, already_notified=False)
    monkeypatch.setattr(bot.db, "select", _select_dispatch())
    ui.command_handler("Testchar", "preferences set mail logon_notification yes", "tell")
    assert notify.added == [("Testchar", "Testchar")]


def test_set_massmsg_yes_adds_to_notify_list(bot, monkeypatch):
    ui, notify = make_ui(bot, already_notified=False)
    monkeypatch.setattr(bot.db, "select", _select_dispatch())
    ui.command_handler("Testchar", "preferences set massmsg anything yes", "tell")
    assert notify.added == [("Testchar", "Testchar")]


def test_set_massmsg_no_does_not_add_to_notify_list(bot, monkeypatch):
    ui, notify = make_ui(bot, already_notified=False)
    monkeypatch.setattr(bot.db, "select", _select_dispatch())
    ui.command_handler("Testchar", "preferences set massmsg anything no", "tell")
    assert notify.added == []


def test_set_autoinv_receive_off_does_not_add_to_notify_list(bot, monkeypatch):
    ui, notify = make_ui(bot, already_notified=False)
    monkeypatch.setattr(bot.db, "select", _select_dispatch())
    ui.command_handler("Testchar", "preferences set autoinv receive_auto_invite off", "tell")
    assert notify.added == []


def test_set_already_notified_skips_add(bot, monkeypatch):
    ui, notify = make_ui(bot, already_notified=True)
    monkeypatch.setattr(bot.db, "select", _select_dispatch())
    ui.command_handler("Testchar", "preferences set autoinv receive_auto_invite on", "tell")
    assert notify.checked == ["Testchar"]
    assert notify.added == []


# -- command_handler: default -----------------------------------------------------

def test_command_handler_default_changes_default_value(bot, monkeypatch):
    ui, _ = make_ui(bot)
    monkeypatch.setattr(
        bot.db, "select", _select_dispatch(def_cache_rows=[
            {"module": "Autoinv", "name": "receive_auto_invite", "value": "Off"}
        ])
    )
    bot.core("prefs").connect()
    result = ui.command_handler("Testchar", "preferences default autoinv receive_auto_invite On", "tell")
    assert result == "The default value for autoinv->receive_auto_invite has been set to 'On'."
    assert bot.core("prefs").cache["def"]["autoinv"]["receive_auto_invite"] == "On"


# -- command_handler: reset (dead code path) / unknown subcommand ---------------

def test_command_handler_reset_is_unsupported_and_errors(bot, monkeypatch):
    """The PHP dispatches "reset" to a core method (`Preferences::reset()`)
    that has never existed on either the PHP or ported class -- this must
    not raise AttributeError, and instead behaves like any other unknown
    subcommand."""
    ui, _ = make_ui(bot)
    monkeypatch.setattr(bot.db, "select", _select_dispatch())
    result = ui.command_handler("Testchar", "preferences reset autoinv", "tell")
    assert isinstance(result, BotError)
    assert "reset" in result.get()


def test_command_handler_unknown_subcommand_returns_error(bot, monkeypatch):
    ui, _ = make_ui(bot)
    monkeypatch.setattr(bot.db, "select", _select_dispatch())
    result = ui.command_handler("Testchar", "preferences frobnicate", "tell")
    assert isinstance(result, BotError)
    assert "frobnicate" in result.get()


# -- integration: alias replacement + registered command dispatch ----------------

def test_prefs_alias_replaces_to_preferences_command(bot):
    make_ui(bot)
    replaced = bot.core("command_alias").replace("prefs show autoinv")
    assert replaced == "preferences show autoinv"
