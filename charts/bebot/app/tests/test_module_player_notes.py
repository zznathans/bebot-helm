from bebot.commodities.base import BotError
from bebot.main_modules.player_notes import PlayerNotes
from bebot.main_modules.tools import Tools
from fakes import FakeSecurity


def make_player_notes(bot, monkeypatch, rows=None, access=True) -> PlayerNotes:
    Tools(bot)
    bot.register_module(FakeSecurity(access=access), "security")
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [] if rows is None else rows)
    return PlayerNotes(bot)


# -- construction --------------------------------------------------------

def test_creates_table_on_construction(bot, monkeypatch):
    module = make_player_notes(bot, monkeypatch)
    create_queries = [q for q in bot.db.queries if "CREATE TABLE" in q]
    assert len(create_queries) == 1
    assert "player_notes" in create_queries[0]
    assert "timestamp" in create_queries[0]


def test_registers_as_player_notes_module(bot, monkeypatch):
    module = make_player_notes(bot, monkeypatch)
    assert bot.core("player_notes") is module


# -- add -------------------------------------------------------------------

def test_add_inserts_note_and_returns_confirmation(bot, monkeypatch):
    module = make_player_notes(bot, monkeypatch, rows=[[7]])
    result = module.add("someplayer", "someauthor", "Watch out for this one", "admin")
    assert result == 'Successfully added "Watch out for this one" note to Someplayer as note id 7'
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___player_notes")]
    assert len(insert_queries) == 1
    assert "'Someplayer'" in insert_queries[0]
    assert "'Someauthor'" in insert_queries[0]
    assert "'Watch out for this one'" in insert_queries[0]
    assert ", 2, " in insert_queries[0]  # "admin" -> class 2


def test_add_sanitizes_and_capitalizes_names(bot, monkeypatch):
    module = make_player_notes(bot, monkeypatch, rows=[[1]])
    module.add("bad!!name", "auth@or", "note", 0)
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___player_notes")]
    assert "'Badname'" in insert_queries[0]
    assert "'Author'" in insert_queries[0]


def test_add_class_ban_maps_to_1(bot, monkeypatch):
    module = make_player_notes(bot, monkeypatch, rows=[[1]])
    module.add("Player", "Author", "note", "ban")
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___player_notes")]
    assert ", 1, " in insert_queries[0]


def test_add_class_unrecognized_defaults_to_0(bot, monkeypatch):
    module = make_player_notes(bot, monkeypatch, rows=[[1]])
    module.add("Player", "Author", "note", "bogus")
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___player_notes")]
    assert ", 0, " in insert_queries[0]


def test_add_class_numeric_above_3_is_clamped(bot, monkeypatch):
    module = make_player_notes(bot, monkeypatch, rows=[[1]])
    module.add("Player", "Author", "note", 9)
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___player_notes")]
    assert ", 3, " in insert_queries[0]


def test_add_truncates_long_notes(bot, monkeypatch):
    module = make_player_notes(bot, monkeypatch, rows=[[1]])
    long_note = "x" * 300
    result = module.add("Player", "Author", long_note, 0)
    assert "x" * 254 in result
    assert "x" * 255 not in result


def test_add_query_failure_returns_bot_error(bot, monkeypatch):
    module = make_player_notes(bot, monkeypatch, rows=[[1]])
    monkeypatch.setattr(bot.db, "query", lambda sql: False)
    result = module.add("Player", "Author", "note", 0)
    assert isinstance(result, BotError)
    assert "unknown error" in result.get()


# -- delete ------------------------------------------------------------------

def test_delete_success_returns_confirmation(bot, monkeypatch):
    module = make_player_notes(bot, monkeypatch)
    monkeypatch.setattr(bot.db, "return_query", lambda sql: object())
    result = module.delete(5)
    assert result == "Deleted player note 5"


def test_delete_not_found_returns_bot_error(bot, monkeypatch):
    module = make_player_notes(bot, monkeypatch)
    monkeypatch.setattr(bot.db, "return_query", lambda sql: False)
    result = module.delete(999)
    assert isinstance(result, BotError)
    assert "999" in result.get()


# -- update ------------------------------------------------------------------

def test_update_non_int_pnid_returns_bot_error(bot, monkeypatch):
    module = make_player_notes(bot, monkeypatch)
    result = module.update("abc", "note", "new text")
    assert isinstance(result, BotError)
    assert "integers" in result.get()


def test_update_success_returns_none(bot, monkeypatch):
    module = make_player_notes(bot, monkeypatch)
    result = module.update(3, "note", "new text")
    assert result is None
    assert any("UPDATE #___player_notes SET note = new text WHERE pnid = 3" in q for q in bot.db.queries)


def test_update_query_failure_returns_bot_error(bot, monkeypatch):
    module = make_player_notes(bot, monkeypatch)
    monkeypatch.setattr(bot.db, "query", lambda sql: False)
    result = module.update(3, "note", "new text")
    assert isinstance(result, BotError)


# -- get_notes -----------------------------------------------------------------

def test_get_notes_no_notes_returns_bot_error(bot, monkeypatch):
    module = make_player_notes(bot, monkeypatch, rows=[])
    result = module.get_notes("Requester", "SomePlayer")
    assert isinstance(result, BotError)
    assert "Someplayer" in result.get()
    assert result.is_error is True


def test_get_notes_returns_rows_for_leader(bot, monkeypatch):
    rows = [{"pnid": 1, "player": "Someplayer", "class": 1}]
    module = make_player_notes(bot, monkeypatch, rows=rows, access=True)
    result = module.get_notes("Leaderguy", "someplayer")
    assert result == rows


def test_get_notes_filters_by_player_in_query(bot, monkeypatch):
    module = make_player_notes(bot, monkeypatch, rows=[{"pnid": 1}])
    captured = {}

    def fake_select(sql, as_dict=False):
        captured["sql"] = sql
        return [{"pnid": 1}]

    monkeypatch.setattr(bot.db, "select", fake_select)
    module.get_notes("Requester", "someplayer")
    assert "player = 'Someplayer'" in captured["sql"]


def test_get_notes_non_leader_only_sees_general_notes(bot, monkeypatch):
    module = make_player_notes(bot, monkeypatch, rows=[{"pnid": 1}], access=False)
    captured = {}

    def fake_select(sql, as_dict=False):
        captured["sql"] = sql
        return [{"pnid": 1}]

    monkeypatch.setattr(bot.db, "select", fake_select)
    module.get_notes("NonLeader")
    assert "class = 0" in captured["sql"]


def test_get_notes_leader_does_not_restrict_class(bot, monkeypatch):
    module = make_player_notes(bot, monkeypatch, rows=[{"pnid": 1}], access=True)
    captured = {}

    def fake_select(sql, as_dict=False):
        captured["sql"] = sql
        return [{"pnid": 1}]

    monkeypatch.setattr(bot.db, "select", fake_select)
    module.get_notes("Leaderguy")
    assert "class = 0" not in captured["sql"]


def test_get_notes_with_specific_pnid_filters_query(bot, monkeypatch):
    module = make_player_notes(bot, monkeypatch, rows=[{"pnid": 4}])
    captured = {}

    def fake_select(sql, as_dict=False):
        captured["sql"] = sql
        return [{"pnid": 4}]

    monkeypatch.setattr(bot.db, "select", fake_select)
    module.get_notes("Requester", "All", 4)
    assert "pnid = 4" in captured["sql"]


def test_get_notes_orders_descending_when_requested(bot, monkeypatch):
    module = make_player_notes(bot, monkeypatch, rows=[{"pnid": 4}])
    captured = {}

    def fake_select(sql, as_dict=False):
        captured["sql"] = sql
        return [{"pnid": 4}]

    monkeypatch.setattr(bot.db, "select", fake_select)
    module.get_notes("Requester", "All", "all", "DESC")
    assert captured["sql"].strip().endswith("ORDER BY pnid DESC")
