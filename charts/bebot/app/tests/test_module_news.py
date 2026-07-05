from bebot.commodities.base import BotError
from bebot.main_modules.command_alias import CommandAlias
from bebot.main_modules.news import News
from bebot.main_modules.preferences import Preferences
from bebot.main_modules.security import Security
from bebot.main_modules.settings import Settings
from bebot.main_modules.tools import Tools
from fakes import FakeAccessControl, FakeLogonNotifies, FakePlayer


class _FakeAccessControlWithCreate(FakeAccessControl):
    """FakeAccessControl doesn't implement create() -- register_command()
    calls it to register the access level required for each command."""

    def create(self, channel, command, access):
        pass

    def create_subcommand(self, channel, command, sub, defaultlevel):
        pass


class FakeNewsDb:
    """Answers the #___news read-only queries News issues from small
    in-memory row lists the test sets up; every other query (setup CREATE
    TABLEs, settings/prefs/security housekeeping) behaves like the default
    fixture fake (empty result / accepted no-op)."""

    def __init__(self, headlines=None, news=None, raids=None):
        self.headlines = headlines or []
        self.news = news or []
        self.raids = raids or []
        self.queries: list[str] = []

    def query(self, sql: str) -> bool:
        self.queries.append(sql)
        return True

    def select(self, sql: str, as_dict: bool = False):
        if "#___news" in sql:
            if "type = '2'" in sql and "LIMIT 0, 3" in sql:
                return list(self.headlines)
            if "type = '2'" in sql and "LIMIT 1" in sql:
                return [(row[2], row[3]) for row in self.headlines[:1]]
            if "type = '1'" in sql:
                return list(self.news)
            if "type = '3'" in sql and "id DESC" in sql:
                return list(self.raids[:1])
            if "type = '3'" in sql:
                return list(self.raids)
            if "WHERE id = " in sql:
                entry_id = sql.rsplit("'", 2)[-2]
                for row in self.headlines + self.news + self.raids:
                    if str(row[0]) == entry_id:
                        return [(row[2],)]
                return []
        return []

    def real_escape_string(self, value) -> str:
        return str(value).replace("'", "\\'")

    def define_tablename(self, table: str, use_prefix) -> str:
        return table


def make_news(bot, monkeypatch, headlines=None, news=None, raids=None):
    fake_db = FakeNewsDb(headlines=headlines, news=news, raids=raids)
    monkeypatch.setattr(bot, "db", fake_db)
    bot.register_module(_FakeAccessControlWithCreate(), "access_control")
    bot.register_module(FakePlayer(ids={"Author": 1, "Someone": 2, "Deleter": 3}), "player")
    bot.register_module(FakeLogonNotifies(), "logon_notifies")
    Tools(bot)
    Settings(bot)
    CommandAlias(bot)
    Security(bot)
    Preferences(bot)
    module = News(bot)
    # Preferences.create() only touches the DB, not the in-memory "def"
    # cache used by get() (see preferences.py's docstring) -- normally
    # populated by Preferences.connect() re-querying #___preferences_def,
    # which this lightweight fake db doesn't model. Seed it directly with
    # what News.__init__() defines instead.
    bot.core("prefs").cache["def"] = {
        "news": {"logonspam": "Last_headline", "pgjoinspam": "Nothing"},
    }
    return module, fake_db


# -- construction / registration --------------------------------------------------

def test_registers_as_news_module(bot, monkeypatch):
    module, _ = make_news(bot, monkeypatch)
    assert bot.core("news") is module


def test_registers_commands_on_all_channels(bot, monkeypatch):
    module, _ = make_news(bot, monkeypatch)
    for channel in ("tell", "gc", "pgmsg"):
        assert bot.commands[channel]["news"] is module
        assert bot.commands[channel]["headline"] is module
        assert bot.commands[channel]["raids"] is module


def test_help_describes_commands(bot, monkeypatch):
    module, _ = make_news(bot, monkeypatch)
    assert "news" in module.help["command"]
    assert "raids" in module.help["command"]


# -- command_handler dispatch -------------------------------------------------------

def test_command_handler_news_read(bot, monkeypatch):
    module, _ = make_news(bot, monkeypatch)
    result = module.command_handler("Someone", "news", "tell")
    assert result == "No news."


def test_command_handler_unknown_command(bot, monkeypatch):
    module, _ = make_news(bot, monkeypatch)
    result = module.command_handler("Someone", "bogus", "tell")
    assert isinstance(result, BotError)
    assert "unknown command" in result.get()


def test_command_handler_headline_dispatches_to_news_view(bot, monkeypatch):
    module, _ = make_news(bot, monkeypatch)
    result = module.command_handler("Someone", "headline", "tell")
    assert result == "No news."


def test_command_handler_raids_dispatches_to_raids_view(bot, monkeypatch):
    module, _ = make_news(bot, monkeypatch)
    result = module.command_handler("Someone", "raids", "tell")
    assert "Planned Raids" in result


def test_sub_handler_missing_add_keyword_still_adds(bot, monkeypatch):
    module, fake_db = make_news(bot, monkeypatch)
    result = module.command_handler("Author", "news forgot the keyword", "tell")
    assert result == "Your entry has been submitted."
    assert any("INSERT INTO #___news" in q for q in fake_db.queries)


# -- get_news / get_last_headline / get_raids ------------------------------------

def test_get_news_empty(bot, monkeypatch):
    module, _ = make_news(bot, monkeypatch)
    assert module.get_news("Someone") == "No news."


def test_get_news_renders_headline_and_news(bot, monkeypatch):
    module, _ = make_news(
        bot, monkeypatch,
        headlines=[(1, 1000, "Author", "Big headline")],
        news=[(2, 2000, "Author", "Regular news")],
    )
    result = module.get_news("Someone")
    assert "Headline" in result
    assert "Big headline" in result
    assert "Regular news" in result
    # The "News last updated" date is always blank -- preserved PHP quirk
    # ($result is read before it's assigned in the original get_news()).
    assert "News last updated :: " in result


def test_get_news_shows_delete_link_for_author(bot, monkeypatch):
    module, _ = make_news(
        bot, monkeypatch,
        news=[(2, 2000, "Author", "Regular news")],
    )
    result = module.get_news("Author")
    assert "news del 2" in result


def test_get_news_hides_delete_link_for_unprivileged_non_author(bot, monkeypatch):
    module, _ = make_news(
        bot, monkeypatch,
        news=[(2, 2000, "Author", "Regular news")],
    )
    result = module.get_news("Someone")
    assert "news del 2" not in result


def test_get_last_headline_false_when_none(bot, monkeypatch):
    module, _ = make_news(bot, monkeypatch)
    assert module.get_last_headline() is False


def test_get_last_headline_formats_name_and_text(bot, monkeypatch):
    module, _ = make_news(bot, monkeypatch, headlines=[(1, 1000, "Author", "Big headline")])
    result = module.get_last_headline()
    assert result == "Author:##highlight## Big headline##end##\n"


def test_get_raids_empty_still_returns_blob(bot, monkeypatch):
    module, _ = make_news(bot, monkeypatch)
    result = module.get_raids("Someone")
    assert "Planned Raids last updated" in result


def test_get_raids_renders_entries_with_date(bot, monkeypatch):
    module, _ = make_news(bot, monkeypatch, raids=[(5, 12345, "Author", "Raid Ankari at 8pm")])
    result = module.get_raids("Someone")
    assert "Raid Ankari at 8pm" in result
    assert "Planned Raids last updated :: " not in result  # newsdate IS populated here


# -- set_news / del_news --------------------------------------------------------

def test_set_news_inserts_row(bot, monkeypatch):
    module, fake_db = make_news(bot, monkeypatch)
    result = module.set_news("Author", "Something happened", 1)
    assert result == "Your entry has been submitted."
    assert any("Something happened" in q for q in fake_db.queries)


def test_del_news_missing_entry(bot, monkeypatch):
    module, _ = make_news(bot, monkeypatch)
    result = module.del_news("Author", "999")
    assert isinstance(result, BotError)
    assert "No entry with id '999' found." in result.get()


def test_del_news_owner_can_delete_own_entry(bot, monkeypatch):
    module, fake_db = make_news(bot, monkeypatch, news=[(2, 2000, "Author", "Regular news")])
    result = module.del_news("Author", "2")
    assert result == "Entry has been removed."
    assert any("DELETE FROM #___news" in q for q in fake_db.queries)


def test_del_news_denies_non_owner_without_access(bot, monkeypatch):
    module, fake_db = make_news(bot, monkeypatch, news=[(2, 2000, "Author", "Regular news")])
    result = module.del_news("Someone", "2")
    assert isinstance(result, BotError)
    assert "must be" in result.get()
    assert not any("DELETE FROM #___news" in q for q in fake_db.queries)


# -- notify / pgjoin (logon_notify + pgjoin event handlers) ----------------------

def test_notify_skips_during_startup_grace_period(bot, monkeypatch):
    module, _ = make_news(bot, monkeypatch, headlines=[(1, 1000, "Author", "Hi")])
    sent = []
    monkeypatch.setattr(bot, "send_output", lambda *a, **kw: sent.append(a))
    module.notify("Someone", startup=True)
    assert sent == []


def test_notify_last_headline_default_sends_tell(bot, monkeypatch):
    module, _ = make_news(bot, monkeypatch, headlines=[(1, 1000, "Author", "Big headline")])
    sent = []
    monkeypatch.setattr(bot, "send_output", lambda *a, **kw: sent.append(a))
    module.notify("Someone", startup=False)
    assert len(sent) == 1
    to, msg, kind = sent[0]
    assert to == "Someone"
    assert "Big headline" in msg
    assert kind == "tell"


def test_pgjoin_default_is_nothing_and_sends_no_message(bot, monkeypatch):
    module, _ = make_news(bot, monkeypatch, headlines=[(1, 1000, "Author", "Big headline")])
    sent = []
    monkeypatch.setattr(bot, "send_output", lambda *a, **kw: sent.append(a))
    module.pgjoin("Someone")
    assert sent == []
