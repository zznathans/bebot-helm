from bebot.main_modules.alts import Alts
from bebot.main_modules.security import Security
from bebot.main_modules.settings import Settings
from bebot.main_modules.time import TimeCore
from bebot.main_modules.timer_core import TimerCore
from bebot.main_modules.timer_ui import TimerUi
from bebot.main_modules.tools import Tools
from fakes import FakeAccessControl


class _FakeAccessControlWithCreate(FakeAccessControl):
    def create(self, channel, command, access):
        pass

    def create_subcommand(self, channel, command, sub, defaultlevel):
        pass


class FakeCommandAlias:
    def register(self, command, alias):
        pass

    def delete(self, alias):
        pass


def make_ui(bot, monkeypatch):
    bot.register_module(_FakeAccessControlWithCreate(), "access_control")
    bot.register_module(FakeCommandAlias(), "command_alias")
    Tools(bot)
    Settings(bot)
    Security(bot)
    Alts(bot)
    TimeCore(bot)
    TimerCore(bot)
    return TimerUi(bot)


# -- construction / registration --------------------------------------------------

def test_registers_as_timer_ui_module(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    assert bot.core("timer_ui") is module


def test_registers_commands_on_all_channels(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    for channel in ("tell", "gc", "pgmsg"):
        assert bot.commands[channel]["timer"] is module
        assert bot.commands[channel]["rtimer"] is module
        assert bot.commands[channel]["remtimer"] is module
        assert bot.commands[channel]["ptimer"] is module


def test_registers_as_timer_callback(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    assert bot.core("timer")._callbacks["timer_ui"] is module


def test_help_describes_commands(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    assert "timer" in module.help["command"]
    assert "ptimer" in module.help["command"]


# -- add_timer / timer command --------------------------------------------------

def test_timer_no_args_lists_no_timers(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    assert module.command_handler("Someuser", "timer", "tell") == "No timers defined!"


def test_timer_bad_syntax_returns_usage(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    result = module.command_handler("Someuser", "timer", "tell")
    assert result == "No timers defined!"
    result = module.command_handler("Someuser", "timer bogus", "tell")
    assert "Correct Format" in result


def test_timer_seconds_shorthand_starts_timer(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    result = module.command_handler("Someuser", "timer 30s Boss respawn", "tell")
    assert "Timer ##highlight##Boss respawn ##end##" in result
    assert "00:00:30" in result
    assert len(module._timers) == 1


def test_timer_colon_format_starts_timer(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    result = module.command_handler("Someuser", "timer 1:20 Reactor cooldown", "tell")
    assert "Reactor cooldown" in result
    ((_, meta),) = module._timers.items()
    assert meta["name"] == "Reactor cooldown"


def test_timer_lists_timer_after_creation(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    module.command_handler("Someuser", "timer 30s Boss respawn", "tell")
    result = module.command_handler("Someuser", "timer", "tell")
    assert "Boss respawn" in result
    assert "remtimer" in result


def test_timer_list_filters_by_channel(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    module.command_handler("Someuser", "timer 30s Guild event", "gc")
    # A "tell" listing for the same user shouldn't see the "gc" timer.
    result = module.command_handler("Someuser", "timer", "tell")
    assert result == "No timers defined!"
    result = module.command_handler("Someuser", "timer", "gc")
    assert "Guild event" in result


def test_timer_list_in_tell_scoped_to_owner(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    module.command_handler("Alice", "timer 30s Alice's timer", "tell")
    module.command_handler("Bob", "timer 30s Bob's timer", "tell")
    result = module.command_handler("Alice", "timer", "tell")
    assert "Alice's timer" in result
    assert "Bob's timer" not in result


# -- ptimer ---------------------------------------------------------------------

def test_ptimer_forces_gc_channel(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    module.command_handler("Someuser", "ptimer 30s Org event", "tell")
    ((_, meta),) = module._timers.items()
    assert meta["channel"] == "gc"


def test_ptimer_bare_lists_gc_timers(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    module.command_handler("Someuser", "timer 30s Org event", "gc")
    result = module.command_handler("Someuser", "ptimer", "tell")
    assert "Org event" in result


# -- rtimer -----------------------------------------------------------------------

def test_rtimer_starts_repeating_timer(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    result = module.command_handler("Someuser", "rtimer 30s 60s Wave spawn", "tell")
    assert "repeat interval" in result
    ((_, meta),) = module._timers.items()
    assert meta["repeat"] == 60


def test_rtimer_below_min_repeat_interval_rejected(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    result = module.command_handler("Someuser", "rtimer 30s 5s Too fast", "tell")
    assert "must be at least" in result
    assert module._timers == {}


def test_rtimer_bad_syntax_returns_usage(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    result = module.command_handler("Someuser", "rtimer nonsense", "tell")
    assert "Correct Format" in result


# -- remtimer ---------------------------------------------------------------------

def test_remtimer_missing_id(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    assert module.command_handler("Someuser", "remtimer", "tell") == "No timer id provided."


def test_remtimer_invalid_id_reports_no_id(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    assert module.command_handler("Someuser", "remtimer abc", "tell") == "No timer id provided."


def test_remtimer_unknown_id(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    result = module.command_handler("Someuser", "remtimer 999", "tell")
    assert result.get() == "Invalid timer ID!"


def test_remtimer_owner_can_delete_own_timer(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    module.command_handler("Someuser", "timer 30s Boss respawn", "tell")
    (timer_id,) = module._timers.keys()
    result = module.command_handler("Someuser", f"remtimer {timer_id}", "tell")
    assert "was deleted" in result
    assert module._timers == {}


def test_remtimer_denies_other_regular_user(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    module.command_handler("Owner1", "timer 30s Boss respawn", "tell")
    (timer_id,) = module._timers.keys()
    result = module.command_handler("Randomguy", f"remtimer {timer_id}", "tell")
    assert result.get() == "You are not allowed to delete this timer!"
    assert timer_id in module._timers


def test_remtimer_admin_can_delete_and_owner_gets_notified(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    bot.core("security").super_admin = {"Adminuser": True}
    module.command_handler("Owner1", "timer 30s Boss respawn", "tell")
    (timer_id,) = module._timers.keys()

    sent = []
    monkeypatch.setattr(bot, "send_output", lambda *a, **kw: sent.append(a))
    result = module.command_handler("Adminuser", f"remtimer {timer_id}", "tell")
    assert "was deleted" in result
    assert len(sent) == 1
    to, msg, kind = sent[0]
    assert to == "Owner1"
    assert "deleted by##highlight## Adminuser" in msg
    assert kind == "tell"


# -- timed_event (fired by timer_core.check_timers()) ----------------------------

def test_timed_event_sends_expiry_message_and_forgets_timer(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    module.command_handler("Someuser", "timer 1s Boss respawn", "tell")
    (timer_id,) = module._timers.keys()

    sent = []
    monkeypatch.setattr(bot, "send_output", lambda *a, **kw: sent.append(a))
    module.timed_event(timer_id, {"owner": "Someuser", "name": "Boss respawn", "channel": "tell", "repeat": 0})

    assert len(sent) == 1
    to, msg, kind = sent[0]
    assert to == "Someuser"
    assert "Boss respawn" in msg
    assert ", ##highlight##" not in msg  # channel == "tell": no owner-name suffix
    assert kind == "tell"
    assert timer_id not in module._timers


def test_timed_event_appends_owner_name_for_non_tell_channels(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    sent = []
    monkeypatch.setattr(bot, "send_output", lambda *a, **kw: sent.append(a))
    module.timed_event(1, {"owner": "Someuser", "name": "Guild event", "channel": "gc", "repeat": 0})
    _, msg, _ = sent[0]
    assert ", ##highlight##Someuser##end##!" in msg


def test_timed_event_reschedules_repeating_timer(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    monkeypatch.setattr(bot, "send_output", lambda *a, **kw: None)
    module.timed_event(1, {"owner": "Someuser", "name": "Wave spawn", "channel": "tell", "repeat": 60})
    assert len(module._timers) == 1
    ((_, meta),) = module._timers.items()
    assert meta["name"] == "Wave spawn"
    assert meta["repeat"] == 60


def test_check_timers_fires_timed_event_via_timer_core(bot, monkeypatch):
    """End-to-end: TimerUi schedules through the real TimerCore, and
    TimerCore.check_timers() drives TimerUi.timed_event() when it's due."""
    module = make_ui(bot, monkeypatch)
    module.command_handler("Someuser", "timer 1s Boss respawn", "tell")
    (timer_id,) = module._timers.keys()

    sent = []
    monkeypatch.setattr(bot, "send_output", lambda *a, **kw: sent.append(a))
    monkeypatch.setattr("bebot.main_modules.timer_core.time.time", lambda: module._timers[timer_id]["endtime"] + 1)
    bot.core("timer").check_timers()

    assert len(sent) == 1
    assert timer_id not in module._timers
