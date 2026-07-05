"""Tests for main_modules/set_debug.py (ported from Modules/SetDebug.php)."""
from __future__ import annotations

from bebot.main_modules.set_debug import SetDebug


def test_registers_as_set_debug_module(bot):
    module = SetDebug(bot)
    assert bot.core("set_debug") is module


def test_registers_setdebug_on_tell_only(bot):
    module = SetDebug(bot)
    assert bot.commands["tell"]["setdebug"] is module
    assert "setdebug" not in bot.commands.get("gc", {})
    assert "setdebug" not in bot.commands.get("pgmsg", {})


def test_toggles_debug_on(bot):
    bot.debug = False
    module = SetDebug(bot)
    result = module.command_handler("Owner", "setdebug", "tell")
    assert bot.debug is True
    assert result == "Debugging output enabled!"


def test_toggles_debug_off(bot):
    bot.debug = True
    module = SetDebug(bot)
    result = module.command_handler("Owner", "setdebug", "tell")
    assert bot.debug is False
    assert result == "Debugging output disabled!"


def test_toggles_back_and_forth(bot):
    module = SetDebug(bot)
    bot.debug = False
    module.command_handler("Owner", "setdebug", "tell")
    module.command_handler("Owner", "setdebug", "tell")
    assert bot.debug is False
