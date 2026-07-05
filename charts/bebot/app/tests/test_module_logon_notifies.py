from fakes import FakeSecurity, FakeSettings, RecordingModule

from bebot.main_modules.logon_notifies import LogonNotifies


class _FakeSettingsWithCreate(FakeSettings):
    """FakeSettings doesn't implement create() -- LogonNotifies.__init__ calls
    it to register its Notify_Delay/Startup_Delay/Enabled settings."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.created: list[tuple] = []

    def create(self, module, setting, value, longdesc, defaultoptions="", hidden=False, disporder=1):
        self.created.append((module, setting, value, longdesc))


def make_logon_notifies(bot, enabled=True, access=True, notify_check=True):
    settings = _FakeSettingsWithCreate({
        ("Logon_Notifies", "Enabled"): enabled,
        ("Logon_Notifies", "Notify_Delay"): 5,
        ("Logon_Notifies", "Startup_Delay"): 120,
    })
    security = FakeSecurity(access=access)
    bot.register_module(settings, "settings")
    bot.register_module(security, "security")
    if notify_check is not None:
        notify = RecordingModule("notify", return_value=notify_check)
        bot.register_module(notify, "notify")
    return LogonNotifies(bot)


# -- construction -----------------------------------------------------------

def test_registers_as_logon_notifies_module(bot):
    module = make_logon_notifies(bot)
    assert bot.core("logon_notifies") is module


def test_creates_default_settings(bot):
    make_logon_notifies(bot)
    settings = bot.core("settings")
    assert settings.get("Logon_Notifies", "Notify_Delay") == 5
    assert settings.get("Logon_Notifies", "Startup_Delay") == 120
    assert settings.get("Logon_Notifies", "Enabled") is True


# -- register / unregister ---------------------------------------------------

def test_register_and_unregister_track_modules(bot):
    module = make_logon_notifies(bot)
    sub = RecordingModule("subscriber")
    module.register(sub)
    assert type(sub).__name__ in module.modules
    module.unregister(sub)
    assert type(sub).__name__ not in module.modules


def test_unregister_unknown_module_is_a_noop(bot):
    module = make_logon_notifies(bot)
    sub = RecordingModule("subscriber")
    module.unregister(sub)  # never registered -- must not raise
    assert module.modules == {}


# -- buddy() ------------------------------------------------------------------

def test_buddy_logon_queues_a_notify_when_enabled_and_allowed(bot):
    module = make_logon_notifies(bot)
    module.buddy("Someguy", 1)
    assert "Someguy" in module.notifies
    assert module.waiting is True


def test_buddy_logoff_does_not_queue_a_notify(bot):
    module = make_logon_notifies(bot)
    module.buddy("Someguy", 0)
    assert "Someguy" not in module.notifies
    assert module.waiting is False


def test_buddy_disabled_setting_does_not_queue(bot):
    module = make_logon_notifies(bot, enabled=False)
    module.buddy("Someguy", 1)
    assert module.notifies == {}
    assert module.waiting is False


def test_buddy_denied_access_does_not_queue(bot):
    module = make_logon_notifies(bot, access=False)
    module.buddy("Someguy", 1)
    assert module.notifies == {}
    assert module.waiting is False


# -- connect() ----------------------------------------------------------------

def test_connect_sets_startup_from_settings(bot, monkeypatch):
    module = make_logon_notifies(bot)
    monkeypatch.setattr("bebot.main_modules.logon_notifies.time.time", lambda: 1000.0)
    module.connect()
    # startup_delay (120) + notify_delay (5) after "now"
    assert module.startup == 1000.0 + 120 + 5


# -- cron() ---------------------------------------------------------------------

def test_cron_does_nothing_when_not_waiting(bot):
    module = make_logon_notifies(bot)
    module.register(RecordingModule("subscriber"))
    module.cron()  # waiting is False -- must not raise or notify anyone


def test_cron_does_nothing_without_registered_modules(bot):
    module = make_logon_notifies(bot)
    module.buddy("Someguy", 1)
    assert module.waiting is True
    module.cron()  # no subscriber modules registered
    # Notify stays queued since there is nothing to flush it to.
    assert "Someguy" in module.notifies


def test_cron_fires_notify_on_registered_modules_once_due(bot, monkeypatch):
    module = make_logon_notifies(bot)
    module.startup = 1000.0  # startup grace period already elapsed by the time cron fires
    subscriber = RecordingModule("subscriber")
    module.register(subscriber)

    monkeypatch.setattr("bebot.main_modules.logon_notifies.time.time", lambda: 1000.0)
    module.buddy("Someguy", 1)
    assert module.notifies["Someguy"] == 1005.0

    monkeypatch.setattr("bebot.main_modules.logon_notifies.time.time", lambda: 1005.0)
    module.cron()

    assert subscriber.calls == [("notify", ("Someguy", False), {})]
    assert "Someguy" not in module.notifies
    # waiting stays True until the *next* cron() tick observes an empty queue
    # (this mirrors the PHP original's two-phase cron() flag reset).
    assert module.waiting is True
    module.cron()
    assert module.waiting is False


def test_cron_does_not_fire_before_delay_elapses(bot, monkeypatch):
    module = make_logon_notifies(bot)
    subscriber = RecordingModule("subscriber")
    module.register(subscriber)

    monkeypatch.setattr("bebot.main_modules.logon_notifies.time.time", lambda: 1000.0)
    module.buddy("Someguy", 1)

    monkeypatch.setattr("bebot.main_modules.logon_notifies.time.time", lambda: 1001.0)
    module.cron()

    assert subscriber.calls == []
    assert "Someguy" in module.notifies


def test_cron_marks_startup_true_before_startup_window_ends(bot, monkeypatch):
    module = make_logon_notifies(bot)
    subscriber = RecordingModule("subscriber")
    module.register(subscriber)
    module.startup = 2000.0  # still "starting up" for a while

    monkeypatch.setattr("bebot.main_modules.logon_notifies.time.time", lambda: 1000.0)
    module.buddy("Someguy", 1)

    monkeypatch.setattr("bebot.main_modules.logon_notifies.time.time", lambda: 1005.0)
    module.cron()

    assert subscriber.calls == [("notify", ("Someguy", True), {})]


# -- end-to-end wiring through Bot.register_event/unregister_event --------------

def test_bot_register_event_logon_notify_wires_into_real_module(bot):
    real = make_logon_notifies(bot)
    sub = RecordingModule("subscriber")

    result = bot.register_event("logon_notify", None, sub)
    assert result is False
    assert type(sub).__name__ in real.modules

    bot.unregister_event("logon_notify", None, sub)
    assert type(sub).__name__ not in real.modules
