from bebot.commodities.base import BotError
from bebot.main_modules.colors import Colors
from bebot.main_modules.online import Online
from bebot.main_modules.online_count import OnlineCounting
from bebot.main_modules.professions import Professions
from bebot.main_modules.settings import Settings
from bebot.main_modules.tools import Tools
from fakes import FakeAccessControl


class _FakeAccessControlWithCreate(FakeAccessControl):
    def create(self, channel, command, access):
        pass


def make_oc(bot, monkeypatch, select_rows=None) -> OnlineCounting:
    """Builds an OnlineCounting wired to the real, already-ported
    Settings/Tools/Colors/Professions/Online core modules (this module is a
    thin query-building/rendering layer over them), with bot.db.select
    monkeypatched so construction (Online's #___users read, Settings'
    #___settings load_all(), etc.) sees an empty result set by default.
    """
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [] if select_rows is None else select_rows)
    bot.register_module(_FakeAccessControlWithCreate(), "access_control")
    Tools(bot)
    Colors(bot)
    Settings(bot)
    Professions(bot)
    Online(bot)
    return OnlineCounting(bot)


# -- construction -------------------------------------------------------------

def test_registers_as_onlinecount_module(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    assert bot.core("onlinecount") is oc


def test_registers_count_and_check_commands(bot, monkeypatch):
    make_oc(bot, monkeypatch)
    for channel in ("tell", "gc", "pgmsg"):
        assert bot.commands[channel]["count"] is bot.core("onlinecount")
        assert bot.commands[channel]["check"] is bot.core("onlinecount")


def test_cp_is_profession_for_ao_default(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    assert oc.cp == "profession"


def test_cp_is_class_for_aoc_game(bot, monkeypatch):
    bot.game = "AoC"
    oc = make_oc(bot, monkeypatch)
    assert oc.cp == "class"


def test_help_describes_commands(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    assert "count all" in oc.help["command"]
    assert "check org [orgname]" in oc.help["command"]


# -- command_handler dispatch --------------------------------------------------

def test_dispatch_count_calls_count_all(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    calls = []
    monkeypatch.setattr(oc, "count_all", lambda: calls.append("count_all") or "ok")
    assert oc.command_handler("Someone", "count", "tell") == "ok"
    assert calls == ["count_all"]


def test_dispatch_count_all_calls_count_all(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    monkeypatch.setattr(oc, "count_all", lambda: "ok")
    assert oc.command_handler("Someone", "count all", "tell") == "ok"


def test_dispatch_count_org_calls_count_org(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    monkeypatch.setattr(oc, "count_org", lambda: "orgs")
    assert oc.command_handler("Someone", "count org", "tell") == "orgs"


def test_dispatch_count_org_name_calls_count_org_members(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    captured = {}
    def fake_count_org_members(name):
        captured["name"] = name
        return "members"

    monkeypatch.setattr(oc, "count_org_members", fake_count_org_members)
    assert oc.command_handler("Someone", "count org Test Org", "tell") == "members"
    assert captured["name"] == "Test Org"


def test_dispatch_count_shortcut_calls_count(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    captured = {}

    def fake_count(shortcut):
        captured["s"] = shortcut
        return "counted"

    monkeypatch.setattr(oc, "count", fake_count)
    assert oc.command_handler("Someone", "count adv", "tell") == "counted"
    assert captured["s"] == "adv"


def test_dispatch_check_calls_check_all(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    monkeypatch.setattr(oc, "check_all", lambda: "checked")
    assert oc.command_handler("Someone", "check", "tell") == "checked"


def test_dispatch_check_all_calls_check_all(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    monkeypatch.setattr(oc, "check_all", lambda: "checked")
    assert oc.command_handler("Someone", "check all", "tell") == "checked"


def test_dispatch_check_org_calls_check_org(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    monkeypatch.setattr(oc, "check_org", lambda: "orgs")
    assert oc.command_handler("Someone", "check org", "tell") == "orgs"


def test_dispatch_check_org_name_calls_check_org_members(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    captured = {}
    def fake_check_org_members(name):
        captured["name"] = name
        return "members"

    monkeypatch.setattr(oc, "check_org_members", fake_check_org_members)
    assert oc.command_handler("Someone", "check org Test Org", "tell") == "members"
    assert captured["name"] == "Test Org"


def test_dispatch_check_shortcut_calls_check(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    captured = {}

    def fake_check(shortcut):
        captured["s"] = shortcut
        return "checked"

    monkeypatch.setattr(oc, "check", fake_check)
    assert oc.command_handler("Someone", "check adv", "tell") == "checked"
    assert captured["s"] == "adv"


def test_dispatch_unmatched_returns_none(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    assert oc.command_handler("Someone", "banana", "tell") is None


# -- count_all -----------------------------------------------------------------

def test_count_all_no_one_online(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [])
    result = oc.count_all()
    assert "Total: ##counting_number##0##end##" in result
    assert "adv: ##counting_number##0##end##" in result


def test_count_all_sums_by_shortcut(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)

    def fake_select(sql, *a, **kw):
        if "GROUP BY profession" in sql:
            return [{"profession": "Adventurer", "count": 3}, {"profession": "Doctor", "count": 2}]
        return []

    monkeypatch.setattr(bot.db, "select", fake_select)
    result = oc.count_all()
    assert "Total: ##counting_number##5##end##" in result
    assert "adv: ##counting_number##3##end##" in result
    assert "doc: ##counting_number##2##end##" in result


# -- count ------------------------------------------------------------------

def test_count_unknown_shortcut_returns_bot_error(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    result = oc.count("nonsense")
    assert isinstance(result, BotError)


def test_count_no_one_of_profession(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)

    def fake_select(sql, *a, **kw):
        if "COUNT(DISTINCT t1.nickname) FROM" in sql:
            return [[0]]
        return []

    monkeypatch.setattr(bot.db, "select", fake_select)
    result = oc.count("adv")
    assert result == "No Adventurer in chat!"


def test_count_lists_members(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)

    def fake_select(sql, *a, **kw):
        if "COUNT(DISTINCT t1.nickname) FROM" in sql:
            return [[2]]
        if "DISTINCT(t1.nickname)" in sql:
            return [["Playerone", 200, 30], ["Playertwo", 150, 10]]
        return []

    monkeypatch.setattr(bot.db, "select", fake_select)
    result = oc.count("adv")
    assert "2 Adventurers in chat:" in result
    assert "Playerone [200/30]" in result
    assert "Playertwo [150/10]" in result


# -- count_org / count_org_members ---------------------------------------------

def test_count_org_nobody_online(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [])
    result = oc.count_org()
    assert result == "Nobody online!"


def test_count_org_lists_organizations(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)

    def fake_select(sql, *a, **kw):
        if "SUM(t2.level)" in sql:
            return [{"org": "Test Org", "count": 4, "avg_level": 100.0}]
        if "count(DISTINCT nickname)" in sql:
            return [{"count": 8}]
        return []

    monkeypatch.setattr(bot.db, "select", fake_select)
    result = oc.count_org()
    assert "Test Org" in result
    assert "50.0%" in result
    assert "average level of 100.0" in result


def test_count_org_members_none_found(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)

    def fake_select(sql, *a, **kw):
        if "COUNT(DISTINCT t1.nickname) FROM" in sql:
            return [[0]]
        return []

    monkeypatch.setattr(bot.db, "select", fake_select)
    result = oc.count_org_members("Test Org")
    assert result == "No member of Test Org in chat!"


def test_count_org_members_lists_members(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)

    def fake_select(sql, *a, **kw):
        if "COUNT(DISTINCT t1.nickname) FROM" in sql:
            return [[1]]
        if "DISTINCT(t1.nickname)" in sql:
            return [["Playerone", 200, 30]]
        return []

    monkeypatch.setattr(bot.db, "select", fake_select)
    result = oc.count_org_members("Test Org")
    assert "1 member of Test Org in chat:" in result
    assert "Playerone [200/30]" in result


# -- check_all / check / check_org / check_org_members -------------------------

def test_check_all_nobody_online(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [])
    assert oc.check_all() == "Nobody online!"


def test_check_all_makes_assist_blob(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [["Playerone", 200, 30]])
    result = oc.check_all()
    assert "/assist Playerone" in result
    assert "Check all online" in result


def test_check_unknown_shortcut_returns_bot_error(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    result = oc.check("nonsense")
    assert isinstance(result, BotError)


def test_check_none_of_profession(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [])
    assert oc.check("adv") == "No Adventurer in chat!"


def test_check_makes_assist_blob(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [["Playerone", 200, 30]])
    result = oc.check("adv")
    assert "/assist Playerone" in result


def test_check_org_nobody_online(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [])
    assert oc.check_org() == "Nobody online!"


def test_check_org_members_none_found(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [])
    result = oc.check_org_members("Test Org")
    assert result == "Nobody of Test Org online!"


def test_check_org_members_makes_assist_blob(bot, monkeypatch):
    oc = make_oc(bot, monkeypatch)
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [["Playerone", 200, 30]])
    result = oc.check_org_members("Test Org")
    assert "/assist Playerone" in result
