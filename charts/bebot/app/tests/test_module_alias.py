import re

from bebot.commodities.base import BotError
from bebot.main_modules.alias import Alias
from bebot.main_modules.alts import Alts
from bebot.main_modules.tools import Tools
from fakes import FakePlayer


class FakeAlts:
    """Local stand-in for core("alts") used when testing Alias in isolation.

    `main()` mimics Alts.main(): looks a character up in a mains map,
    falling back to the (capitalized) name itself if it isn't a known alt.
    """

    def __init__(self, mains=None, alts=None):
        self.mains = dict(mains or {})
        self.alts = dict(alts or {})

    def main(self, name: str) -> str:
        name = str(name).capitalize()
        return self.mains.get(name, name)

    def get_alts(self, main: str):
        return self.alts.get(main, [])


def _fake_alias_select(table):
    """Builds a `bot.db.select()` stand-in that understands the three query
    shapes Alias.php's port issues against #___alias: the full-table scan
    used by create_caches(), and the two "WHERE alias = 'x'" lookups used
    by add_alias()/del_alias()/del_alias_admin() (which select different
    column subsets). `table` is a list of (alias, nickname, main) rows.
    """

    def fake_select(sql, *a, **kw):
        if "alias, nickname, main FROM #___alias" in sql:
            return list(table)
        match = re.search(r"alias = '([^']*)'", sql)
        if not match:
            return []
        matches = [row for row in table if row[0] == match.group(1)]
        if "SELECT nickname, main" in sql:
            return [(row[1], row[2]) for row in matches]
        if "SELECT nickname" in sql:
            return [(row[1],) for row in matches]
        return []

    return fake_select


def make_alias(bot, monkeypatch, rows=None, player=None, alts=None) -> Alias:
    """Builds an Alias module with its cache pre-populated from `rows`.

    Unlike Alts.py (which fills its caches straight from __init__), the
    ported Alias only (re)builds self.alias/self.main in create_caches(),
    which the PHP original only invokes off the "connect" event -- so this
    helper mimics the bot having already fired that event once, the way it
    would have by the time players can run the `alias` command for real.
    """
    Tools(bot)
    bot.register_module(player or FakePlayer(), "player")
    bot.register_module(alts or FakeAlts(), "alts")
    monkeypatch.setattr(bot.db, "select", _fake_alias_select([] if rows is None else list(rows)))
    module = Alias(bot)
    module.connect()
    return module


# -- construction --------------------------------------------------------------

def test_creates_table_on_construction(bot, monkeypatch):
    make_alias(bot, monkeypatch)
    create_queries = [q for q in bot.db.queries if "CREATE TABLE" in q]
    assert len(create_queries) == 1
    assert "alias" in create_queries[0]
    assert "nickname" in create_queries[0]


def test_registers_as_alias_module(bot, monkeypatch):
    module = make_alias(bot, monkeypatch)
    assert bot.core("alias") is module


def test_registers_alias_command(bot, monkeypatch):
    make_alias(bot, monkeypatch)
    assert bot.commands["tell"]["alias"] is bot.core("alias")


# -- create_caches ------------------------------------------------------------

def test_create_caches_builds_alias_and_main_maps(bot, monkeypatch):
    rows = [("Foo", "Somechar", 1), ("Bar", "Somechar", 0)]
    module = make_alias(bot, monkeypatch, rows=rows)
    assert module.alias == {"foo": "Somechar", "bar": "Somechar"}
    assert module.main == {"Somechar": "Foo"}


def test_connect_event_rebuilds_caches(bot, monkeypatch):
    module = make_alias(bot, monkeypatch, rows=[])
    assert module.alias == {}
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [("Foo", "Somechar", 1)])
    module.connect()
    assert module.alias == {"foo": "Somechar"}
    assert module.main == {"Somechar": "Foo"}


# -- add_alias ------------------------------------------------------------------

def test_add_alias_unknown_player_returns_error(bot, monkeypatch):
    player = FakePlayer(ids={})

    class _Player(FakePlayer):
        def id(self, name):
            return BotError(bot, "player")

    module = make_alias(bot, monkeypatch, player=_Player())
    result = module.add_alias("Nobody", "Foobar")
    assert "does not exist" in result


def test_add_alias_too_short_returns_error(bot, monkeypatch):
    module = make_alias(bot, monkeypatch)
    result = module.add_alias("Somechar", "ab")
    assert "too Short" in result


def test_add_alias_success_sets_as_main_and_updates_cache(bot, monkeypatch):
    module = make_alias(bot, monkeypatch)
    result = module.add_alias("somechar", "Foobar")
    assert "Added as Alias of" in result
    assert "set as Main Alias" in result
    assert module.alias["foobar"] == "Somechar"
    assert module.main["Somechar"] == "Foobar"
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___alias")]
    assert len(insert_queries) == 1
    assert "'Foobar', 'Somechar', 1" in insert_queries[0]


def test_add_second_alias_not_marked_main(bot, monkeypatch):
    module = make_alias(bot, monkeypatch)
    module.add_alias("Somechar", "Foobar")
    result = module.add_alias("Somechar", "Bazqux")
    assert "set as Main Alias" not in result
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___alias")]
    assert "'Bazqux', 'Somechar', 0" in insert_queries[1]


def test_add_alias_uses_alts_main(bot, monkeypatch):
    alts = FakeAlts(mains={"Altchar": "Mainchar"})
    module = make_alias(bot, monkeypatch, alts=alts)
    result = module.add_alias("Altchar", "Foobar")
    assert "Added as Alias of ##highlight##Mainchar##end##" in result


def test_add_alias_already_taken_returns_owner(bot, monkeypatch):
    module = make_alias(bot, monkeypatch, rows=[("Foobar", "Otherchar", 1)])
    result = module.add_alias("Somechar", "Foobar")
    assert "is Already an Alias off ##highlight##Otherchar" in result


# -- del_alias --------------------------------------------------------------

def test_del_alias_owned_by_caller_deletes(bot, monkeypatch):
    module = make_alias(bot, monkeypatch, rows=[("foobar", "Somechar", 1)])
    result = module.del_alias("Somechar", "foobar")
    assert "Deleted" in result
    assert "foobar" not in module.alias
    assert "Somechar" not in module.main
    assert any("DELETE FROM #___alias WHERE alias = 'foobar'" in q for q in bot.db.queries)


def test_del_alias_owned_by_someone_else_denied(bot, monkeypatch):
    module = make_alias(bot, monkeypatch, rows=[("foobar", "Otherchar", 0)])
    result = module.del_alias("Somechar", "foobar")
    assert "can not be Deleted by you" in result


def test_del_alias_not_found(bot, monkeypatch):
    module = make_alias(bot, monkeypatch, rows=[])
    result = module.del_alias("Somechar", "foobar")
    assert "Not found" in result


# -- del_alias_admin -----------------------------------------------------------

def test_del_alias_admin_deletes_regardless_of_owner(bot, monkeypatch):
    module = make_alias(bot, monkeypatch, rows=[("foobar", "Somechar", 1)])
    result = module.del_alias_admin("foobar")
    assert "Deleted" in result
    assert "foobar" not in module.alias
    assert "Somechar" not in module.main


def test_del_alias_admin_not_found(bot, monkeypatch):
    module = make_alias(bot, monkeypatch, rows=[])
    result = module.del_alias_admin("foobar")
    assert "Not found" in result


# -- get_alias ------------------------------------------------------------------

def test_get_alias_no_aliases_found(bot, monkeypatch):
    module = make_alias(bot, monkeypatch, rows=[])
    result = module.get_alias("Somechar")
    assert "No Alias's Found" in result


def test_get_alias_filters_by_main(bot, monkeypatch):
    rows = [("foo", "Somechar", 1), ("bar", "Otherchar", 1)]
    module = make_alias(bot, monkeypatch, rows=rows)
    result = module.get_alias("Somechar")
    assert "foo" in result
    assert "bar" not in result
    assert "Alias List :: Somechar and Alts ::" in result


def test_get_alias_list_shows_all(bot, monkeypatch):
    rows = [("foo", "Somechar", 1), ("bar", "Otherchar", 1)]
    module = make_alias(bot, monkeypatch, rows=rows)
    result = module.get_alias("list")
    assert "foo" in result
    assert "bar" in result
    assert result.startswith("Alias List :: ")
    assert "and Alts" not in result


# -- set_main -------------------------------------------------------------------

def test_set_main_already_main_alias(bot, monkeypatch):
    rows = [("foobar", "Somechar", 1)]
    module = make_alias(bot, monkeypatch, rows=rows)
    result = module.set_main("Somechar", "foobar")
    assert "is Already you main alias" in result


def test_set_main_switches_between_own_aliases(bot, monkeypatch):
    rows = [("foobar", "Somechar", 1), ("bazqux", "Somechar", 0)]
    module = make_alias(bot, monkeypatch, rows=rows)
    result = module.set_main("Somechar", "bazqux")
    assert result == "Alias Main set"
    update_queries = [q for q in bot.db.queries if q.startswith("UPDATE")]
    assert any("main = 0 WHERE nickname = 'Somechar'" in q for q in update_queries)
    assert any("main = 1 WHERE alias = 'bazqux'" in q for q in update_queries)


def test_set_main_not_your_alias_rejected(bot, monkeypatch):
    rows = [("foobar", "Somechar", 1), ("bazqux", "Otherchar", 1)]
    module = make_alias(bot, monkeypatch, rows=rows)
    result = module.set_main("Somechar", "bazqux")
    assert "cannot be set as main" in result


def test_set_main_no_existing_main_uses_alts(bot, monkeypatch):
    rows = [("foobar", "Somechar", 0)]
    alts = FakeAlts(alts={"Somechar": ["Somealt"]})
    module = make_alias(bot, monkeypatch, rows=rows, alts=alts)
    result = module.set_main("Somechar", "foobar")
    assert result == "Alias Main set"
    update_queries = [q for q in bot.db.queries if q.startswith("UPDATE")]
    assert any(
        "main = 0 WHERE nickname = 'Somechar' OR nickname = 'Somealt'" in q
        for q in update_queries
    )


def test_set_main_alias_not_found(bot, monkeypatch):
    module = make_alias(bot, monkeypatch, rows=[])
    result = module.set_main("Somechar", "nope")
    assert result == "Alias not Found"


# -- get_main -------------------------------------------------------------------

def test_get_main_known(bot, monkeypatch):
    rows = [("foobar", "Somechar", 1)]
    module = make_alias(bot, monkeypatch, rows=rows)
    assert module.get_main("Somechar") == "foobar"


def test_get_main_unknown_returns_false(bot, monkeypatch):
    module = make_alias(bot, monkeypatch, rows=[])
    assert module.get_main("Somechar") is False


# -- command_handler -----------------------------------------------------------

def test_command_handler_add_dispatches(bot, monkeypatch):
    module = make_alias(bot, monkeypatch)
    result = module.command_handler("Somechar", "alias add Foobar", "tell")
    assert "Added as Alias of" in result


def test_command_handler_del_and_rem_dispatch(bot, monkeypatch):
    module = make_alias(bot, monkeypatch, rows=[("foobar", "Somechar", 1)])
    result = module.command_handler("Somechar", "alias del foobar", "tell")
    assert "Deleted" in result


def test_command_handler_no_args_shows_own_alias(bot, monkeypatch):
    rows = [("foobar", "Somechar", 1)]
    module = make_alias(bot, monkeypatch, rows=rows)
    result = module.command_handler("Somechar", "alias", "tell")
    assert "Alias List :: Somechar and Alts ::" in result


def test_command_handler_name_arg_shows_that_name(bot, monkeypatch):
    rows = [("foobar", "Otherchar", 1)]
    module = make_alias(bot, monkeypatch, rows=rows)
    result = module.command_handler("Somechar", "alias Otherchar", "tell")
    assert "Alias List :: Otherchar and Alts ::" in result
    assert "foobar" in result


def test_command_handler_admin_add(bot, monkeypatch):
    module = make_alias(bot, monkeypatch)
    result = module.command_handler("Adminguy", "alias admin add somechar Foobar", "tell")
    assert "Added as Alias of ##highlight##Somechar" in result


def test_command_handler_admin_del(bot, monkeypatch):
    module = make_alias(bot, monkeypatch, rows=[("foobar", "Somechar", 1)])
    result = module.command_handler("Adminguy", "alias admin del foobar", "tell")
    assert "Deleted" in result


def test_command_handler_admin_unknown_subcommand(bot, monkeypatch):
    module = make_alias(bot, monkeypatch)
    result = module.command_handler("Adminguy", "alias admin bogus foobar", "tell")
    assert "Unknown Subcommand of alias admin" in result


# -- integration with the real Alts module --------------------------------------

def test_integration_with_real_alts_module(bot, monkeypatch):
    """Register the real, already-ported Alts module alongside Alias to make
    sure the two actually interoperate (alts->main() normalization, etc.)."""
    from fakes import FakeSettings

    class _FakeSettingsWithCreate(FakeSettings):
        def create(self, module, setting, value, longdesc, defaultoptions="", hidden=False, disporder=1):
            self._values.setdefault((module, setting), value)

    Tools(bot)
    bot.register_module(_FakeSettingsWithCreate(), "settings")
    bot.register_module(FakePlayer(), "player")

    select_rows = {"alts": [("Mainchar", "Altchar")], "alias": []}

    def fake_select(sql, *a, **kw):
        if "#___alts" in sql:
            return select_rows["alts"]
        if "#___alias" in sql:
            return select_rows["alias"]
        return []

    monkeypatch.setattr(bot.db, "select", fake_select)

    Alts(bot)
    alias_module = Alias(bot)

    # Adding an alias for the alt should attribute it to the main character.
    result = alias_module.add_alias("Altchar", "Foobar")
    assert "Added as Alias of ##highlight##Mainchar##end##" in result
    assert alias_module.main["Mainchar"] == "Foobar"

    # Looking it up by the alt's name should resolve through alts.main().
    listing = alias_module.get_alias("Altchar")
    assert "foobar" in listing
