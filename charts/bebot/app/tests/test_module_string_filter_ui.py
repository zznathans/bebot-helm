from bebot.commodities.base import BotError
from bebot.main_modules.settings import Settings
from bebot.main_modules.string_filter import StringFilter
from bebot.main_modules.string_filter_ui import StringFilterUi
from bebot.main_modules.tools import Tools


class FakeFunFilters:
    """Local stand-in for bot.core("funfilters"), unused by these tests but
    required by StringFilter's constructor (registers "Funmode" setting
    whose value is never non-"off" here, so none of its methods actually
    get called).
    """

    def __getattr__(self, name):
        raise AssertionError(f"unexpected funfilters.{name}() call")


def make_string_filter_ui(bot, monkeypatch, rows=None):
    def fake_select(sql):
        if "string_filter" in sql:
            return rows or []
        return []

    monkeypatch.setattr(bot.db, "select", fake_select)
    bot.register_module(FakeFunFilters(), "funfilters")
    Tools(bot)
    Settings(bot)
    StringFilter(bot)
    bot.core("stringfilter").connect()
    return StringFilterUi(bot)


# -- construction --------------------------------------------------------------

def test_registers_as_string_filter_ui_module(bot, monkeypatch):
    module = make_string_filter_ui(bot, monkeypatch)
    assert bot.core("string_filter_ui") is module


def test_registers_filter_command(bot, monkeypatch):
    make_string_filter_ui(bot, monkeypatch)
    assert bot.commands["tell"]["filter"] is bot.core("string_filter_ui")
    assert bot.commands["gc"]["filter"] is bot.core("string_filter_ui")
    assert bot.commands["pgmsg"]["filter"] is bot.core("string_filter_ui")


def test_help_metadata(bot, monkeypatch):
    module = make_string_filter_ui(bot, monkeypatch)
    assert "filter" in module.help["description"].lower()
    assert "filter add <string>" in module.help["command"]
    assert "filter rem <string>" in module.help["command"]


# -- show (bare "filter") --------------------------------------------------------

def test_show_with_empty_list(bot, monkeypatch):
    module = make_string_filter_ui(bot, monkeypatch)
    result = module.command_handler("Player", "filter", "tell")
    assert isinstance(result, str)
    assert "Filtered String List" in result
    # make_blob wraps it in a text:// link
    assert result.startswith('<a href="text://')


def test_show_lists_configured_strings(bot, monkeypatch):
    module = make_string_filter_ui(bot, monkeypatch, rows=[("badword", "**bleep**")])
    result = module.command_handler("Player", "filter", "tell")
    assert "badword" in result
    assert "**bleep**" in result
    assert "filter rem badword" in result


def test_show_includes_remove_link_per_entry(bot, monkeypatch):
    module = make_string_filter_ui(
        bot, monkeypatch, rows=[("foo", "bar"), ("baz", "**bleep**")]
    )
    result = module.command_handler("Player", "filter", "tell")
    assert "filter rem foo" in result
    assert "filter rem baz" in result


# -- add: "filter add <string>" --------------------------------------------------

def test_add_without_replacement(bot, monkeypatch):
    module = make_string_filter_ui(bot, monkeypatch)
    result = module.command_handler("Player", "filter add badword", "tell")
    assert result == "Added 'badword' to the filterd string list. It will be replaced with '**bleep**'"
    assert bot.core("stringfilter").stringlist["badword"] == "**bleep**"


def test_add_with_replacement(bot, monkeypatch):
    module = make_string_filter_ui(bot, monkeypatch)
    result = module.command_handler("Player", "filter add badword replace: nicer", "tell")
    assert result == "Added 'badword' to the filterd string list. It will be replaced with 'nicer'"
    assert bot.core("stringfilter").stringlist["badword"] == "nicer"


def test_add_with_spaces_in_string(bot, monkeypatch):
    module = make_string_filter_ui(bot, monkeypatch)
    result = module.command_handler("Player", "filter add some bad phrase", "tell")
    assert "some bad phrase" in result
    assert "some bad phrase" in bot.core("stringfilter").stringlist


def test_add_with_spaces_in_both_string_and_replacement(bot, monkeypatch):
    module = make_string_filter_ui(bot, monkeypatch)
    result = module.command_handler(
        "Player", "filter add some bad phrase replace: something nicer", "tell"
    )
    assert result == (
        "Added 'some bad phrase' to the filterd string list. "
        "It will be replaced with 'something nicer'"
    )
    assert bot.core("stringfilter").stringlist["some bad phrase"] == "something nicer"


def test_add_duplicate_returns_error(bot, monkeypatch):
    module = make_string_filter_ui(bot, monkeypatch, rows=[("badword", "**bleep**")])
    result = module.command_handler("Player", "filter add badword", "tell")
    assert isinstance(result, BotError)
    assert "already on the filtered word list" in result.get()


def test_add_is_case_insensitive_command_match(bot, monkeypatch):
    module = make_string_filter_ui(bot, monkeypatch)
    result = module.command_handler("Player", "FILTER ADD badword", "tell")
    assert "Added 'badword'" in result


# -- rem: "filter rem <string>" --------------------------------------------------

def test_rem_existing_string(bot, monkeypatch):
    module = make_string_filter_ui(bot, monkeypatch, rows=[("badword", "**bleep**")])
    result = module.command_handler("Player", "filter rem badword", "tell")
    assert result == "Removed badword from the filtered string list."
    assert "badword" not in bot.core("stringfilter").stringlist


def test_rem_unknown_string_returns_error(bot, monkeypatch):
    module = make_string_filter_ui(bot, monkeypatch)
    result = module.command_handler("Player", "filter rem nope", "tell")
    assert isinstance(result, BotError)
    assert "is not on the filtered string list" in result.get()


def test_rem_with_spaces_in_string(bot, monkeypatch):
    module = make_string_filter_ui(
        bot, monkeypatch, rows=[("some bad phrase", "**bleep**")]
    )
    result = module.command_handler("Player", "filter rem some bad phrase", "tell")
    assert result == "Removed some bad phrase from the filtered string list."


# -- dispatch precedence ---------------------------------------------------------

def test_add_replace_pattern_takes_precedence_over_plain_add(bot, monkeypatch):
    # "replace: " in the message must be consumed by the add+replace regex,
    # not swallowed as part of the plain <string> capture.
    module = make_string_filter_ui(bot, monkeypatch)
    result = module.command_handler("Player", "filter add foo replace: bar", "tell")
    assert bot.core("stringfilter").stringlist["foo"] == "bar"
    assert result == "Added 'foo' to the filterd string list. It will be replaced with 'bar'"


def test_unrecognized_filter_message_falls_back_to_show(bot, monkeypatch):
    module = make_string_filter_ui(bot, monkeypatch, rows=[("badword", "**bleep**")])
    result = module.command_handler("Player", "filter", "tell")
    assert "Filtered String List" in result
