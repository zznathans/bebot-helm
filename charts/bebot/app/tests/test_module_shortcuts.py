from bebot.commodities.base import BotError
from bebot.main_modules.shortcuts import DEFAULT_SHORTCUTS, Shortcuts


def make_shortcuts(bot, monkeypatch, rows=None):
    """Builds a Shortcuts module whose create_caches() sees `rows` (or the
    default seed set if rows is None) instead of the FakeMySQL's empty select().
    """
    if rows is None:
        rows = list(DEFAULT_SHORTCUTS)
    monkeypatch.setattr(bot.db, "select", lambda sql: rows)
    return Shortcuts(bot)


# -- construction / seeding ----------------------------------------------------

def test_creates_table_and_seeds_defaults(bot, monkeypatch):
    monkeypatch.setattr(bot.db, "select", lambda sql: [])
    Shortcuts(bot)
    create_queries = [q for q in bot.db.queries if "CREATE TABLE" in q]
    insert_queries = [q for q in bot.db.queries if "INSERT IGNORE" in q]
    assert len(create_queries) == 1
    assert "shortcuts" in create_queries[0]
    assert len(insert_queries) == 1
    assert "'Pres', 'President'" in insert_queries[0]
    assert "'Peas', 'Peasant'" in insert_queries[0]


def test_registers_as_shortcuts_module(bot, monkeypatch):
    monkeypatch.setattr(bot.db, "select", lambda sql: [])
    module = Shortcuts(bot)
    assert bot.core("shortcuts") is module


# -- get_short / get_long -------------------------------------------------------

def test_get_short_known_long_description(bot, monkeypatch):
    module = make_shortcuts(bot, monkeypatch)
    assert module.get_short("President") == "Pres"


def test_get_short_is_case_insensitive(bot, monkeypatch):
    module = make_shortcuts(bot, monkeypatch)
    assert module.get_short("president") == "Pres"
    assert module.get_short("PRESIDENT") == "Pres"


def test_get_short_unknown_returns_unmodified(bot, monkeypatch):
    module = make_shortcuts(bot, monkeypatch)
    assert module.get_short("Nonexistent Rank") == "Nonexistent Rank"


def test_get_long_known_shortcut(bot, monkeypatch):
    module = make_shortcuts(bot, monkeypatch)
    assert module.get_long("Pres") == "President"


def test_get_long_is_case_insensitive(bot, monkeypatch):
    module = make_shortcuts(bot, monkeypatch)
    assert module.get_long("PRES") == "President"


def test_get_long_unknown_returns_unmodified(bot, monkeypatch):
    module = make_shortcuts(bot, monkeypatch)
    assert module.get_long("Nope") == "Nope"


# -- add -------------------------------------------------------------------

def test_add_new_shortcut_updates_cache_and_db(bot, monkeypatch):
    module = make_shortcuts(bot, monkeypatch)
    result = module.add("Amb", "Ambassador")
    assert result == 'New shortcut "Amb" added to database with corresponding long entry "Ambassador".'
    assert module.get_short("Ambassador") == "Amb"
    assert module.get_long("Amb") == "Ambassador"
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___shortcuts")]
    assert any("Amb" in q and "Ambassador" in q for q in insert_queries)


def test_add_duplicate_long_description_returns_error(bot, monkeypatch):
    module = make_shortcuts(bot, monkeypatch)
    result = module.add("Prz", "President")
    assert isinstance(result, BotError)
    assert "already is in the databse" in result.get()
    # cache must not have been mutated
    assert module.get_short("President") == "Pres"


def test_add_duplicate_shortcut_returns_error(bot, monkeypatch):
    module = make_shortcuts(bot, monkeypatch)
    result = module.add("Pres", "Presiding Officer")
    assert isinstance(result, BotError)
    assert "is already defined" in result.get()
    assert module.get_long("Pres") == "President"


def test_add_duplicate_is_case_insensitive(bot, monkeypatch):
    module = make_shortcuts(bot, monkeypatch)
    result = module.add("pres", "someone else")
    assert isinstance(result, BotError)


# -- delete_shortcut ---------------------------------------------------------

def test_delete_shortcut_removes_from_cache_and_db(bot, monkeypatch):
    module = make_shortcuts(bot, monkeypatch)
    result = module.delete_shortcut("Pres")
    assert result == (
        'The shortcut "Pres" and the corresponding long description "President" were deleted!'
    )
    assert module.get_short("President") == "President"  # no longer cached -> unmodified passthrough
    assert module.get_long("Pres") == "Pres"
    assert any("DELETE FROM #___shortcuts WHERE shortcut = 'Pres'" in q for q in bot.db.queries)


def test_delete_shortcut_unknown_returns_error(bot, monkeypatch):
    module = make_shortcuts(bot, monkeypatch)
    result = module.delete_shortcut("Nope")
    assert isinstance(result, BotError)
    assert "does not exist" in result.get()


# -- delete_description -------------------------------------------------------

def test_delete_description_removes_from_cache_and_db(bot, monkeypatch):
    module = make_shortcuts(bot, monkeypatch)
    result = module.delete_description("President")
    assert result == (
        'The description "President" and the corresponding shortcut "Pres" were deleted!'
    )
    assert module.get_long("Pres") == "Pres"
    assert module.get_short("President") == "President"
    assert any("DELETE FROM #___shortcuts WHERE long_desc = 'President'" in q for q in bot.db.queries)


def test_delete_description_unknown_returns_error(bot, monkeypatch):
    module = make_shortcuts(bot, monkeypatch)
    result = module.delete_description("Nonexistent")
    assert isinstance(result, BotError)
    assert "does not exist" in result.get()


# -- delete_id ---------------------------------------------------------------

def test_delete_id_found_deletes_and_reports(bot, monkeypatch):
    module = make_shortcuts(bot, monkeypatch)
    monkeypatch.setattr(bot.db, "select", lambda sql: [("Pres", "President")])
    result = module.delete_id(3)
    assert result == "The entry with the ID 3 has been deleted. Shortcut: Pres, long description: President."
    assert any("DELETE FROM #___shortcuts WHERE id = 3" in q for q in bot.db.queries)


def test_delete_id_not_found_returns_error(bot, monkeypatch):
    module = make_shortcuts(bot, monkeypatch)
    monkeypatch.setattr(bot.db, "select", lambda sql: [])
    result = module.delete_id(999)
    assert isinstance(result, BotError)
    assert "No entry with the ID 999 exists!" in result.get()


# -- cron ---------------------------------------------------------------------

def test_cron_rebuilds_caches_from_db(bot, monkeypatch):
    module = make_shortcuts(bot, monkeypatch, rows=[("Pres", "President")])
    assert module.get_short("Ambassador") == "Ambassador"
    monkeypatch.setattr(bot.db, "select", lambda sql: [("Pres", "President"), ("Amb", "Ambassador")])
    module.cron()
    assert module.get_short("Ambassador") == "Amb"
