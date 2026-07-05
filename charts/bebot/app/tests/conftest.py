"""Shared fixtures for the bot core test suite.

Bot.__init__ constructs a real AOChat (no socket opened until .connect())
and a real MySQL, which *does* open a connection and run CREATE TABLE
statements from its constructor. `bebot.bot.MySQL` is therefore patched
to a lightweight fake for every test so building a Bot never touches a
real database. Its `core(name)` dependencies (settings, security,
access_control, ...) are real main_modules that also touch the database
on construction, so tests inject lightweight fakes via
`bot.register_module(...)` instead of instantiating those directly.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from bebot.bot import Bot
from bebot.conf import BotConfig


class _FakeMySQL:
    """Stands in for bebot.mysql.MySQL so Bot() never opens a real connection."""

    def __init__(self, bot, dbase, user, password, server,
                 table_prefix=None, master_tablename=None, no_underscore=False):
        self.bot = bot
        self.botname = bot.botname
        self.queries: list[str] = []

    def query(self, sql: str) -> bool:
        self.queries.append(sql)
        return True

    def select(self, sql: str, as_dict: bool = False):
        return []

    def real_escape_string(self, value) -> str:
        return str(value).replace("'", "\\'")

    def define_tablename(self, table: str, use_prefix) -> str:
        return table


@pytest.fixture(autouse=True)
def _fake_mysql(monkeypatch):
    monkeypatch.setattr("bebot.bot.MySQL", _FakeMySQL)


def make_config(tmp_path, **overrides) -> BotConfig:
    defaults = dict(
        ao_username="ao_user",
        ao_password="ao_pass",
        bot_name="testbot",
        dimension="5",
        guild="TestGuild",
        owner="owner",
        super_admin={"Admin": True},
        guildbot=True,
        guild_id=123,
        log="chat",
        log_path=str(tmp_path / "log"),
        log_timestamp="none",
        log_format="text",
        command_prefix="!",
        db_name="test",
        db_user="test",
        db_password="test",
        db_server="localhost",
    )
    defaults.update(overrides)
    return BotConfig(**defaults)


@pytest.fixture
def make_bot(tmp_path):
    def _make(**overrides) -> Bot:
        return Bot(make_config(tmp_path, **overrides))

    return _make


@pytest.fixture
def bot(make_bot) -> Bot:
    return make_bot()
