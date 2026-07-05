from bebot.main_modules.command_alias import CommandAlias
from bebot.main_modules.countdown import Countdown
from bebot.main_modules.settings import Settings
from bebot.main_modules.timer_core import TimerCore
from bebot.main_modules.tools import Tools
from fakes import FakeAccessControl


class _FakeAccessControlWithCreate(FakeAccessControl):
    def create(self, channel, command, access):
        pass


def make_module(bot) -> Countdown:
    bot.register_module(_FakeAccessControlWithCreate(), "access_control")
    Tools(bot)
    Settings(bot)
    CommandAlias(bot)
    TimerCore(bot)
    return Countdown(bot)


# -- construction / registration --------------------------------------------------

def test_registers_as_countdown_module(bot):
    module = make_module(bot)
    assert bot.core("countdown") is module


def test_registers_countdown_command_on_all_channels(bot):
    module = make_module(bot)
    for channel in ("tell", "gc", "pgmsg"):
        assert bot.commands[channel]["countdown"] is module


def test_registers_cd_alias(bot):
    make_module(bot)
    assert bot.core("command_alias").exists("cd")
    assert bot.core("command_alias").replace("cd") == "countdown"


def test_help_describes_command(bot):
    module = make_module(bot)
    assert "countdown" in module.help["command"]


def test_registers_timer_callback(bot):
    module = make_module(bot)
    assert bot.core("timer")._callbacks["countdown"] is module


def test_creates_channel_setting(bot):
    make_module(bot)
    assert bot.core("settings").get("Countdown", "Channel") == "both"


# -- command_handler: schedules six staged timers -----------------------------------

def test_command_handler_schedules_six_timers(bot):
    module = make_module(bot)
    result = module.command_handler("Someuser", "countdown", "gc")
    assert result == "Countdown started!"
    timers = bot.core("timer")._timers
    assert len(timers) == 6
    assert all(t["owner"] == "countdown" for t in timers)
    texts = [t["data"]["text"] for t in timers]
    assert any("5" in text for text in texts)
    assert any("GO GO GO" in text for text in texts)


def test_command_handler_carries_name_and_origin(bot):
    module = make_module(bot)
    module.command_handler("Someuser", "countdown", "gc")
    timers = bot.core("timer")._timers
    for t in timers:
        assert t["data"]["name"] == "Someuser"
        assert t["data"]["origin"] == "gc"


# -- timed_event: sends staged message to configured channel -------------------------

def test_timed_event_default_channel_is_both(bot, monkeypatch):
    module = make_module(bot)
    calls = []
    monkeypatch.setattr(bot, "send_output", lambda name, msg, kind, low=0: calls.append((name, msg, kind)))
    module.timed_event(1, {"name": "Someuser", "origin": "gc", "text": "STEP"})
    assert calls == [("Someuser", "STEP", "both")]


def test_timed_event_respects_origin_channel_setting(bot, monkeypatch):
    module = make_module(bot)
    bot.core("settings").save("Countdown", "Channel", "origin")
    calls = []
    monkeypatch.setattr(bot, "send_output", lambda name, msg, kind, low=0: calls.append((name, msg, kind)))
    module.timed_event(1, {"name": "Someuser", "origin": "pgmsg", "text": "STEP"})
    assert calls == [("Someuser", "STEP", "pgmsg")]


def test_timed_event_respects_explicit_channel_setting(bot, monkeypatch):
    module = make_module(bot)
    bot.core("settings").save("Countdown", "Channel", "gc")
    calls = []
    monkeypatch.setattr(bot, "send_output", lambda name, msg, kind, low=0: calls.append((name, msg, kind)))
    module.timed_event(1, {"name": "Someuser", "origin": "pgmsg", "text": "STEP"})
    assert calls == [("Someuser", "STEP", "gc")]


# -- end-to-end: firing the scheduled timers dispatches all six steps ----------------

def test_full_countdown_fires_all_steps_in_order(bot, monkeypatch):
    module = make_module(bot)
    calls = []
    monkeypatch.setattr(bot, "send_output", lambda name, msg, kind, low=0: calls.append(msg))

    fake_now = [1000.0]
    monkeypatch.setattr("bebot.main_modules.timer_core.time.time", lambda: fake_now[0])

    module.command_handler("Someuser", "countdown", "gc")
    timer = bot.core("timer")
    for step_seconds in range(1, 7):
        fake_now[0] = 1000.0 + step_seconds
        timer.check_timers()

    assert len(calls) == 6
    assert "5" in calls[0]
    assert "4" in calls[1]
    assert "3" in calls[2]
    assert "2" in calls[3]
    assert "1" in calls[4]
    assert "GO GO GO" in calls[5]
