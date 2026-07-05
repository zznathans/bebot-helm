from bebot.commodities.base import BotError
from bebot.main_modules.alts import Alts
from bebot.main_modules.tools import Tools
from fakes import FakePlayer, FakeSettings


class _FakeSettingsWithCreate(FakeSettings):
    """FakeSettings doesn't implement create() -- Alts.__init__ calls it to
    register its Output/Detail/LastSeen/Confirmation/incAll settings."""

    def create(self, module, setting, value, longdesc, defaultoptions="", hidden=False, disporder=1):
        self._values.setdefault((module, setting), value)


class FakeOnline:
    """Local stand-in for online.py used when testing Alts in isolation."""

    def __init__(self, states=None, last_seen=None):
        self.states = states or {}
        self.last_seen = last_seen or {}
        self.calls: list[tuple] = []

    def get_online_state(self, name):
        self.calls.append(("get_online_state", name))
        return self.states.get(name, {"content": "##white##Unknown##end##", "status": -1})

    def get_last_seen(self, name, checkalts=False):
        self.calls.append(("get_last_seen", name))
        return self.last_seen.get(name, False)


def make_alts(bot, monkeypatch, rows=None, settings=None, player=None, online=None) -> Alts:
    Tools(bot)
    bot.register_module(settings or _FakeSettingsWithCreate(), "settings")
    bot.register_module(player or FakePlayer(), "player")
    bot.register_module(online or FakeOnline(), "online")
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [] if rows is None else rows)
    return Alts(bot)


# -- construction --------------------------------------------------------------

def test_creates_table_on_construction(bot, monkeypatch):
    make_alts(bot, monkeypatch)
    create_queries = [q for q in bot.db.queries if "CREATE TABLE" in q]
    assert len(create_queries) == 1
    assert "alts" in create_queries[0]
    assert "confirmed" in create_queries[0]


def test_registers_as_alts_module(bot, monkeypatch):
    module = make_alts(bot, monkeypatch)
    assert bot.core("alts") is module


def test_creates_settings(bot, monkeypatch):
    settings = _FakeSettingsWithCreate()
    make_alts(bot, monkeypatch, settings=settings)
    assert settings.get("Alts", "Output") == "Fancy"
    assert settings.get("Alts", "Detail") is True
    assert settings.get("Alts", "LastSeen") is True
    assert settings.get("Alts", "Confirmation") is False
    assert settings.get("Alts", "incAll") is False


# -- create_caches / main / get_alts -------------------------------------------

def test_no_alts_registered_main_returns_self(bot, monkeypatch):
    module = make_alts(bot, monkeypatch, rows=[])
    assert module.main("Somechar") == "Somechar"
    assert module.get_alts("Somechar") == []


def test_create_caches_builds_main_and_alt_lookup(bot, monkeypatch):
    rows = [("Mainchar", "Altone"), ("Mainchar", "Alttwo"), ("Otherman", "Altthree")]
    module = make_alts(bot, monkeypatch, rows=rows)
    assert module.main("altone") == "Mainchar"
    assert module.main("ALTTWO") == "Mainchar"
    assert module.main("altthree") == "Otherman"
    assert module.get_alts("Mainchar") == ["Altone", "Alttwo"]
    assert module.get_alts("Otherman") == ["Altthree"]


def test_main_unknown_char_returns_normalized_self(bot, monkeypatch):
    module = make_alts(bot, monkeypatch, rows=[("Mainchar", "Altone")])
    assert module.main("nOTaCHAR") == "Notachar"


def test_get_alts_numeric_id_resolves_via_player(bot, monkeypatch):
    player = FakePlayer(names={42: "Mainchar"})
    module = make_alts(bot, monkeypatch, rows=[("Mainchar", "Altone")], player=player)
    assert module.get_alts(42) == ["Altone"]


def test_cron_rebuilds_caches(bot, monkeypatch):
    module = make_alts(bot, monkeypatch, rows=[("Mainchar", "Altone")])
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [("Mainchar", "Altone"), ("Mainchar", "Alttwo")])
    module.cron()
    assert module.get_alts("Mainchar") == ["Altone", "Alttwo"]


# -- add_alt / del_alt ----------------------------------------------------------

def test_add_alt_updates_caches(bot, monkeypatch):
    module = make_alts(bot, monkeypatch, rows=[])
    module.add_alt("mainchar", "altone")
    assert module.main("Altone") == "Mainchar"
    assert module.get_alts("Mainchar") == ["Altone"]


def test_add_alt_second_alt_sorts_alphabetically(bot, monkeypatch):
    module = make_alts(bot, monkeypatch, rows=[])
    module.add_alt("Mainchar", "Zebra")
    module.add_alt("Mainchar", "Alpha")
    assert module.get_alts("Mainchar") == ["Alpha", "Zebra"]


def test_del_alt_removes_from_caches(bot, monkeypatch):
    module = make_alts(bot, monkeypatch, rows=[("Mainchar", "Altone"), ("Mainchar", "Alttwo")])
    module.del_alt("Mainchar", "Altone")
    assert module.get_alts("Mainchar") == ["Alttwo"]
    assert module.main("Altone") == "Altone"  # no longer a known alt -> passthrough


def test_del_alt_unknown_alt_is_a_no_op(bot, monkeypatch):
    module = make_alts(bot, monkeypatch, rows=[("Mainchar", "Altone")])
    module.del_alt("Mainchar", "Nonexistent")
    assert module.get_alts("Mainchar") == ["Altone"]


# -- old_output -------------------------------------------------------------------

def test_old_output_no_alts(bot, monkeypatch):
    module = make_alts(bot, monkeypatch, rows=[])
    result = module.old_output("Somechar")
    assert result == {"alts": False, "list": ""}


def test_old_output_with_alts_returns_blob(bot, monkeypatch):
    module = make_alts(bot, monkeypatch, rows=[("Mainchar", "Altone")])
    result = module.old_output("Mainchar")
    assert result["alts"] is True
    assert "Altone" in result["list"]
    assert "Mainchar" in result["list"]


def test_old_output_returntype_1_skips_blob_wrapper(bot, monkeypatch):
    module = make_alts(bot, monkeypatch, rows=[("Mainchar", "Altone")])
    result = module.old_output("Mainchar", 1)
    assert "Altone" in result["list"]
    assert "text://" not in result["list"]


def test_make_alt_blob_title_differs_when_who_is_not_main(bot, monkeypatch):
    module = make_alts(bot, monkeypatch, rows=[])
    blob = module.make_alt_blob("Mainchar", "Altone", ["Altone"], 0)
    assert "Mainchar's alts" in blob


def test_make_alt_blob_title_is_alts_when_who_is_main(bot, monkeypatch):
    module = make_alts(bot, monkeypatch, rows=[])
    blob = module.make_alt_blob("Mainchar", "Mainchar", ["Altone"], 1)
    assert blob.startswith("##highlight##::: Mainchar's Alts")


# -- fancy_output -----------------------------------------------------------------

def test_fancy_output_unknown_player_returns_error_string(bot, monkeypatch):
    module = make_alts(bot, monkeypatch, rows=[], player=FakePlayer())
    result = module.fancy_output("Ghost", 0)
    assert result == "##highlight##Ghost##end## does not exist."


def test_fancy_output_known_player_no_alts(bot, monkeypatch):
    player = FakePlayer(ids={"Mainchar": 1})
    module = make_alts(bot, monkeypatch, rows=[], player=player)
    result = module.fancy_output("Mainchar", 0)
    assert result["alts"] is False


def test_fancy_output_known_player_with_alts_includes_main_first(bot, monkeypatch):
    player = FakePlayer(ids={"Altone": 1})
    online = FakeOnline(states={"Mainchar": {"content": "##red##Offline##end##", "status": 0}})
    module = make_alts(bot, monkeypatch, rows=[("Mainchar", "Altone")], player=player, online=online)
    result = module.fancy_output("Altone", 0)
    assert result["alts"] is True
    assert "Mainchar" in result["list"]


def test_fancy_output_incall_false_calling_main_excludes_self(bot, monkeypatch):
    settings = _FakeSettingsWithCreate()
    player = FakePlayer(ids={"Mainchar": 1})
    online = FakeOnline()
    module = make_alts(
        bot, monkeypatch, rows=[("Mainchar", "Altone")],
        settings=settings, player=player, online=online,
    )
    settings.set("Alts", "incAll", False)
    result = module.fancy_output("Mainchar", 1)
    assert "whois Mainchar" not in result["list"]
    assert "whois Altone" in result["list"]


def test_fancy_output_incall_true_calling_main_includes_self(bot, monkeypatch):
    settings = _FakeSettingsWithCreate()
    player = FakePlayer(ids={"Mainchar": 1})
    online = FakeOnline()
    module = make_alts(
        bot, monkeypatch, rows=[("Mainchar", "Altone")],
        settings=settings, player=player, online=online,
    )
    settings.set("Alts", "incAll", True)
    result = module.fancy_output("Mainchar", 1)
    assert "whois Mainchar" in result["list"]
    assert "whois Altone" in result["list"]


# -- make_info_blob: cross-call into online ----------------------------------------

def test_make_info_blob_shows_online_status_from_online_module(bot, monkeypatch):
    online = FakeOnline(states={"Altone": {"content": "##green##Online##end##", "status": 1}})
    module = make_alts(bot, monkeypatch, rows=[], online=online)
    blob = module.make_info_blob({"nickname": "Mainchar"}, "Mainchar", ["Altone"], 1)
    assert "##green##Online##end##" in blob
    assert ("get_online_state", "Altone") in online.calls


def test_make_info_blob_shows_last_seen_when_offline(bot, monkeypatch):
    online = FakeOnline(
        states={"Altone": {"content": "##red##Offline##end##", "status": 0}},
        last_seen={"Altone": 1000000000},
    )
    settings = _FakeSettingsWithCreate()
    module = make_alts(bot, monkeypatch, rows=[], settings=settings, online=online)
    settings.set("Alts", "LastSeen", True)
    blob = module.make_info_blob({"nickname": "Mainchar"}, "Mainchar", ["Altone"], 1)
    assert "Last seen at" in blob


def test_make_info_blob_skips_last_seen_when_setting_disabled(bot, monkeypatch):
    online = FakeOnline(
        states={"Altone": {"content": "##red##Offline##end##", "status": 0}},
        last_seen={"Altone": 1000000000},
    )
    settings = _FakeSettingsWithCreate()
    module = make_alts(bot, monkeypatch, rows=[], settings=settings, online=online)
    settings.set("Alts", "LastSeen", False)
    blob = module.make_info_blob({"nickname": "Mainchar"}, "Mainchar", ["Altone"], 1)
    assert "Last seen at" not in blob


def test_make_info_blob_excludes_self_unless_incall(bot, monkeypatch):
    online = FakeOnline()
    settings = _FakeSettingsWithCreate()
    module = make_alts(bot, monkeypatch, rows=[], settings=settings, online=online)
    settings.set("Alts", "incAll", False)
    blob = module.make_info_blob({"nickname": "Altone"}, "Mainchar", ["Altone"], 1)
    assert "whois Altone" not in blob


def test_make_info_blob_no_alts_still_titles_correctly(bot, monkeypatch):
    module = make_alts(bot, monkeypatch, rows=[])
    blob = module.make_info_blob({"nickname": "Mainchar"}, "Mainchar", [], 1)
    assert blob == ""


# -- show_alt dispatch --------------------------------------------------------------

def test_show_alt_dispatches_to_old_output(bot, monkeypatch):
    settings = _FakeSettingsWithCreate()
    module = make_alts(bot, monkeypatch, rows=[("Mainchar", "Altone")], settings=settings)
    settings.set("Alts", "Output", "Old")
    result = module.show_alt("Mainchar")
    assert result["alts"] is True


def test_show_alt_dispatches_to_fancy_output(bot, monkeypatch):
    settings = _FakeSettingsWithCreate()
    player = FakePlayer(ids={"Mainchar": 1})
    module = make_alts(bot, monkeypatch, rows=[], settings=settings, player=player)
    settings.set("Alts", "Output", "Fancy")
    result = module.show_alt("Mainchar")
    assert result["alts"] is False


def test_show_alt_unknown_setting_returns_message(bot, monkeypatch):
    settings = _FakeSettingsWithCreate()
    module = make_alts(bot, monkeypatch, rows=[], settings=settings)
    settings.set("Alts", "Output", "Bogus")
    result = module.show_alt("Mainchar")
    assert result == "Settings module required for this module to work properly!"


# -- whois gap: fancy_output/make_info_blob tolerate an un-ported whois module ------

def test_fancy_output_tolerates_missing_whois_module(bot, monkeypatch):
    """core("whois") isn't registered (Core/Ao/Whois.php isn't ported), so
    bot.core("whois") returns a DummyModule whose .lookup() returns an error
    string, not a dict. fancy_output() must fall back gracefully instead of
    raising or treating that string as whois data."""
    player = FakePlayer(ids={"Mainchar": 1})
    module = make_alts(bot, monkeypatch, rows=[], player=player)
    result = module.fancy_output("Mainchar", 0)
    assert isinstance(result, dict)
    assert result["alts"] is False
