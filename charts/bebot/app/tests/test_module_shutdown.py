"""Tests for main_modules/shutdown.py (ported from Modules/Shutdown.php)."""
from __future__ import annotations

import time

import pytest

from bebot.main_modules.settings import Settings
from bebot.main_modules.shutdown import Shutdown


def make_shutdown(bot) -> Shutdown:
    Settings(bot)
    bot.connected_time = time.time() - 100  # past the 10s startup grace period
    return Shutdown(bot)


# -- construction / registration ------------------------------------------------

def test_registers_as_shutdown_module(bot):
    module = make_shutdown(bot)
    assert bot.core("shutdown") is module


def test_registers_shutdown_and_restart_on_tell_only(bot):
    module = make_shutdown(bot)
    assert bot.commands["tell"]["shutdown"] is module
    assert bot.commands["tell"]["restart"] is module
    assert "shutdown" not in bot.commands.get("gc", {})
    assert "restart" not in bot.commands.get("gc", {})


# -- command_handler --------------------------------------------------------------

def test_ignored_within_first_ten_seconds(bot):
    Settings(bot)
    bot.connected_time = time.time()
    module = Shutdown(bot)
    result = module.command_handler("Admin", "shutdown", "tell")
    assert result is False
    assert module.crontime is None


def test_shutdown_schedules_crontime_and_registers_cron(bot):
    module = make_shutdown(bot)
    result = module.command_handler("Admin", "shutdown", "tell")
    assert result is False
    assert module.crontime is not None
    assert module.crontime[1] == "The bot has been shutdown."
    assert "Shutdown" in bot._cron_jobs.get(1, {})


def test_restart_uses_restarting_text(bot):
    module = make_shutdown(bot)
    module.command_handler("Admin", "restart", "tell")
    assert module.crontime[1] == "The bot is restarting."


def test_unknown_command_returns_error(bot):
    module = make_shutdown(bot)
    result = module.command_handler("Admin", "blorp", "tell")
    assert "Unknown Command" in result
    assert "blorp" in result


# -- cron ---------------------------------------------------------------------

def test_cron_does_nothing_before_due(bot):
    module = make_shutdown(bot)
    module.crontime = (time.time() + 100, "The bot has been shutdown.")
    module.cron(1)  # should not raise / exit


def test_cron_disconnects_and_exits_when_due(bot, monkeypatch):
    module = make_shutdown(bot)
    disconnected = []
    monkeypatch.setattr(bot, "disconnect", lambda: disconnected.append(True))
    module.crontime = (time.time() - 1, "The bot has been shutdown.")
    with pytest.raises(SystemExit) as exc_info:
        module.cron(1)
    assert disconnected == [True]
    assert exc_info.value.code == 0


def test_cron_noop_when_never_scheduled(bot):
    module = make_shutdown(bot)
    module.cron(1)  # crontime is still None, must not raise
