"""Tests for main_modules/bans_manager_ui.py (ported from Modules/BansManagerUi.php).

Uses the real Settings/Tools/Colors/CommandAlias modules (cheap, pure) plus
small local fakes for Player/Security/Online/Chat/db so tests can control
exactly what ban/unban/list operations see and do.
"""
from __future__ import annotations

from bebot.commodities.base import BotError
from bebot.main_modules.bans_manager_ui import BansManagerUi
from bebot.main_modules.colors import Colors
from bebot.main_modules.command_alias import CommandAlias
from bebot.main_modules.settings import Settings
from bebot.main_modules.tools import Tools


class FakePlayer:
    def __init__(self, ids: dict[str, int] | None = None):
        self._ids = dict(ids or {})

    def id(self, name):
        if name in self._ids:
            return self._ids[name]
        return BotError(None, "player")


class FakeSecurity:
    def __init__(self):
        self.set_ban_calls: list[tuple] = []
        self.rem_ban_calls: list[tuple] = []
        self.set_ban_result = "banned"
        self.rem_ban_result = "unbanned"

    def set_ban(self, admin, target, reason, endtime):
        self.set_ban_calls.append((admin, target, reason, endtime))
        return self.set_ban_result

    def rem_ban(self, admin, target):
        self.rem_ban_calls.append((admin, target))
        return self.rem_ban_result


class FakeOnline:
    def __init__(self, in_chat_names=None):
        self._in_chat = set(in_chat_names or [])

    def in_chat(self, name):
        return name in self._in_chat


class FakeChat:
    def __init__(self):
        self.kicked: list[str] = []

    def pgroup_kick(self, user):
        self.kicked.append(user)


class FakeAutoUserAdd:
    def __init__(self):
        self.checked: dict[str, bool] = {"Somebody": True}


class FakeDb:
    def __init__(self, rows_by_query=None):
        self.rows_by_query = rows_by_query or {}
        self.queries: list[str] = []

    def query(self, sql: str) -> bool:
        self.queries.append(sql)
        return True

    def select(self, sql: str, as_dict: bool = False):
        for needle, rows in self.rows_by_query.items():
            if needle in sql:
                return rows
        return []

    def real_escape_string(self, value) -> str:
        return str(value).replace("'", "\\'")

    def define_tablename(self, table: str, use_prefix) -> str:
        return table


def make_module(
    bot,
    ids=None,
    in_chat_names=None,
    rows_by_query=None,
    req_reason=False,
    morebots="",
    with_autouseradd=True,
) -> BansManagerUi:
    Settings(bot)
    Tools(bot)
    Colors(bot)
    CommandAlias(bot)
    bot.register_module(FakePlayer(ids or {}), "player")
    bot.register_module(FakeSecurity(), "security")
    bot.register_module(FakeOnline(in_chat_names or []), "online")
    bot.register_module(FakeChat(), "chat")
    if with_autouseradd:
        bot.register_module(FakeAutoUserAdd(), "autouseradd")

    fake_db = FakeDb(rows_by_query)
    bot.db = fake_db

    module = BansManagerUi(bot)
    bot.core("settings").save("Ban", "ReqReason", req_reason)
    bot.core("settings").save("Ban", "MoreBots", morebots)
    return module


# -- construction ---------------------------------------------------------------

def test_registers_as_bansmanagerui_module(bot):
    module = make_module(bot)
    assert bot.core("bansmanagerui") is module


def test_creates_ban_settings(bot):
    make_module(bot)
    settings = bot.core("settings")
    assert settings.exists("Ban", "ReqReason")
    assert settings.exists("Ban", "MoreBots")


def test_registers_cron_event(bot):
    module = make_module(bot)
    assert type(module).__name__ in bot._cron_jobs.get(300, {})


def test_registers_aliases(bot):
    make_module(bot)
    alias = bot.core("command_alias")
    assert alias.alias["banlist"] == "ban list"
    assert alias.alias["banhistory"] == "ban history"
    assert alias.alias["bansearch"] == "ban search"
    assert alias.alias["blacklist"] == "ban"


# -- command_handler dispatch ----------------------------------------------------

def test_dispatch_plain_ban_shows_list(bot):
    module = make_module(bot)
    result = module.command_handler("Someone", "ban", "tell")
    assert "Banned" in result or "banned" in result


def test_dispatch_ban_list_with_skip(bot):
    module = make_module(bot)
    result = module.command_handler("Someone", "ban list 20", "tell")
    assert "Nobody is banned!" == result


def test_dispatch_ban_history(bot):
    module = make_module(bot)
    result = module.command_handler("Someone", "ban history", "tell")
    assert result == "Nobody was banned!"


def test_dispatch_ban_search(bot):
    module = make_module(bot)
    result = module.command_handler("Someone", "ban search Naughty", "tell")
    assert result == "Nobody found banned!"


def test_dispatch_ban_add_name_only(bot, monkeypatch):
    module = make_module(bot, ids={"Newbie": 111})
    calls = []
    monkeypatch.setattr(module, "add_ban", lambda *a: calls.append(a) or "ok")
    result = module.command_handler("Admin", "ban add Newbie", "tell")
    assert calls == [("Admin", "Newbie", "0", "")]
    assert result == "ok"


def test_dispatch_ban_add_name_duration(bot, monkeypatch):
    module = make_module(bot)
    calls = []
    monkeypatch.setattr(module, "add_ban", lambda *a: calls.append(a) or "ok")
    module.command_handler("Admin", "ban add Newbie 5h", "tell")
    assert calls == [("Admin", "Newbie", "5h", "")]


def test_dispatch_ban_add_name_reason(bot, monkeypatch):
    module = make_module(bot)
    calls = []
    monkeypatch.setattr(module, "add_ban", lambda *a: calls.append(a) or "ok")
    module.command_handler("Admin", "ban add Newbie being a jerk", "tell")
    assert calls == [("Admin", "Newbie", "0", "being a jerk")]


def test_dispatch_ban_add_name_duration_reason(bot, monkeypatch):
    module = make_module(bot)
    calls = []
    monkeypatch.setattr(module, "add_ban", lambda *a: calls.append(a) or "ok")
    module.command_handler("Admin", "ban add Newbie 5h being a jerk", "tell")
    assert calls == [("Admin", "Newbie", "5h", "being a jerk")]


def test_dispatch_ban_del(bot, monkeypatch):
    module = make_module(bot)
    calls = []
    monkeypatch.setattr(module, "del_ban", lambda *a: calls.append(a) or "ok")
    module.command_handler("Admin", "ban del Newbie", "tell")
    assert calls == [("Admin", "Newbie")]


def test_dispatch_ban_rem(bot, monkeypatch):
    module = make_module(bot)
    calls = []
    monkeypatch.setattr(module, "del_ban", lambda *a: calls.append(a) or "ok")
    module.command_handler("Admin", "ban rem Newbie", "tell")
    assert calls == [("Admin", "Newbie")]


def test_dispatch_unmatched_sends_help(bot, monkeypatch):
    module = make_module(bot)
    calls = []
    monkeypatch.setattr(bot, "send_help", lambda to, cmd=False: calls.append((to, cmd)) or "help!")
    result = module.command_handler("Someone", "ban blah blah blah", "tell")
    assert calls == [("Someone", "ban")]
    assert result == "help!"


# -- add_ban ----------------------------------------------------------------------

def test_add_ban_invalid_name(bot):
    module = make_module(bot, ids={})
    result = module.add_ban("Admin", "Nobody", "0", "")
    assert "is no valid character name!" in result


def test_add_ban_reason_required_blocks_empty_reason(bot):
    module = make_module(bot, ids={"Newbie": 111}, req_reason=True)
    result = module.add_ban("Admin", "Newbie", "0", "")
    assert result == "Reason Required for adding Bans"


def test_add_ban_defaults_reason_when_not_required(bot):
    module = make_module(bot, ids={"Newbie": 111}, req_reason=False)
    module.add_ban("Admin", "Newbie", "0", "")
    security = bot.core("security")
    assert security.set_ban_calls[-1] == ("Admin", "Newbie", "None given.", 0)


def test_add_ban_permanent_endtime_zero(bot):
    module = make_module(bot, ids={"Newbie": 111})
    module.add_ban("Admin", "Newbie", "0", "reason")
    security = bot.core("security")
    assert security.set_ban_calls[-1][3] == 0


def test_add_ban_duration_units(bot):
    module = make_module(bot, ids={"Newbie": 111})
    security = bot.core("security")
    cases = {
        "6h": 6 * 60 * 60,
        "2d": 2 * 60 * 60 * 24,
        "1w": 60 * 60 * 24 * 7,
        "3m": 3 * 60 * 60 * 24 * 30,
        "1y": 60 * 60 * 24 * 365,
        "10": 10 * 60,
    }
    for duration, expected_seconds in cases.items():
        before = __import__("time").time()
        module.add_ban("Admin", "Newbie", duration, "reason")
        endtime = security.set_ban_calls[-1][3]
        assert abs(endtime - (before + expected_seconds)) < 5


def test_add_ban_kicks_from_pgroup_when_in_chat(bot):
    module = make_module(bot, ids={"Newbie": 111}, in_chat_names=["Newbie"])
    module.add_ban("Admin", "Newbie", "0", "reason")
    assert bot.core("chat").kicked == ["Newbie"]


def test_add_ban_does_not_kick_when_not_in_chat(bot):
    module = make_module(bot, ids={"Newbie": 111}, in_chat_names=[])
    module.add_ban("Admin", "Newbie", "0", "reason")
    assert bot.core("chat").kicked == []


def test_add_ban_relays_to_morebots(bot, monkeypatch):
    module = make_module(bot, ids={"Newbie": 111, "Otherbot": 222}, morebots="Otherbot")
    sent = []
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))
    module.add_ban("Admin", "Newbie", "0", "reason")
    assert len(sent) == 1
    assert sent[0][0] == "Otherbot"
    assert "ban add Newbie 0 reason" in sent[0][1]


def test_add_ban_relays_to_morebots_even_when_unresolvable(bot, monkeypatch):
    """Faithful port of the PHP condition `if (!$idb instanceof BotError || $idb
    != 0)`: since a BotError object is never loosely-equal to 0, this condition
    is (also in the original) always true regardless of whether the configured
    bot resolves -- i.e. it never actually skips a relay. Not "fixed" here since
    the brief is a faithful port, not a bugfix; documented in the module
    docstring alongside the other MoreBots notes."""
    module = make_module(bot, ids={"Newbie": 111}, morebots="Ghostbot")
    sent = []
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))
    module.add_ban("Admin", "Newbie", "0", "reason")
    assert len(sent) == 1
    assert sent[0][0] == "Ghostbot"


# -- del_ban ------------------------------------------------------------------------

def test_del_ban_invalid_name(bot):
    module = make_module(bot, ids={"Nobody": 0})
    result = module.del_ban("Admin", "Nobody")
    assert "is no valid character name!" in result


def test_del_ban_calls_security_rem_ban_with_two_args(bot):
    module = make_module(bot, ids={"Newbie": 111})
    module.del_ban("Admin", "Newbie")
    security = bot.core("security")
    assert security.rem_ban_calls[-1] == ("Admin", "Newbie")


def test_del_ban_flips_autouseradd_checked_entry(bot):
    module = make_module(bot, ids={"Newbie": 111}, with_autouseradd=True)
    module.del_ban("Admin", "Newbie")
    assert bot.core("autouseradd").checked["Newbie"] is False


def test_del_ban_noop_when_autouseradd_not_registered(bot):
    module = make_module(bot, ids={"Newbie": 111}, with_autouseradd=False)
    # Should not raise even though autouseradd isn't a real module.
    module.del_ban("Admin", "Newbie")


# -- cron -------------------------------------------------------------------------

def test_cron_unbans_expired_and_calls_auto_user_readd(bot, monkeypatch):
    module = make_module(
        bot,
        ids={"Expired": 111},
        rows_by_query={"user_level = -1 AND banned_until > 0": [("Expired",)]},
        with_autouseradd=True,
    )
    module.cron()
    security = bot.core("security")
    assert security.rem_ban_calls == [("Cron", "Expired")]
    assert bot.core("autouseradd").checked["Expired"] is False


def test_cron_does_nothing_when_no_expired_bans(bot):
    module = make_module(bot)
    module.cron()
    assert bot.core("security").rem_ban_calls == []


# -- listing ------------------------------------------------------------------------

def test_show_ban_list_empty(bot):
    module = make_module(bot)
    result = module.show_ban_list(0)
    assert result == "Nobody is banned!"


def test_show_ban_list_renders_entries(bot):
    module = make_module(
        bot,
        rows_by_query={
            "SELECT COUNT(*) FROM #___users WHERE user_level = -1": [(1,)],
            "SELECT nickname, banned_by, banned_at, banned_for, banned_until": [
                ("Naughty", "Admin", 1700000000, "spam", 0),
            ],
        },
    )
    result = module.show_ban_list(0)
    assert "Characters Banned" in result
    assert "Naughty" in result
    assert "Admin" in result
    assert "spam" in result
    assert "Permanent ban" in result


def test_ban_history_empty(bot):
    module = make_module(bot)
    assert module.ban_history(0) == "Nobody was banned!"


def test_ban_search_empty(bot):
    module = make_module(bot)
    assert module.ban_search(0, None) == "Nobody found banned!"
