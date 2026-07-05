from fakes import FakeAccessControl

from bebot.main_modules.command_alias import CommandAlias
from bebot.main_modules.command_alias_ui import CommandAliasUi
from bebot.main_modules.tools import Tools


class _FakeAccessControlWithCreate(FakeAccessControl):
    """FakeAccessControl doesn't implement create() -- register_command() calls
    it to register the access level required for the "comalias" command."""

    def create(self, channel, command, access):
        pass


def make_ui(bot, monkeypatch=None, rows=None) -> CommandAliasUi:
    """Builds a CommandAliasUi wired to the *real* CommandAlias core module
    (rather than a fake), since command_alias is already fully ported and
    this UI module is just a thin dispatcher over it.
    """
    bot.register_module(_FakeAccessControlWithCreate(), "access_control")
    Tools(bot)
    if rows is not None and monkeypatch is not None:
        monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: rows)
    CommandAlias(bot)
    return CommandAliasUi(bot)


# -- construction ---------------------------------------------------------------

def test_registers_as_command_alias_ui_module(bot, monkeypatch):
    ui = make_ui(bot, monkeypatch)
    assert bot.core("command_alias_ui") is ui


def test_registers_comalias_command(bot, monkeypatch):
    make_ui(bot, monkeypatch)
    assert bot.commands["tell"]["comalias"] is bot.core("command_alias_ui")


def test_help_describes_subcommands(bot, monkeypatch):
    ui = make_ui(bot, monkeypatch)
    assert "comalias add <alias> <command>" in ui.help["command"]
    assert "comalias del <alias>" in ui.help["command"]
    assert "comalias rem <alias>" in ui.help["command"]


# -- add ------------------------------------------------------------------------

def test_add_new_alias_success(bot, monkeypatch):
    ui = make_ui(bot, monkeypatch)
    result = ui.command_handler("Someuser", "comalias add foo bar baz", "tell")
    assert "foo" in result and "is now an alias of" in result
    assert "bar baz" in result
    assert bot.core("command_alias").exists("foo")
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___command_alias")]
    assert any("foo" in q and "bar baz" in q for q in insert_queries)


def test_add_duplicate_alias_returns_already_exists(bot, monkeypatch):
    ui = make_ui(bot, monkeypatch)
    ui.command_handler("Someuser", "comalias add foo bar", "tell")
    result = ui.command_handler("Someuser", "comalias add foo qux", "tell")
    assert "is already an alias of" in result
    assert "bar" in result


def test_add_comalias_itself_rejected(bot, monkeypatch):
    ui = make_ui(bot, monkeypatch)
    result = ui.command_handler("Someuser", "comalias add comalias somecmd", "tell")
    assert "Cannot be set as an alias" in result
    assert not bot.core("command_alias").exists("comalias")


# -- del / rem --------------------------------------------------------------

def test_del_existing_alias_deletes(bot, monkeypatch):
    ui = make_ui(bot, monkeypatch)
    ui.command_handler("Someuser", "comalias add foo bar", "tell")
    # Make the follow-up SELECT (used by delete() to confirm a DB row exists)
    # report the row we just "inserted".
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [("foo",)])
    result = ui.command_handler("Someuser", "comalias del foo", "tell")
    assert "deleted" in result
    assert not bot.core("command_alias").exists("foo")
    assert any("DELETE FROM #___command_alias WHERE alias = 'foo'" in q for q in bot.db.queries)


def test_rem_is_alias_of_del(bot, monkeypatch):
    ui = make_ui(bot, monkeypatch)
    ui.command_handler("Someuser", "comalias add foo bar", "tell")
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [("foo",)])
    result = ui.command_handler("Someuser", "comalias rem foo", "tell")
    assert "deleted" in result
    assert not bot.core("command_alias").exists("foo")


def test_del_unknown_alias_not_found(bot, monkeypatch):
    ui = make_ui(bot, monkeypatch)
    result = ui.command_handler("Someuser", "comalias del nosuchalias", "tell")
    assert "not found" in result


def test_del_alias_registered_but_not_db_backed_cannot_be_deleted(bot, monkeypatch):
    ui = make_ui(bot, monkeypatch)
    # register() is how config-defined (non-DB) aliases get loaded at startup;
    # unlike add(), it never inserts a row, so delete() should refuse.
    bot.core("command_alias").register("somecommand", "cfgalias")
    result = ui.command_handler("Someuser", "comalias del cfgalias", "tell")
    assert "cannot be deleted" in result
    assert bot.core("command_alias").exists("cfgalias")


# -- default / listing -----------------------------------------------------------

def test_default_no_aliases_set(bot, monkeypatch):
    ui = make_ui(bot, monkeypatch)
    result = ui.command_handler("Someuser", "comalias", "tell")
    assert result == "No command aliases set!"


def test_default_lists_aliases_with_delete_link(bot, monkeypatch):
    ui = make_ui(bot, monkeypatch)
    ui.command_handler("Someuser", "comalias add foo bar baz", "tell")
    result = ui.command_handler("Someuser", "comalias", "tell")
    assert result.startswith("Command aliases :: ")
    assert "foo" in result
    assert "bar baz" in result
    assert "comalias del foo" in result


def test_default_lists_multiple_aliases(bot, monkeypatch):
    ui = make_ui(bot, monkeypatch)
    ui.command_handler("Someuser", "comalias add foo cmd1", "tell")
    ui.command_handler("Someuser", "comalias add bar cmd2", "tell")
    result = ui.command_handler("Someuser", "comalias", "tell")
    assert "foo" in result
    assert "bar" in result
    assert "cmd1" in result
    assert "cmd2" in result
