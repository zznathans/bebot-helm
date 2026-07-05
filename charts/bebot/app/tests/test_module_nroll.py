"""Tests for main_modules/nroll.py (ported from Modules/nroll.php)."""
from __future__ import annotations

from bebot.main_modules.nroll import Nroll
from bebot.main_modules.tools import Tools
from fakes import FakeAccessControl


class _FakeAccessControlWithCreate(FakeAccessControl):
    def create(self, channel, command, access):
        pass


def make_nroll(bot) -> Nroll:
    bot.register_module(_FakeAccessControlWithCreate(), "access_control")
    Tools(bot)
    return Nroll(bot)


# -- construction -----------------------------------------------------------------

def test_registers_as_nroll_module(bot):
    n = make_nroll(bot)
    assert bot.core("nroll") is n


def test_registers_nroll_and_nverify_on_all_channels(bot):
    n = make_nroll(bot)
    for channel in ("tell", "gc", "pgmsg"):
        assert bot.commands[channel]["nroll"] is n
        assert bot.commands[channel]["nverify"] is n


# -- nroll ------------------------------------------------------------------------

def test_nroll_comma_separated_options(bot, monkeypatch):
    n = make_nroll(bot)
    monkeypatch.setattr(bot.core("tools"), "my_rand", lambda a, b: 1)
    result = n.command_handler("Chooser", "nroll red,blue,green", "tell")
    assert "I choose <font color=yellow>blue</font>" in result
    assert "nverify 0" in result


def test_nroll_space_separated_when_no_commas(bot, monkeypatch):
    n = make_nroll(bot)
    monkeypatch.setattr(bot.core("tools"), "my_rand", lambda a, b: 0)
    result = n.command_handler("Chooser", "nroll red blue green", "tell")
    assert "I choose <font color=yellow>red</font>" in result


def test_nroll_verify_id_is_zero_based_and_increments(bot, monkeypatch):
    n = make_nroll(bot)
    monkeypatch.setattr(bot.core("tools"), "my_rand", lambda a, b: 0)
    first = n.command_handler("Chooser", "nroll a,b", "tell")
    second = n.command_handler("Chooser", "nroll c,d", "tell")
    assert "nverify 0" in first
    assert "nverify 1" in second


# -- nverify ----------------------------------------------------------------------

def test_nverify_returns_recorded_choice(bot, monkeypatch):
    n = make_nroll(bot)
    monkeypatch.setattr(bot.core("tools"), "my_rand", lambda a, b: 0)
    n.command_handler("Chooser", "nroll red,blue", "tell")
    result = n.command_handler("Verifier", "nverify 0", "tell")
    assert "I chose <font color=yellow>red</font>" in result
    assert "for <font color=green>Chooser</font>" in result


def test_nverify_unknown_id(bot):
    n = make_nroll(bot)
    result = n.command_handler("Verifier", "nverify 5", "tell")
    assert result.startswith("Results not found")


def test_nverify_non_numeric_id(bot):
    n = make_nroll(bot)
    result = n.command_handler("Verifier", "nverify abc", "tell")
    assert result.startswith("Results not found")


def test_command_handler_no_match_returns_empty(bot):
    n = make_nroll(bot)
    assert n.command_handler("Someone", "nroll", "tell") == ""
