from bebot.commodities.base import BotError
from bebot.main_modules.shortcuts import DEFAULT_SHORTCUTS, Shortcuts
from bebot.main_modules.shortcuts_ui import ShortcutsUi
from bebot.main_modules.tools import Tools


def _make_select(cache_rows, show_rows):
    """Dispatches on the shape of the SQL, mirroring the two query shapes
    this feature actually issues: show_shortcuts()'s "... ORDER BY shortcut
    ASC" listing query (id included), versus the plain "shortcut, long_desc"
    scan used by core("shortcuts")'s create_caches()/cron().
    """

    def fake_select(sql, *a, **kw):
        if "ORDER BY shortcut ASC" in sql:
            return list(show_rows)
        return list(cache_rows)

    return fake_select


def make_module(bot, monkeypatch, cache_rows=None, show_rows=None) -> ShortcutsUi:
    """Builds a real ShortcutsUi wired to a real core("shortcuts") Shortcuts
    module (integration-style, per the task brief), with bot.db.select
    faked to serve both modules' distinct query shapes.
    """
    if cache_rows is None:
        cache_rows = list(DEFAULT_SHORTCUTS)
    if show_rows is None:
        show_rows = [(short, long, i + 1) for i, (short, long) in enumerate(cache_rows)]
    monkeypatch.setattr(bot.db, "select", _make_select(cache_rows, show_rows))
    Tools(bot)
    Shortcuts(bot)
    return ShortcutsUi(bot)


# -- construction / registration ------------------------------------------------

def test_registers_as_shortcuts_ui_module(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    assert bot.core("shortcuts_ui") is module


def test_registers_shortcuts_command_on_all_channels(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    assert bot.commands["tell"]["shortcuts"] is module
    assert bot.commands["gc"]["shortcuts"] is module
    assert bot.commands["pgmsg"]["shortcuts"] is module


# -- show_shortcuts ---------------------------------------------------------------

def test_show_shortcuts_empty_returns_message(bot, monkeypatch):
    module = make_module(bot, monkeypatch, cache_rows=[], show_rows=[])
    result = module.show_shortcuts()
    assert result == "No shortcuts defined!"


def test_show_shortcuts_lists_entries_with_delete_links(bot, monkeypatch):
    rows = [("Pres", "President"), ("Gen", "General")]
    show_rows = [("Gen", "General", 1), ("Pres", "President", 2)]
    module = make_module(bot, monkeypatch, cache_rows=rows, show_rows=show_rows)
    result = module.show_shortcuts()
    assert "Gen" in result and "General" in result
    assert "Pres" in result and "President" in result
    assert "shortcuts del 1" in result
    assert "shortcuts del 2" in result
    assert "[DELETE]" in result
    assert "Defined shortcuts" in result


def test_command_handler_dispatches_show_shortcuts(bot, monkeypatch):
    module = make_module(bot, monkeypatch, cache_rows=[], show_rows=[])
    result = module.command_handler("Somechar", "shortcuts", "tell")
    assert result == "No shortcuts defined!"


def test_command_handler_show_shortcuts_case_insensitive(bot, monkeypatch):
    module = make_module(bot, monkeypatch, cache_rows=[], show_rows=[])
    result = module.command_handler("Somechar", "SHORTCUTS", "tell")
    assert result == "No shortcuts defined!"


# -- add ----------------------------------------------------------------------

def test_add_new_shortcut_succeeds(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.add("Amb", "Ambassador")
    assert result == 'New shortcut "Amb" added to database with corresponding long entry "Ambassador".'
    assert module.bot.core("shortcuts").get_long("Amb") == "Ambassador"


def test_add_strips_quotes(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.add("'Amb'", '"Ambassador"')
    assert result == 'New shortcut "Amb" added to database with corresponding long entry "Ambassador".'


def test_add_short_longer_than_long_is_rejected(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.add("Ambassadorial", "Amb")
    assert result == "Short cannot be longer (nor equal) than long."


def test_add_short_equal_length_to_long_is_rejected(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.add("abcd", "wxyz")
    assert result == "Short cannot be longer (nor equal) than long."


def test_add_duplicate_long_description_returns_error(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.add("Prz", "President")
    assert isinstance(result, BotError)
    assert "already is in the databse" in result.get()


def test_add_duplicate_shortcut_returns_error(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.add("Pres", "Presiding Officer")
    assert isinstance(result, BotError)
    assert "is already defined" in result.get()


# -- delete ---------------------------------------------------------------------

def test_delete_known_id_succeeds(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [("Pres", "President")])
    result = module.delete(1)
    assert result == "The entry with the ID 1 has been deleted. Shortcut: Pres, long description: President."


def test_delete_unknown_id_returns_error(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [])
    result = module.delete(999)
    assert isinstance(result, BotError)
    assert "No entry with the ID 999 exists!" in result.get()


# -- command_handler dispatch ----------------------------------------------------

def test_command_handler_add_dispatches(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.command_handler("Somechar", "shortcuts add Amb Ambassador", "tell")
    assert result == 'New shortcut "Amb" added to database with corresponding long entry "Ambassador".'


def test_command_handler_add_case_insensitive(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.command_handler("Somechar", "SHORTCUTS ADD Amb Ambassador", "tell")
    assert result == 'New shortcut "Amb" added to database with corresponding long entry "Ambassador".'


def test_command_handler_add_with_multiword_long_only_keeps_last_word(bot, monkeypatch):
    """Faithful-port quirk (see module docstring): the greedy regex splits
    on the *last* space, so a multi-word description gets truncated to its
    final word while the leading words spill into <short> instead."""
    module = make_module(bot, monkeypatch)
    result = module.command_handler("Somechar", "shortcuts add Amb Grand Ambassador", "tell")
    assert result == 'New shortcut "Amb Grand" added to database with corresponding long entry "Ambassador".'
    assert module.bot.core("shortcuts").get_long("Amb Grand") == "Ambassador"


def test_command_handler_del_dispatches(bot, monkeypatch):
    module = make_module(bot, monkeypatch)

    def fake_select(sql, *a, **kw):
        if "WHERE id = 5" in sql:
            return [("Pres", "President")]
        return []

    monkeypatch.setattr(bot.db, "select", fake_select)
    result = module.command_handler("Somechar", "shortcuts del 5", "tell")
    assert result == "The entry with the ID 5 has been deleted. Shortcut: Pres, long description: President."


def test_command_handler_del_non_numeric_id_unrecognized(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.command_handler("Somechar", "shortcuts del abc", "tell")
    assert result is None


def test_command_handler_unrecognized_command_returns_none(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.command_handler("Somechar", "shortcuts frobnicate", "tell")
    assert result is None
