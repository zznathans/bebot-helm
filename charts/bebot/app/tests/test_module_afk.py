import time

from bebot.main_modules.afk import Afk
from bebot.main_modules.alias import Alias
from bebot.main_modules.alts import Alts
from bebot.main_modules.command_alias import CommandAlias
from bebot.main_modules.settings import Settings
from bebot.main_modules.tools import Tools
from fakes import FakePlayer


class FakeAlias:
    """Local stand-in for core("alias") (the character-alias module,
    main_modules/alias.py) -- distinct from core("command_alias"). Only the
    `.alias` dict (alias -> owning nickname) is used by Afk.gone().
    """

    def __init__(self, alias=None):
        self.alias = dict(alias or {})


class FakeSecurity:
    """Local stand-in for core("security"); only get_access_level() is used,
    by Afk.buddy()."""

    def __init__(self, levels=None, default=2):
        self.levels = dict(levels or {})
        self.default = default

    def get_access_level(self, name) -> int:
        return self.levels.get(name, self.default)


class FakeAlts:
    def __init__(self, mains=None, alts=None):
        self.mains = dict(mains or {})
        self.alts = dict(alts or {})

    def main(self, name):
        return self.mains.get(name, name)

    def get_alts(self, main):
        return self.alts.get(main, [])


def make_afk(bot, monkeypatch, alias=None, alts=None, security=None) -> Afk:
    """Builds an Afk module with lightweight fakes for alias/alts/security
    (unless overridden) and the real, already-ported Settings/CommandAlias
    modules (so `register_alias("afk", "brb")` and the `Afk/*` settings
    created in __init__ are exercised for real)."""
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [])
    Settings(bot)
    Tools(bot)
    CommandAlias(bot)
    bot.register_module(alts if alts is not None else FakeAlts(), "alts")
    bot.register_module(alias if alias is not None else FakeAlias(), "alias")
    bot.register_module(security if security is not None else FakeSecurity(), "security")
    return Afk(bot)


# -- construction --------------------------------------------------------------

def test_registers_as_afk_module(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    assert bot.core("afk") is module


def test_registers_afk_command_on_all_chat_channels(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    assert bot.commands["tell"]["afk"] is module
    assert bot.commands["gc"]["afk"] is module
    assert bot.commands["pgmsg"]["afk"] is module


def test_registers_brb_as_command_alias_for_afk(bot, monkeypatch):
    make_afk(bot, monkeypatch)
    assert bot.core("command_alias").alias["brb"] == "afk"


def test_creates_afk_settings_with_documented_defaults(bot, monkeypatch):
    make_afk(bot, monkeypatch)
    settings = bot.core("settings")
    assert settings.get("Afk", "Alias") is True
    assert settings.get("Afk", "noprefix") is False
    assert settings.get("Afk", "brb_noprefix") is False


def test_registers_privgroup_gmsg_buddy_events(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    assert bot.commands["privgroup"]["Afk"] is module
    assert bot.commands["gmsg"]["org"]["Afk"] is module
    assert bot.commands["buddy"]["Afk"] is module


# -- command_handler -------------------------------------------------------------

def test_command_handler_sets_afk_with_message(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    result = module.command_handler("Somechar", "afk gone fishing", "tell")
    assert result == "##highlight##Somechar##end## is now AFK."
    assert module.afk["Somechar"]["msg"] == "gone fishing"
    assert module.acheck("Somechar")


def test_command_handler_no_message_uses_default(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    module.command_handler("Somechar", "afk", "tell")
    assert module.afk["Somechar"]["msg"] == "Away from keyboard"


# -- gone/back/acheck --------------------------------------------------------------

def test_gone_marks_player_afk_with_timestamp(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    before = time.time()
    module.gone("Somechar", "brb")
    assert module.afk["Somechar"]["msg"] == "brb"
    assert module.afk["Somechar"]["time"] >= before


def test_gone_folds_alts_into_afkalias(bot, monkeypatch):
    alts = FakeAlts(mains={"Somechar": "Somechar"}, alts={"Somechar": ["Somealt1", "Somealt2"]})
    module = make_afk(bot, monkeypatch, alts=alts)
    module.gone("Somechar")
    assert module.afkalias["Somealt1"] == "Somechar"
    assert module.afkalias["Somealt2"] == "Somechar"


def test_gone_folds_character_aliases_into_afkalias_when_enabled(bot, monkeypatch):
    alias = FakeAlias(alias={"grumpy": "Somechar", "other": "Otherchar"})
    module = make_afk(bot, monkeypatch, alias=alias)
    module.gone("Somechar")
    assert module.afkalias["grumpy"] == "Somechar"
    assert "other" not in module.afkalias


def test_gone_ignores_character_aliases_when_setting_disabled(bot, monkeypatch):
    alias = FakeAlias(alias={"grumpy": "Somechar"})
    module = make_afk(bot, monkeypatch, alias=alias)
    bot.core("settings").save("Afk", "Alias", False)
    module.gone("Somechar")
    assert "grumpy" not in module.afkalias


def test_back_clears_afk_and_associated_aliases(bot, monkeypatch):
    alts = FakeAlts(alts={"Somechar": ["Somealt"]})
    module = make_afk(bot, monkeypatch, alts=alts)
    module.gone("Somechar")
    assert module.acheck("Somechar")
    module.back("Somechar")
    assert not module.acheck("Somechar")
    assert "Somealt" not in module.afkalias


def test_acheck_false_for_unknown_or_empty_name(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    assert module.acheck("Nobody") is False
    assert module.acheck("") is False
    assert module.acheck(None) is False


# -- afk_time ----------------------------------------------------------------------

def test_afk_time_seconds(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    module.afk["Somechar"] = {"time": time.time() - 30, "msg": "afk"}
    assert module.afk_time("Somechar") == "30 Seconds"


def test_afk_time_minutes(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    module.afk["Somechar"] = {"time": time.time() - 125, "msg": "afk"}
    assert module.afk_time("Somechar") == "2 Minutes"


def test_afk_time_hours_and_minutes(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    module.afk["Somechar"] = {"time": time.time() - (2 * 3600 + 5 * 60), "msg": "afk"}
    assert module.afk_time("Somechar") == "2 Hours and 5 Minutes"


# -- msg_check / msgs ----------------------------------------------------------------

def test_msg_check_direct_name_match_records_and_replies(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    module.gone("Somechar", "in the oven")
    result = module.msg_check("Otherchar", "", "hey Somechar you around?")
    assert "Somechar has been AFK for" in result
    assert "(in the oven)" in result
    assert module.afkmsgs["Somechar"][0][1] == "Otherchar"
    assert module.afkmsgs["Somechar"][0][2] == "hey Somechar you around?"


def test_msg_check_no_match_returns_false(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    module.gone("Somechar")
    assert module.msg_check("Otherchar", "", "nothing relevant here") is False


def test_msg_check_matches_via_alias_when_enabled(bot, monkeypatch):
    alts = FakeAlts(alts={"Somechar": ["Somealt"]})
    module = make_afk(bot, monkeypatch, alts=alts)
    module.gone("Somechar", "napping")
    result = module.msg_check("Otherchar", "", "yo Somealt where you at")
    assert "Somechar has been AFK for" in result
    assert "(napping)" in result
    assert module.afkmsgs["Somechar"][0][1] == "Otherchar"


def test_msg_check_ignores_alias_when_setting_disabled(bot, monkeypatch):
    alts = FakeAlts(alts={"Somechar": ["Somealt"]})
    module = make_afk(bot, monkeypatch, alts=alts)
    bot.core("settings").save("Afk", "Alias", False)
    module.gone("Somechar")
    assert module.msg_check("Otherchar", "", "yo Somealt where you at") is False


def test_msgs_returns_false_with_no_messages(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    assert module.msgs("Somechar") is False


def test_msgs_builds_blob_and_clears_log(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    module.gone("Somechar", "brb")
    module.msg_check("Otherchar", "", "hey Somechar")
    result = module.msgs("Somechar")
    assert "1" in result
    assert "Messages ::" in result
    assert "Otherchar" in result
    assert "hey Somechar" in result
    # A second call finds nothing left to report.
    assert module.msgs("Somechar") is False


# -- privgroup -----------------------------------------------------------------------

def test_privgroup_announces_return_when_afk_player_speaks(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    module.gone("Somechar", "brb")
    sent = []
    monkeypatch.setattr(bot, "send_output", lambda *a, **kw: sent.append(a))
    module.privgroup("Somechar", "I'm back")
    assert not module.acheck("Somechar")
    assert sent
    assert "Somechar is back. AFK for" in sent[0][1]
    assert sent[0][2] == "both"


def test_privgroup_noprefix_afk_sets_status(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    bot.core("settings").save("Afk", "noprefix", True)
    sent = []
    monkeypatch.setattr(bot, "send_output", lambda *a, **kw: sent.append(a))
    module.privgroup("Somechar", "afk making dinner")
    assert module.afk["Somechar"]["msg"] == "making dinner"
    assert sent[-1][1] == "Somechar is now AFK."


def test_privgroup_noprefix_afk_bare_uses_default_message(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    bot.core("settings").save("Afk", "noprefix", True)
    monkeypatch.setattr(bot, "send_output", lambda *a, **kw: None)
    module.privgroup("Somechar", "afk")
    assert module.afk["Somechar"]["msg"] == "Away from keyboard"


def test_privgroup_noprefix_brb_sets_status(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    bot.core("settings").save("Afk", "brb_noprefix", True)
    sent = []
    monkeypatch.setattr(bot, "send_output", lambda *a, **kw: sent.append(a))
    module.privgroup("Somechar", "brb dinner")
    assert module.afk["Somechar"]["msg"] == "dinner"
    assert sent[-1][1] == "Somechar is now AFK."


def test_privgroup_relays_afk_notice_to_pgroup(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    module.gone("Somechar", "napping")
    sent = []
    monkeypatch.setattr(bot, "send_pgroup", lambda *a, **kw: sent.append(a))
    module.privgroup("Otherchar", "hey Somechar you there?")
    assert sent
    assert "Somechar has been AFK for" in sent[0][0]


# -- gmsg --------------------------------------------------------------------------

def test_gmsg_announces_return_when_afk_player_speaks(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    module.gone("Somechar", "brb")
    sent = []
    monkeypatch.setattr(bot, "send_output", lambda *a, **kw: sent.append(a))
    module.gmsg("Somechar", "org", "back now")
    assert not module.acheck("Somechar")
    assert "Somechar is back. AFK for" in sent[0][1]


def test_gmsg_noprefix_afk_sets_status_and_highlights(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    bot.core("settings").save("Afk", "noprefix", True)
    sent = []
    monkeypatch.setattr(bot, "send_output", lambda *a, **kw: sent.append(a))
    module.gmsg("Somechar", "org", "afk lunch")
    assert module.afk["Somechar"]["msg"] == "lunch"
    assert sent[-1][1] == "##highlight##Somechar##end## is now AFK."


def test_gmsg_relays_afk_notice_to_guild_chat(bot, monkeypatch):
    module = make_afk(bot, monkeypatch)
    module.gone("Somechar", "afk")
    sent = []
    monkeypatch.setattr(bot, "send_gc", lambda *a, **kw: sent.append(a))
    module.gmsg("Otherchar", "org", "paging Somechar")
    assert sent
    assert "Somechar has been AFK for" in sent[0][0]


# -- buddy (logon/logoff) ------------------------------------------------------------

def test_buddy_logoff_clears_afk_and_tells_user(bot, monkeypatch):
    security = FakeSecurity(default=2)
    module = make_afk(bot, monkeypatch, security=security)
    module.gone("Somechar", "brb")
    sent = []
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))
    module.buddy("Somechar", 0)
    assert not module.acheck("Somechar")
    assert "you have been set as back. (Logoff)" in sent[0][1]


def test_buddy_zone_in_marks_afk_for_member(bot, monkeypatch):
    security = FakeSecurity(default=2)
    module = make_afk(bot, monkeypatch, security=security)
    sent = []
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))
    module.buddy("Somechar", 3)
    assert module.acheck("Somechar")
    assert "you have been set as AFK." in sent[0][1]


def test_buddy_zone_out_marks_back_for_member(bot, monkeypatch):
    security = FakeSecurity(default=2)
    module = make_afk(bot, monkeypatch, security=security)
    module.gone("Somechar", "brb")
    sent = []
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))
    module.buddy("Somechar", 5)
    assert not module.acheck("Somechar")
    assert "you have been set as back." in sent[0][1]


def test_buddy_ignores_low_access_players(bot, monkeypatch):
    security = FakeSecurity(default=1)
    module = make_afk(bot, monkeypatch, security=security)
    sent = []
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))
    module.buddy("Guestchar", 3)
    assert not module.acheck("Guestchar")
    assert sent == []


def test_buddy_zone_in_already_afk_is_noop(bot, monkeypatch):
    security = FakeSecurity(default=2)
    module = make_afk(bot, monkeypatch, security=security)
    module.gone("Somechar", "already gone")
    sent = []
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))
    module.buddy("Somechar", 3)
    assert module.afk["Somechar"]["msg"] == "already gone"
    assert sent == []


# -- integration with the real Alts and Alias modules --------------------------------

def test_integration_with_real_alts_and_alias_modules(bot, monkeypatch):
    """Register the real, already-ported Alts and Alias modules alongside
    Afk to confirm main<->alt normalization and the character-alias watch
    list actually interoperate end to end."""
    select_rows = {"alts": [("Mainchar", "Altchar")], "alias": [("grumpy", "Mainchar", 1)]}

    def fake_select(sql, *a, **kw):
        if "#___alts" in sql:
            return select_rows["alts"]
        if "alias, nickname, main FROM #___alias" in sql:
            return select_rows["alias"]
        return []

    monkeypatch.setattr(bot.db, "select", fake_select)
    Settings(bot)
    Tools(bot)
    CommandAlias(bot)
    bot.register_module(FakePlayer(), "player")
    bot.register_module(FakeSecurity(), "security")

    Alts(bot)
    alias_module = Alias(bot)
    alias_module.connect()

    module = Afk(bot)
    module.gone("Mainchar", "grabbing food")

    # The alt and the character-alias should both be watched for "Mainchar".
    assert module.afkalias["Altchar"] == "Mainchar"
    assert module.afkalias["grumpy"] == "Mainchar"

    result = module.msg_check("Otherchar", "", "yo grumpy you home?")
    assert "Mainchar has been AFK for" in result
    assert "(grabbing food)" in result
