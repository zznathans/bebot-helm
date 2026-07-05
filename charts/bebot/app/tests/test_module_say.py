"""Tests for main_modules/say.py (ported from Modules/Say.php)."""
from __future__ import annotations

from bebot.commodities.base import BotError
from bebot.main_modules.say import Say
from bebot.main_modules.settings import Settings
from bebot.main_modules.tools import Tools
from fakes import FakeAccessControl


class _FakeAccessControlWithCreate(FakeAccessControl):
    def create(self, channel, command, access):
        pass


class FakeWhois:
    def __init__(self, known=None):
        self.known = set(known or [])

    def lookup(self, name):
        if name in self.known:
            return {"nickname": name}
        err = BotError(None, "whois")
        err.set("not found", log=False)
        return err


def make_say(bot, known_players=None) -> Say:
    bot.register_module(_FakeAccessControlWithCreate(), "access_control")
    Tools(bot)
    Settings(bot)
    bot.register_module(FakeWhois(known_players), "whois")
    return Say(bot)


# -- construction -----------------------------------------------------------------

def test_registers_as_say_module(bot):
    s = make_say(bot)
    assert bot.core("say") is s


def test_registers_commands(bot):
    s = make_say(bot)
    for command in ("say", "whosaidthat", "sendtell", "sendhelp"):
        for channel in ("tell", "gc", "pgmsg"):
            assert bot.commands[channel][command] is s


def test_creates_output_channel_setting(bot):
    make_say(bot)
    assert bot.core("settings").get("Say", "OutputChannel") == "both"


# -- say ------------------------------------------------------------------------

def test_say_origin_channel_returns_message_directly(bot):
    s = make_say(bot)
    bot.core("settings").save("Say", "OutputChannel", "origin")
    result = s.command_handler("Someguy", "say Hello there", "tell")
    assert result == "Hello there"


def test_say_non_origin_channel_sends_output_and_returns_false(bot, monkeypatch):
    s = make_say(bot)
    sent = []
    monkeypatch.setattr(bot, "send_output", lambda name, msg, kind: sent.append((name, msg, kind)))
    result = s.command_handler("Someguy", "say Hello there", "tell")
    assert result is False
    assert sent == [("Someguy", "Hello there", "both")]


def test_whosaidthat_records_who_said_it(bot):
    s = make_say(bot)
    s.command_handler("Someguy", "say Hello there", "tell")
    result = s.whosaidthat()
    assert result.startswith("Someguy made me say \"Hello there\"")
    assert "seconds ago." in result


def test_whosaidthat_nobody_yet(bot):
    s = make_say(bot)
    assert s.whosaidthat() == "Nobody has used the say command since I logged in."


# -- sendtell ---------------------------------------------------------------------

def test_sendtell_requires_arguments(bot):
    s = make_say(bot)
    assert s.sendtell("Someadmin", "") == "Please provide player & message"


def test_sendtell_unknown_player(bot):
    s = make_say(bot, known_players=set())
    assert s.sendtell("Someadmin", "Otherguy hi there") == "Player Otherguy does not exist"


def test_sendtell_self(bot):
    s = make_say(bot, known_players={"Someadmin"})
    assert s.sendtell("Someadmin", "Someadmin hi") == "No use to send a tell to yourself"


def test_sendtell_empty_message(bot):
    s = make_say(bot, known_players={"Otherguy"})
    assert s.sendtell("Someadmin", "Otherguy") == "Can't send empty message"


def test_sendtell_sends_and_records(bot, monkeypatch):
    s = make_say(bot, known_players={"Otherguy"})
    sent = []
    monkeypatch.setattr(bot, "send_tell", lambda to, msg, *a, **k: sent.append((to, msg)))
    result = s.sendtell("Someadmin", "Otherguy hi there friend")
    assert result == "Message sent to Otherguy"
    assert sent == [("Otherguy", "hi there friend")]
    assert "Someadmin made me say" in s.whosaidthat()


# -- sendhelp ---------------------------------------------------------------------

def test_sendhelp_requires_arguments(bot):
    s = make_say(bot)
    assert s.sendhelp("Someadmin", "") == "Please provide player & command"


def test_sendhelp_unknown_player(bot):
    s = make_say(bot, known_players=set())
    assert s.sendhelp("Someadmin", "Otherguy settings") == "Player Otherguy doesn't exist"


def test_sendhelp_self(bot):
    s = make_say(bot, known_players={"Someadmin"})
    assert s.sendhelp("Someadmin", "Someadmin settings") == "No use to send help to yourself"


def test_sendhelp_wrong_arg_count(bot):
    s = make_say(bot, known_players={"Otherguy"})
    assert s.sendhelp("Someadmin", "Otherguy") == "Can't send wrong command"


def test_sendhelp_sends_and_records(bot, monkeypatch):
    s = make_say(bot, known_players={"Otherguy"})
    sent = []
    monkeypatch.setattr(bot, "send_help", lambda to, command=False: sent.append((to, command)))
    result = s.sendhelp("Someadmin", "Otherguy settings")
    assert result == "Help sent to Otherguy"
    assert sent == [("Otherguy", "settings")]


# -- default/help fallback --------------------------------------------------------

def test_command_handler_unknown_command_sends_help(bot, monkeypatch):
    s = make_say(bot)
    sent = []
    monkeypatch.setattr(bot, "send_help", lambda to, command=False: sent.append(to))
    result = s.command_handler("Someadmin", "unknown", "tell")
    assert result is False
    assert sent == ["Someadmin"]
