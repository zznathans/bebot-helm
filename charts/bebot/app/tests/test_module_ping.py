"""Tests for main_modules/ping.py (ported from Modules/Ping.php).

`_execute()` is monkeypatched in every test that would otherwise shell out
to a real `ping`/`traceroute`/`tracert` binary, keeping these tests
hermetic and fast.
"""
from __future__ import annotations

from bebot.main_modules.ping import Ping
from bebot.main_modules.settings import Settings
from bebot.main_modules.tools import Tools
from fakes import FakeAccessControl


class _FakeAccessControlWithCreate(FakeAccessControl):
    def create(self, channel, command, access):
        pass


def make_ping(bot, server="chat.d1.funcom.com") -> Ping:
    bot.register_module(_FakeAccessControlWithCreate(), "access_control")
    Tools(bot)
    Settings(bot)
    bot.server = server
    return Ping(bot)


# -- construction -----------------------------------------------------------------

def test_registers_as_ping_module(bot):
    p = make_ping(bot)
    assert bot.core("ping") is p


def test_registers_commands_owner_only(bot):
    p = make_ping(bot)
    for channel in ("tell", "gc", "pgmsg"):
        assert bot.commands[channel]["ping"] is p
        assert bot.commands[channel]["tracert"] is p
    assert bot.core("access_control").calls == []


def test_creates_settings(bot):
    make_ping(bot)
    assert bot.core("settings").get("Ping", "Server") == "Windows"
    assert bot.core("settings").get("Ping", "PingCount") == 4


# -- ping_server ------------------------------------------------------------------

def test_ping_server_windows_uses_ping_dash_n(bot, monkeypatch):
    p = make_ping(bot)
    captured = {}

    def fake_execute(cmd):
        captured["cmd"] = cmd
        return ["Reply from chat.d1.funcom.com: bytes=32 time=10ms"]

    monkeypatch.setattr(p, "_execute", fake_execute)
    result = p.command_handler("Owner", "ping", "tell")
    assert captured["cmd"] == ["ping", "-n", "4", "chat.d1.funcom.com"]
    assert "Reply from chat.d1.funcom.com" in result
    assert "Ping results ::" in result


def test_ping_server_linux_uses_dash_c_dash_w(bot, monkeypatch):
    p = make_ping(bot)
    bot.core("settings").save("Ping", "Server", "Linux")
    captured = {}

    def fake_execute(cmd):
        captured["cmd"] = cmd
        return ["64 bytes from chat.d1.funcom.com"]

    monkeypatch.setattr(p, "_execute", fake_execute)
    p.command_handler("Owner", "ping", "tell")
    assert captured["cmd"] == ["ping", "-c4", "-w4", "chat.d1.funcom.com"]


def test_ping_server_no_results(bot, monkeypatch):
    p = make_ping(bot)
    monkeypatch.setattr(p, "_execute", lambda cmd: [])
    result = p.ping_server()
    assert "Could not find results" in result


def test_ping_server_sanitizes_host(bot, monkeypatch):
    p = make_ping(bot, server="evil;host&&`rm -rf /`")
    captured = {}
    monkeypatch.setattr(p, "_execute", lambda cmd: captured.setdefault("cmd", cmd) or [])
    p.ping_server()
    assert captured["cmd"][-1] == "evilhostrm-rf"


# -- tracert_server -----------------------------------------------------------------

def test_tracert_windows_uses_tracert_binary(bot, monkeypatch):
    p = make_ping(bot)
    captured = {}
    monkeypatch.setattr(p, "_execute", lambda cmd: captured.setdefault("cmd", cmd) or ["1  10 ms  host"])
    result = p.command_handler("Owner", "tracert", "tell")
    assert captured["cmd"] == ["tracert", "chat.d1.funcom.com"]
    assert "Trace route results ::" in result


def test_tracert_linux_uses_traceroute_binary(bot, monkeypatch):
    p = make_ping(bot)
    bot.core("settings").save("Ping", "Server", "Linux")
    captured = {}
    monkeypatch.setattr(p, "_execute", lambda cmd: captured.setdefault("cmd", cmd) or [])
    p.tracert_server()
    assert captured["cmd"] == ["traceroute", "chat.d1.funcom.com"]


# -- dispatch -----------------------------------------------------------------------

def test_command_handler_unrecognized_returns_none(bot):
    p = make_ping(bot)
    assert p.command_handler("Owner", "something else", "tell") is None
