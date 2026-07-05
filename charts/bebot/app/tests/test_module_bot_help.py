"""Tests for main_modules/bot_help.py (ported from Main/15_BotHelp.php).

Regression coverage for a real bug: show_help() built the ##blob_title##
HTML window but returned it raw instead of passing it through
tools.make_blob(), so `help <command>` sent the whole blob body as a
direct tell instead of a clickable info-window link -- unlike
show_help_menu(), which already wrapped its output correctly.
"""
from __future__ import annotations

from bebot.commodities.base import BaseActiveModule
from bebot.main_modules.access_control import AccessControl
from bebot.main_modules.bot_help import BotHelp
from bebot.main_modules.security import Security
from bebot.main_modules.settings import Settings
from bebot.main_modules.tools import Tools


class FakeCommandModule(BaseActiveModule):
    def __init__(self, bot, help_data=None):
        super().__init__(bot, "FakeCommandModule")
        self.help = help_data or {}
        self.register_command("tell", "foo", "GUEST")

    def command_handler(self, name, msg, origin):
        return "ok"


def make_help(bot) -> BotHelp:
    Settings(bot)
    Security(bot)
    AccessControl(bot)
    Tools(bot)
    return BotHelp(bot)


def test_show_help_wraps_output_in_a_blob(bot):
    help_module = make_help(bot)
    FakeCommandModule(bot, {"description": "Does a thing.", "command": {"foo bar": "does bar"}})

    result = help_module.show_help(bot.owner, "foo")

    assert result.startswith('<a href="text://')
    assert "Does a thing." in result
    assert "does bar" in result


def test_show_help_unknown_command_returns_plain_error(bot):
    help_module = make_help(bot)

    result = help_module.show_help(bot.owner, "nonexistent")

    assert "does not exist" in result
    assert not result.startswith('<a href="text://')


def test_bare_help_command_populates_cache_and_lists_registered_commands(bot):
    """Regression test: command_handler() never called update_cache(), so
    help_cache stayed {} forever and the bare `help` menu was always blank
    -- matches Main/15_BotHelp.php's command_handler(), which lazily calls
    update_cache() the first time help_cache is empty."""
    help_module = make_help(bot)
    FakeCommandModule(bot, {"description": "Does a thing."})

    result = help_module.command_handler(bot.owner, "help", "tell")

    assert "foo" in result
