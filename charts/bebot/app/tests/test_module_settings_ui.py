from bebot.commodities.base import BotError
from bebot.main_modules.command_alias import CommandAlias
from bebot.main_modules.settings import Settings
from bebot.main_modules.settings_ui import SettingsUi
from bebot.main_modules.tools import Tools
from fakes import FakeAccessControl


class _FakeAccessControlWithCreate(FakeAccessControl):
    """FakeAccessControl doesn't implement create() -- register_command()
    calls it to register the access level required for the "settings"
    command."""

    def create(self, channel, command, access):
        pass


def make_ui(bot) -> SettingsUi:
    """Builds a SettingsUi wired to the *real*, already-ported Settings and
    CommandAlias core modules (rather than fakes), since this module is a
    thin chat-command layer over settings.py and we want genuine
    integration coverage.
    """
    bot.register_module(_FakeAccessControlWithCreate(), "access_control")
    Tools(bot)
    Settings(bot)
    CommandAlias(bot)
    return SettingsUi(bot)


def _select_dispatch(module_rows=None, setting_rows=None):
    """A bot.db.select() stand-in that answers the two read-only queries
    show_all_modules()/show_module() issue, while leaving every other query
    (the ones settings.py/access_control.py/command_alias.py issue during
    setup, and settings.py's create()/save() "does it already exist" checks)
    behaving like the default FakeMySQL (empty result).
    """

    def fake_select(sql, *a, **kw):
        if "DISTINCT module FROM #___settings" in sql:
            return list(module_rows or [])
        if "setting, value, datatype, longdesc, defaultoptions" in sql:
            return list(setting_rows or [])
        return []

    return fake_select


# -- construction ---------------------------------------------------------------

def test_registers_as_settings_ui_module(bot):
    ui = make_ui(bot)
    assert bot.core("settings_ui") is ui


def test_registers_settings_command_on_all_channels(bot):
    ui = make_ui(bot)
    for channel in ("tell", "gc", "pgmsg"):
        assert bot.commands[channel]["settings"] is ui


def test_registers_set_alias(bot):
    make_ui(bot)
    assert bot.core("command_alias").exists("set")


def test_help_describes_commands(bot):
    ui = make_ui(bot)
    assert "settings" in ui.help["command"]
    assert "set <module> <setting> <value>" in ui.help["command"]


# -- show_all_modules -----------------------------------------------------------

def test_show_all_modules_none_defined(bot, monkeypatch):
    ui = make_ui(bot)
    monkeypatch.setattr(bot.db, "select", _select_dispatch())
    result = ui.show_all_modules()
    assert result == "No settings defined."


def test_show_all_modules_lists_groups(bot, monkeypatch):
    ui = make_ui(bot)
    monkeypatch.setattr(bot.db, "select", _select_dispatch(module_rows=[("Testmod",), ("Othermod",)]))
    result = ui.show_all_modules()
    assert "Testmod" in result
    assert "Othermod" in result
    assert "settings Testmod" in result


def test_command_handler_no_args_shows_all_modules(bot, monkeypatch):
    ui = make_ui(bot)
    monkeypatch.setattr(bot.db, "select", _select_dispatch(module_rows=[("Testmod",)]))
    result = ui.command_handler("Someadmin", "settings", "tell")
    assert "Testmod" in result


# -- show_module ------------------------------------------------------------------

def test_show_module_no_settings(bot, monkeypatch):
    ui = make_ui(bot)
    monkeypatch.setattr(bot.db, "select", _select_dispatch())
    result = ui.show_module("Nonexistent")
    assert result == "No settings for module Nonexistent"


def test_show_module_shows_bool_setting_as_on_off(bot, monkeypatch):
    ui = make_ui(bot)
    rows = [("Enabled", "TRUE", "bool", "", "On;Off")]
    monkeypatch.setattr(bot.db, "select", _select_dispatch(setting_rows=rows))
    result = ui.show_module("Testmod")
    assert "Enabled" in result
    assert "On" in result
    assert "Change to" in result


def test_show_module_masks_password(bot, monkeypatch):
    ui = make_ui(bot)
    rows = [("Password", "hunter2", "string", "", "")]
    monkeypatch.setattr(bot.db, "select", _select_dispatch(setting_rows=rows))
    result = ui.show_module("Testmod")
    assert "hunter2" not in result
    assert "************" in result


def test_show_module_shows_color_swatch(bot, monkeypatch):
    ui = make_ui(bot)
    rows = [("Color", "#AABBCC", "string", "", "")]
    monkeypatch.setattr(bot.db, "select", _select_dispatch(setting_rows=rows))
    result = ui.show_module("Testmod")
    assert "<font color=#AABBCC>" in result


def test_show_module_generic_description_by_datatype(bot, monkeypatch):
    ui = make_ui(bot)
    rows = [("Threshold", "5", "int", "", "")]
    monkeypatch.setattr(bot.db, "select", _select_dispatch(setting_rows=rows))
    result = ui.show_module("Testmod")
    assert "Numeric" in result


def test_command_handler_module_arg_shows_module(bot, monkeypatch):
    ui = make_ui(bot)
    rows = [("Enabled", "TRUE", "bool", "", "On;Off")]
    monkeypatch.setattr(bot.db, "select", _select_dispatch(setting_rows=rows))
    result = ui.command_handler("Someadmin", "settings Testmod", "tell")
    assert "Enabled" in result


# -- change_setting -----------------------------------------------------------

def test_change_setting_nonexistent_setting(bot):
    ui = make_ui(bot)
    result = ui.change_setting("Someadmin", "Nosuchmod", "nosuchsetting", "value")
    assert result == "Setting nosuchsetting for module Nosuchmod does not exist."


def test_change_setting_bool_on(bot):
    ui = make_ui(bot)
    bot.core("settings").create("Testmod", "Enabled", False, "Enable it?", "On;Off")
    result = ui.change_setting("Someadmin", "Testmod", "Enabled", "on")
    assert "Changed setting Enabled for module Testmod to On" in result
    assert bot.core("settings").get("Testmod", "Enabled") is True


def test_change_setting_bool_off(bot):
    ui = make_ui(bot)
    bot.core("settings").create("Testmod", "Enabled", True, "Enable it?", "On;Off")
    result = ui.change_setting("Someadmin", "Testmod", "Enabled", "off")
    assert "Changed setting Enabled for module Testmod to Off" in result
    assert bot.core("settings").get("Testmod", "Enabled") is False


def test_change_setting_bool_invalid_value_rejected(bot):
    ui = make_ui(bot)
    bot.core("settings").create("Testmod", "Enabled", True, "Enable it?", "On;Off")
    result = ui.change_setting("Someadmin", "Testmod", "Enabled", "maybe")
    assert result == "Unrecognized value for setting Enabled for module Testmod. No change made."
    # No change made.
    assert bot.core("settings").get("Testmod", "Enabled") is True


def test_change_setting_string(bot):
    ui = make_ui(bot)
    bot.core("settings").create("Testmod", "Greeting", "hi", "Greeting text")
    result = ui.change_setting("Someadmin", "Testmod", "Greeting", "hello there")
    assert "Changed setting Greeting for module Testmod to hello there" in result
    assert bot.core("settings").get("Testmod", "Greeting") == "hello there"


def test_change_setting_int(bot):
    ui = make_ui(bot)
    bot.core("settings").create("Testmod", "Threshold", 5, "A threshold")
    result = ui.change_setting("Someadmin", "Testmod", "Threshold", "42")
    assert "Changed setting Threshold for module Testmod to 42" in result
    assert bot.core("settings").get("Testmod", "Threshold") == 42


def test_change_setting_int_invalid_value_coerces_like_php_intval(bot):
    ui = make_ui(bot)
    bot.core("settings").create("Testmod", "Threshold", 5, "A threshold")
    result = ui.change_setting("Someadmin", "Testmod", "Threshold", "not-a-number")
    assert "Changed setting Threshold for module Testmod to 0" in result
    assert bot.core("settings").get("Testmod", "Threshold") == 0


def test_change_setting_float(bot):
    ui = make_ui(bot)
    bot.core("settings").create("Testmod", "Ratio", 1.5, "A ratio")
    result = ui.change_setting("Someadmin", "Testmod", "Ratio", "2.75")
    assert "Changed setting Ratio for module Testmod to 2.75" in result
    assert bot.core("settings").get("Testmod", "Ratio") == 2.75


def test_change_setting_null_literal(bot):
    ui = make_ui(bot)
    bot.core("settings").create("Testmod", "Optional", None, "An optional value")
    result = ui.change_setting("Someadmin", "Testmod", "Optional", "null")
    assert "Changed setting Optional for module Testmod to None" in result
    assert bot.core("settings").get("Testmod", "Optional") is None


def test_change_setting_array_rejected(bot):
    ui = make_ui(bot)
    bot.core("settings").create("Testmod", "Items", ["a", "b"], "A list of items")
    result = ui.change_setting("Someadmin", "Testmod", "Items", "c;d")
    assert result == "Modifying array values is not supported in this interface. See the help for Testmod"
    assert bot.core("settings").get("Testmod", "Items") == ["a", "b"]


def test_change_setting_module_and_setting_names_normalize_spaces(bot):
    ui = make_ui(bot)
    bot.core("settings").create("Test mod", "My Setting", "hi", "Greeting text")
    result = ui.change_setting("Someadmin", "Test mod", "My Setting", "yo")
    assert "Changed setting My_Setting for module Test_mod to yo" in result
    assert bot.core("settings").get("Test_mod", "My_Setting") == "yo"


def test_change_setting_returns_bot_error_on_save_failure(bot, monkeypatch):
    ui = make_ui(bot)
    bot.core("settings").create("Testmod", "Greeting", "hi", "Greeting text")
    monkeypatch.setattr(bot.db, "query", lambda sql: False)
    result = ui.change_setting("Someadmin", "Testmod", "Greeting", "hello")
    assert isinstance(result, BotError)


# -- command_handler dispatch (change path) ------------------------------------

def test_command_handler_four_tokens_changes_setting(bot):
    ui = make_ui(bot)
    bot.core("settings").create("Testmod", "Greeting", "hi", "Greeting text")
    result = ui.command_handler("Someadmin", "settings Testmod Greeting hello", "tell")
    assert "Changed setting Greeting for module Testmod to hello" in result


def test_command_handler_three_tokens_preserved_php_quirk_always_not_found(bot):
    """Faithful port of a PHP argument-shift bug: "settings <module> <setting>"
    (no value) silently drops $name and shifts arguments, so setting always
    ends up empty and the lookup always reports "does not exist". See the
    module docstring."""
    ui = make_ui(bot)
    bot.core("settings").create("Testmod", "Greeting", "hi", "Greeting text")
    result = ui.command_handler("Someadmin", "settings Testmod Greeting", "tell")
    assert result == "Setting  for module Greeting does not exist."
    # The real setting was untouched.
    assert bot.core("settings").get("Testmod", "Greeting") == "hi"


# -- integration: alias replacement + registered command dispatch ----------------

def test_set_alias_replaces_to_settings_command(bot):
    make_ui(bot)
    replaced = bot.core("command_alias").replace("set Testmod Greeting hello")
    assert replaced == "settings Testmod Greeting hello"
