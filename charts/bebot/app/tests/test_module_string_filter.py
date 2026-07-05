from bebot.commodities.base import BotError
from bebot.main_modules.settings import Settings
from bebot.main_modules.string_filter import StringFilter


class FakeFunFilters:
    """Local stand-in for bot.core("funfilters") -- the real module is being
    ported in parallel by another engineer. Each stub method returns a
    recognizable marker so tests can assert StringFilter calls the right
    method with the right argument.
    """

    def rot13(self, text):
        return f"ROT13({text})"

    def chef(self, text):
        return f"CHEF({text})"

    def eleet(self, text):
        return f"ELEET({text})"

    def fudd(self, text):
        return f"FUDD({text})"

    def pirate(self, text):
        return f"PIRATE({text})"

    def nofont(self, text):
        return f"NOFONT({text})"


def make_string_filter(bot, monkeypatch, rows=None):
    def fake_select(sql):
        if "string_filter" in sql:
            return rows or []
        return []

    monkeypatch.setattr(bot.db, "select", fake_select)
    bot.register_module(FakeFunFilters(), "funfilters")
    Settings(bot)
    return StringFilter(bot)


# -- construction --------------------------------------------------------------

def test_creates_table_and_registers_module(bot, monkeypatch):
    module = make_string_filter(bot, monkeypatch)
    create_queries = [q for q in bot.db.queries if "CREATE TABLE" in q and "string_filter" in q]
    assert len(create_queries) == 1
    assert bot.core("stringfilter") is module


def test_creates_settings(bot, monkeypatch):
    make_string_filter(bot, monkeypatch)
    settings = bot.core("settings")
    assert settings.get("Filter", "Enabled") is False
    assert settings.get("Filter", "Funmode") == "off"


# -- get_strings / connect ------------------------------------------------------

def test_get_strings_without_update_returns_current_cache(bot, monkeypatch):
    module = make_string_filter(bot, monkeypatch)
    assert module.get_strings() == {}


def test_connect_loads_strings_from_db(bot, monkeypatch):
    module = make_string_filter(bot, monkeypatch, rows=[("badword", "**bleep**")])
    module.connect()
    assert module.stringlist == {"badword": "**bleep**"}


def test_get_strings_update_with_no_rows_returns_false(bot, monkeypatch):
    module = make_string_filter(bot, monkeypatch, rows=[])
    assert module.get_strings(True) is False


# -- output_filter / input_filter -----------------------------------------------

def test_output_filter_replaces_configured_strings(bot, monkeypatch):
    module = make_string_filter(bot, monkeypatch, rows=[("badword", "**bleep**")])
    module.connect()
    assert module.output_filter("this is a badword here") == "this is a **bleep** here"


def test_output_filter_is_case_insensitive(bot, monkeypatch):
    module = make_string_filter(bot, monkeypatch, rows=[("badword", "**bleep**")])
    module.connect()
    assert module.output_filter("BADWORD") == "**bleep**"


def test_output_filter_applies_funmode_when_enabled(bot, monkeypatch):
    module = make_string_filter(bot, monkeypatch)
    bot.core("settings").save("Filter", "Funmode", "chef")
    assert module.output_filter("hello") == "CHEF(hello)"


def test_output_filter_skips_funmode_when_off(bot, monkeypatch):
    module = make_string_filter(bot, monkeypatch)
    assert module.output_filter("hello") == "hello"


def test_input_filter_replaces_configured_strings(bot, monkeypatch):
    module = make_string_filter(bot, monkeypatch, rows=[("badword", "**bleep**")])
    module.connect()
    assert module.input_filter("a badword input") == "a **bleep** input"


# -- funmode ---------------------------------------------------------------------

def test_funmode_dispatches_to_correct_funfilters_method(bot, monkeypatch):
    module = make_string_filter(bot, monkeypatch)
    assert module.funmode("hi", "rot13") == "ROT13(hi)"
    assert module.funmode("hi", "chef") == "CHEF(hi)"
    assert module.funmode("hi", "eleet") == "ELEET(hi)"
    assert module.funmode("hi", "fudd") == "FUDD(hi)"
    assert module.funmode("hi", "pirate") == "PIRATE(hi)"
    assert module.funmode("hi", "nofont") == "NOFONT(hi)"


def test_funmode_is_case_insensitive(bot, monkeypatch):
    module = make_string_filter(bot, monkeypatch)
    assert module.funmode("hi", "CHEF") == "CHEF(hi)"


def test_funmode_invalid_filter_returns_text_unchanged(bot, monkeypatch):
    module = make_string_filter(bot, monkeypatch)
    assert module.funmode("hi", "bogus") == "hi"


# -- add_string / rem_string -----------------------------------------------------

def test_add_string_with_explicit_replacement(bot, monkeypatch):
    module = make_string_filter(bot, monkeypatch)
    result = module.add_string("badword", "nicer")
    assert result == "Added 'badword' to the filterd string list. It will be replaced with 'nicer'"
    assert module.stringlist["badword"] == "nicer"
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___string_filter")]
    assert any("badword" in q and "nicer" in q for q in insert_queries)


def test_add_string_without_replacement_defaults_to_bleep(bot, monkeypatch):
    module = make_string_filter(bot, monkeypatch)
    result = module.add_string("badword")
    assert "**bleep**" in result
    assert module.stringlist["badword"] == "**bleep**"


def test_add_string_lowercases_search(bot, monkeypatch):
    module = make_string_filter(bot, monkeypatch)
    module.add_string("BadWord")
    assert "badword" in module.stringlist


def test_add_string_duplicate_returns_error(bot, monkeypatch):
    module = make_string_filter(bot, monkeypatch, rows=[("badword", "**bleep**")])
    module.connect()
    result = module.add_string("badword")
    assert isinstance(result, BotError)
    assert "already on the filtered word list" in result.get()


def test_rem_string_removes_existing(bot, monkeypatch):
    module = make_string_filter(bot, monkeypatch, rows=[("badword", "**bleep**")])
    module.connect()
    result = module.rem_string("badword")
    assert result == "Removed badword from the filtered string list."
    assert "badword" not in module.stringlist
    assert any("DELETE FROM #___string_filter WHERE search = 'badword'" in q for q in bot.db.queries)


def test_rem_string_unknown_returns_error(bot, monkeypatch):
    module = make_string_filter(bot, monkeypatch)
    result = module.rem_string("nope")
    assert isinstance(result, BotError)
    assert "is not on the filtered string list" in result.get()
