"""Tests for main_modules/timer_relay.py (ported/redesigned from
Modules/TimerRelay.php -- see the module docstring for why this no longer
implements the PHP's multi-bot relay-bridge wire format).
"""
from __future__ import annotations

from bebot.main_modules.settings import Settings
from bebot.main_modules.timer_core import TimerCore
from bebot.main_modules.timer_relay import TimerRelay


def make_timer_relay(bot) -> TimerRelay:
    Settings(bot)
    TimerCore(bot)
    return TimerRelay(bot)


# -- construction / registration ------------------------------------------------

def test_registers_as_timer_relay_module(bot):
    module = make_timer_relay(bot)
    assert bot.core("timer_relay") is module


def test_registers_relaytimer_on_tell_only(bot):
    module = make_timer_relay(bot)
    assert bot.commands["tell"]["relaytimer"] is module
    assert "relaytimer" not in bot.commands.get("gc", {})


def test_registers_timer_callback(bot):
    make_timer_relay(bot)
    timer = bot.core("timer")
    assert "timer_relay" in timer._callbacks


# -- command_handler / scheduling -----------------------------------------------

def test_schedules_a_timer_and_confirms(bot):
    module = make_timer_relay(bot)
    result = module.command_handler("Admin", "relaytimer 30 Raid Start", "tell")
    assert result == "Timer 'Raid Start' scheduled to be announced in 30 second(s)."
    timer = bot.core("timer")
    assert len(timer._timers) == 1
    assert timer._timers[0]["owner"] == "timer_relay"


def test_invalid_message_sends_help_and_returns_false(bot):
    module = make_timer_relay(bot)
    result = module.command_handler("Admin", "relaytimer", "tell")
    assert result is False


# -- timed_event announcement ---------------------------------------------------

def test_timed_event_announces_to_gc_and_pgroup_by_default(bot, monkeypatch):
    module = make_timer_relay(bot)
    gc_msgs = []
    pg_msgs = []
    monkeypatch.setattr(bot, "send_gc", lambda msg, *a, **kw: gc_msgs.append(msg))
    monkeypatch.setattr(bot, "send_pgroup", lambda msg, *a, **kw: pg_msgs.append(msg))

    module.command_handler("Admin", "relaytimer 5 Raid Start", "tell")
    timer_id = next(iter(module._pending))
    module.timed_event(timer_id, module._pending[timer_id])

    assert any("Raid Start" in m for m in gc_msgs)
    assert any("Raid Start" in m for m in pg_msgs)
    assert timer_id not in module._pending


def test_timed_event_quiet_relay_tells_requester_only(bot, monkeypatch):
    module = make_timer_relay(bot)
    module.bot.core("settings").save("TimerRelay", "QuietRelay", True)
    gc_msgs = []
    tell_msgs = []
    monkeypatch.setattr(bot, "send_gc", lambda msg, *a, **kw: gc_msgs.append(msg))
    monkeypatch.setattr(bot, "send_pgroup", lambda msg, *a, **kw: None)
    monkeypatch.setattr(bot, "send_tell", lambda to, msg, *a, **kw: tell_msgs.append((to, msg)))

    module.command_handler("Admin", "relaytimer 5 Raid Start", "tell")
    timer_id = next(iter(module._pending))
    module.timed_event(timer_id, module._pending[timer_id])

    assert gc_msgs == []
    assert tell_msgs and tell_msgs[0][0] == "Admin"
    assert "Raid Start" in tell_msgs[0][1]


def test_timer_core_check_timers_fires_timed_event(bot, monkeypatch):
    module = make_timer_relay(bot)
    announced = []
    monkeypatch.setattr(bot, "send_gc", lambda msg, *a, **kw: announced.append(msg))
    monkeypatch.setattr(bot, "send_pgroup", lambda msg, *a, **kw: None)

    module.command_handler("Admin", "relaytimer 0 Instant", "tell")
    bot.core("timer").check_timers()

    assert any("Instant" in m for m in announced)
