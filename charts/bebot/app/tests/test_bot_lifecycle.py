import pytest

from bebot.bot import _DummyModule
from fakes import FakeAOChat, RecordingModule


def test_disconnect_calls_aoc_disconnect_and_dispatches(bot):
    fake_aoc = FakeAOChat()
    bot.aoc = fake_aoc
    mod = RecordingModule()
    bot.register_event("disconnect", None, mod)
    bot.disconnect()
    assert fake_aoc.disconnected is True
    assert mod.calls == [("disconnect", (), {})]


@pytest.mark.asyncio
async def test_connect_success_runs_full_lifecycle(bot):
    bot.aoc = FakeAOChat(connect_result=True)
    connected = []
    bot.register_event("connect", None, RecordingModule())
    real_mod = bot.commands["connect"]["RecordingModule"]

    def on_connect():
        connected.append(True)

    real_mod.connect = on_connect

    await bot.connect()

    assert bot.aoc.calls[0][0] == "connect"
    assert bot.aoc.calls[1][0] == "authenticate"
    assert bot.aoc.calls[2][0] == "login"
    assert bot.username is None
    assert bot.password is None
    assert bot.cron_activated is True
    assert bot.connected_time is not None
    assert connected == [True]


@pytest.mark.asyncio
async def test_connect_failure_disconnects_and_exits(bot):
    bot.aoc = FakeAOChat(connect_result=False)
    bot.reconnecttime = 0
    with pytest.raises(SystemExit):
        await bot.connect()
    assert bot.aoc.disconnected is True
    assert bot.cron_activated is False


@pytest.mark.asyncio
async def test_reconnect_disconnects_and_exits(bot):
    bot.aoc = FakeAOChat()
    bot.reconnecttime = 0
    with pytest.raises(SystemExit):
        await bot.reconnect()
    assert bot.aoc.disconnected is True
    assert bot.cron_activated is False


def test_debug_bt_returns_empty_string(bot):
    assert bot.debug_bt() == ""


def test_dummy_module_is_falsy(bot):
    dummy = _DummyModule(bot, "missing")
    assert bool(dummy) is False


def test_dummy_module_logs_and_returns_error_on_any_call(bot):
    logged = []
    bot.log = lambda *a, **kw: logged.append(a)
    dummy = _DummyModule(bot, "missing")
    result = dummy.whatever(1, 2)
    assert "missing" in result
    assert logged[0][0] == "CORE"
    assert logged[0][1] == "ERROR"
