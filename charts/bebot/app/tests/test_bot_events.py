import pytest

from bebot.bot import _parse_cron_interval
from fakes import FakeLogonNotifies, FakeTimer, RecordingModule


@pytest.mark.parametrize(
    "target,expected",
    [
        ("1sec", 1),
        ("30seconds", 30),
        ("5min", 300),
        ("5minutes", 300),
        ("2hour", 7200),
        ("1day", 86400),
        ("not-a-duration", 0),
        ("", 0),
    ],
)
def test_parse_cron_interval(target, expected):
    assert _parse_cron_interval(target) == expected


def test_register_event_rejects_unknown_event(bot):
    mod = RecordingModule()
    result = bot.register_event("not-a-real-event", None, mod)
    assert "invalid" in result
    assert not bot.exists_command("not-a-real-event", "anything")


def test_register_event_generic_stores_module_by_type_name(bot):
    mod = RecordingModule()
    result = bot.register_event("connect", None, mod)
    assert result is False
    assert bot.commands["connect"]["RecordingModule"] is mod


def test_register_event_gmsg_requires_target(bot):
    mod = RecordingModule()
    result = bot.register_event("gmsg", "", mod)
    assert "No channel specified" in result


def test_register_event_gmsg_registers_under_target(bot):
    mod = RecordingModule()
    result = bot.register_event("gmsg", "MyOrg", mod)
    assert result is False
    assert bot.commands["gmsg"]["MyOrg"]["RecordingModule"] is mod


def test_register_event_cron_with_numeric_target(bot):
    mod = RecordingModule()
    result = bot.register_event("cron", 60, mod)
    assert result is False
    assert bot._cron_jobs[60]["RecordingModule"] is mod
    assert bot._cron_times[60] == 60


def test_register_event_cron_with_string_interval(bot):
    mod = RecordingModule()
    result = bot.register_event("cron", "5min", mod)
    assert result is False
    assert bot._cron_jobs[300]["RecordingModule"] is mod


def test_register_event_cron_invalid_interval(bot):
    mod = RecordingModule()
    result = bot.register_event("cron", "not-a-duration", mod)
    assert "invalid" in result
    assert 0 not in bot._cron_jobs


def test_register_event_timer_requires_target(bot):
    mod = RecordingModule()
    result = bot.register_event("timer", "", mod)
    assert "No name" in result


def test_register_event_timer_delegates_to_timer_module(bot):
    timer = FakeTimer()
    bot.register_module(timer, "timer")
    mod = RecordingModule()
    result = bot.register_event("timer", "mytimer", mod)
    assert result is False
    assert timer.registered["mytimer"] is mod


def test_register_event_logon_notify_delegates(bot):
    logon = FakeLogonNotifies()
    bot.register_module(logon, "logon_notifies")
    mod = RecordingModule()
    result = bot.register_event("logon_notify", None, mod)
    assert result is False
    assert mod in logon.registered


def test_register_event_settings_requires_module_and_setting(bot):
    mod = RecordingModule()
    result = bot.register_event("settings", {"module": "Core"}, mod)
    assert "No module and/or setting" in result


def test_register_event_settings_delegates(bot):
    recorded = {}

    class SettingsStub:
        def register_callback(self, module, setting, target_module):
            recorded["args"] = (module, setting, target_module)
            return False

    bot.register_module(SettingsStub(), "settings")
    mod = RecordingModule()
    result = bot.register_event("settings", {"module": "Core", "setting": "Foo"}, mod)
    assert result is False
    assert recorded["args"] == ("Core", "Foo", mod)


def test_register_event_irc_is_a_noop(bot):
    mod = RecordingModule()
    assert bot.register_event("irc", None, mod) is False


def test_unregister_event_generic(bot):
    mod = RecordingModule()
    bot.register_event("connect", None, mod)
    bot.unregister_event("connect", None, mod)
    assert "RecordingModule" not in bot.commands.get("connect", {})


def test_unregister_event_gmsg(bot):
    mod = RecordingModule()
    bot.register_event("gmsg", "MyOrg", mod)
    bot.unregister_event("gmsg", "MyOrg", mod)
    assert "RecordingModule" not in bot.commands["gmsg"]["MyOrg"]


def test_unregister_event_cron(bot):
    mod = RecordingModule()
    bot.register_event("cron", 60, mod)
    bot.unregister_event("cron", 60, mod)
    assert "RecordingModule" not in bot._cron_jobs[60]


def test_unregister_event_timer_delegates(bot):
    timer = FakeTimer()
    bot.register_module(timer, "timer")
    timer.registered["mytimer"] = "placeholder"
    bot.unregister_event("timer", "mytimer", RecordingModule())
    assert "mytimer" not in timer.registered


def test_unregister_event_logon_notify_delegates(bot):
    logon = FakeLogonNotifies()
    bot.register_module(logon, "logon_notifies")
    mod = RecordingModule()
    logon.registered.append(mod)
    bot.unregister_event("logon_notify", None, mod)
    assert mod not in logon.registered


def test_unregister_event_settings_requires_module_and_setting(bot):
    result = bot.unregister_event("settings", {"module": "Core"}, RecordingModule())
    assert "No module and/or setting" in result
