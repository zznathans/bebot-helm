import time

from fakes import FakeTimer, RecordingModule


def test_cronjob_runs_due_job_and_reschedules(bot):
    mod = RecordingModule()
    bot.register_event("cron", 60, mod)
    now = time.time()
    bot._cron_job_timer[60] = now - 1
    bot.cronjob(now, 60)
    assert mod.calls == [("cron", (60,), {})]
    assert bot._cron_job_timer[60] > now


def test_cronjob_skips_when_not_due(bot):
    mod = RecordingModule()
    bot.register_event("cron", 60, mod)
    now = time.time()
    bot._cron_job_timer[60] = now + 1000
    bot.cronjob(now, 60)
    assert mod.calls == []


def test_cronjob_skips_when_already_active(bot):
    mod = RecordingModule()
    bot.register_event("cron", 60, mod)
    now = time.time()
    bot._cron_job_timer[60] = now - 1
    bot._cron_job_active[60] = True
    bot.cronjob(now, 60)
    assert mod.calls == []


def test_cron_noop_when_not_activated(bot):
    timer = FakeTimer()
    bot.register_module(timer, "timer")
    bot.cron_activated = False
    bot.cron()
    assert timer.checked is False


def test_cron_dispatches_due_jobs_when_activated(bot):
    timer = FakeTimer()
    bot.register_module(timer, "timer")
    mod = RecordingModule()
    bot.register_event("cron", 60, mod)
    bot._cron_job_timer[60] = time.time() - 1
    bot.cron_activated = True
    bot.cron()
    assert timer.checked is True
    assert mod.calls == [("cron", (60,), {})]
