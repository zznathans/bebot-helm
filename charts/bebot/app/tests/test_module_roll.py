"""Tests for main_modules/roll.py (ported from Modules/Roll.php)."""
from __future__ import annotations

from bebot.commodities.base import BotError
from bebot.main_modules.roll import Roll
from bebot.main_modules.settings import Settings
from bebot.main_modules.tools import Tools
from fakes import FakeAccessControl


class _FakeAccessControlWithCreate(FakeAccessControl):
    def create(self, channel, command, access):
        pass


def make_roll(bot) -> Roll:
    bot.register_module(_FakeAccessControlWithCreate(), "access_control")
    Tools(bot)
    Settings(bot)
    return Roll(bot)


# -- construction -----------------------------------------------------------------

def test_registers_as_roll_module(bot):
    r = make_roll(bot)
    assert bot.core("roll") is r


def test_registers_roll_and_flip_on_all_channels(bot):
    r = make_roll(bot)
    for channel in ("tell", "gc", "pgmsg"):
        assert bot.commands[channel]["roll"] is r
        assert bot.commands[channel]["flip"] is r


def test_registers_verify_tell_only(bot):
    r = make_roll(bot)
    assert bot.commands["tell"]["verify"] is r
    assert "verify" not in bot.commands.get("gc", {})


def test_creates_rolltime_setting(bot):
    make_roll(bot)
    assert bot.core("settings").get("Roll", "RollTime") == 30


# -- do_roll --------------------------------------------------------------------

def test_roll_min_max_produces_result_in_range(bot, monkeypatch):
    r = make_roll(bot)
    monkeypatch.setattr(bot.core("tools"), "my_rand", lambda a, b: b)
    result = r.command_handler("Roller", "roll 1 100", "tell")
    assert "Result: 100" in result
    assert "Range: 1 - 100" in result


def test_roll_single_arg_treated_as_max_with_min_1(bot, monkeypatch):
    r = make_roll(bot)
    monkeypatch.setattr(bot.core("tools"), "my_rand", lambda a, b: a)
    result = r.command_handler("Roller", "roll 50", "tell")
    assert "Range: 1 - 50" in result
    assert "Result: 1" in result


def test_roll_missing_max_errors(bot):
    r = make_roll(bot)
    result = r.do_roll("Roller", "1", "", "")
    assert isinstance(result, BotError)
    assert "specify a maximum value" in str(result)


def test_roll_non_integer_errors(bot):
    r = make_roll(bot)
    result = r.do_roll("Roller", "abc", "100", "")
    assert isinstance(result, BotError)
    assert "need to be an integer" in str(result)


def test_roll_max_below_2_errors(bot):
    r = make_roll(bot)
    result = r.do_roll("Roller", "1", "1", "")
    assert isinstance(result, BotError)
    assert "less than one person" in str(result)


def test_roll_cooldown_blocks_second_roll(bot, monkeypatch):
    r = make_roll(bot)
    monkeypatch.setattr(bot.core("tools"), "my_rand", lambda a, b: a)
    r.command_handler("Roller", "roll 1 10", "tell")
    result = r.command_handler("Roller", "roll 1 10", "tell")
    assert result == "You may only roll once every 30 seconds."


def test_roll_item_is_recorded(bot, monkeypatch):
    r = make_roll(bot)
    monkeypatch.setattr(bot.core("tools"), "my_rand", lambda a, b: a)
    result = r.command_handler("Roller", "roll 1 10 the loot", "tell")
    assert "Target: ##highlight##'the loot'##end##" in result


# -- do_flip --------------------------------------------------------------------

def test_flip_produces_heads_or_tails(bot, monkeypatch):
    r = make_roll(bot)
    monkeypatch.setattr(bot.core("tools"), "my_rand", lambda a, b: 1)
    result = r.command_handler("Flipper", "flip", "tell")
    assert "Result: heads" in result


def test_flip_shares_cooldown_pool_with_roll(bot, monkeypatch):
    r = make_roll(bot)
    monkeypatch.setattr(bot.core("tools"), "my_rand", lambda a, b: a)
    r.command_handler("Someone", "roll 1 10", "tell")
    result = r.command_handler("Someone", "flip", "tell")
    assert result == "You may only flip once every 30 seconds."


# -- verify -----------------------------------------------------------------------

def test_verify_no_rolls_yet_is_invalid(bot):
    r = make_roll(bot)
    result = r.command_handler("Verifier", "verify", "tell")
    assert isinstance(result, BotError)
    assert "Invalid verification ID" in str(result)


def test_verify_out_of_range_is_invalid(bot, monkeypatch):
    r = make_roll(bot)
    monkeypatch.setattr(bot.core("tools"), "my_rand", lambda a, b: a)
    r.command_handler("Roller", "roll 1 10", "tell")
    result = r.command_handler("Verifier", "verify 99", "tell")
    assert isinstance(result, BotError)


def test_verify_zero_mirrors_php_empty_and_shows_latest(bot, monkeypatch):
    """PHP's empty("0") is true, so "verify 0" is redirected to "show the
    latest roll" before the bound check -- same as bare "verify"."""
    r = make_roll(bot)
    monkeypatch.setattr(bot.core("tools"), "my_rand", lambda a, b: a)
    r.command_handler("Roller", "roll 1 10", "tell")
    result = r.command_handler("Verifier", "verify 0", "tell")
    assert "Verify id: 1" in result


def test_verify_empty_shows_latest_roll(bot, monkeypatch):
    r = make_roll(bot)
    monkeypatch.setattr(bot.core("tools"), "my_rand", lambda a, b: a)
    r.command_handler("Roller", "roll 1 10", "tell")
    result = r.command_handler("Verifier", "verify", "tell")
    assert "Verify id: 1" in result
