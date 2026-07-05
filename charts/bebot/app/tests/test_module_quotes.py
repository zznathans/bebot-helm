"""Tests for main_modules/quotes.py (ported from Modules/Quotes.php)."""
from __future__ import annotations

import re

from bebot.main_modules.command_alias import CommandAlias
from bebot.main_modules.quotes import Quotes
from bebot.main_modules.tools import Tools
from fakes import FakeAccessControl


class _FakeAccessControlWithCreate(FakeAccessControl):
    def create(self, channel, command, access):
        pass


class FakeQuotesDb:
    """In-memory stand-in for #___quotes, answering exactly the queries
    quotes.py issues."""

    def __init__(self, rows=None):
        # rows: list of [id, quote, contributor]
        self.rows = rows or []
        self._next_id = (max((r[0] for r in self.rows), default=0)) + 1
        self.queries: list[str] = []

    def query(self, sql: str) -> bool:
        self.queries.append(sql)
        m = re.match(r"INSERT INTO #___quotes \(quote, contributor\) VALUES \('(.*)', '(.*)'\)", sql)
        if m:
            self.rows.append([self._next_id, m.group(1), m.group(2)])
            self._next_id += 1
            return True
        m = re.match(r"DELETE FROM #___quotes WHERE id=(\d+)", sql)
        if m:
            qid = int(m.group(1))
            self.rows = [r for r in self.rows if r[0] != qid]
            return True
        return True

    def select(self, sql: str, as_dict: bool = False):
        self.queries.append(sql)
        if "ORDER BY id DESC" in sql and "SELECT id" in sql:
            if not self.rows:
                return []
            return [[max(r[0] for r in self.rows)]]
        m = re.match(r"SELECT \* FROM #___quotes WHERE id=(\d+)", sql)
        if m:
            qid = int(m.group(1))
            return [list(r) for r in self.rows if r[0] == qid]
        m = re.match(r"SELECT \* FROM #___quotes WHERE quote LIKE '%(.*)%'", sql)
        if m:
            text = m.group(1)
            return [list(r) for r in self.rows if text in r[1]]
        m = re.match(r"SELECT \* FROM #___quotes WHERE contributor = '(.*)'", sql)
        if m:
            name = m.group(1)
            return [list(r) for r in self.rows if r[2] == name]
        if sql == "SELECT * FROM #___quotes":
            return [list(r) for r in self.rows]
        return []

    def real_escape_string(self, value) -> str:
        return str(value).replace("'", "\\'")

    def define_tablename(self, table, use_prefix=False):
        return table


def make_quotes(bot, rows=None) -> Quotes:
    bot.register_module(_FakeAccessControlWithCreate(), "access_control")
    Tools(bot)
    CommandAlias(bot)
    bot.db = FakeQuotesDb(rows)
    return Quotes(bot)


# -- construction -----------------------------------------------------------------

def test_registers_as_quotes_module(bot):
    q = make_quotes(bot)
    assert bot.core("quotes") is q


def test_registers_quotes_command(bot):
    q = make_quotes(bot)
    for channel in ("tell", "gc", "pgmsg"):
        assert bot.commands[channel]["quotes"] is q


def test_registers_quote_alias(bot):
    make_quotes(bot)
    assert bot.core("command_alias").exists("quote")


def test_help_describes_commands(bot):
    q = make_quotes(bot)
    assert "quotes" in q.help["command"]
    assert "quotes add text" in q.help["command"]


# -- add/get/delete -----------------------------------------------------------------

def test_add_quote_returns_new_id(bot):
    q = make_quotes(bot)
    result = q.add_quote("Hello world", "Someguy")
    assert result == "Thank you, your quote has been added as id #1"


def test_send_quote_by_id(bot):
    q = make_quotes(bot, rows=[[1, "Hello world", "Someguy"]])
    result = q.send_quote(1)
    assert result == "#1 - Hello world [By: Someguy]"


def test_send_quote_missing_id(bot):
    q = make_quotes(bot, rows=[[1, "Hello world", "Someguy"]])
    result = q.send_quote(5)
    assert "not found" in result
    assert "Highest quote ID is 1" in result


def test_send_quote_random_pick(bot, monkeypatch):
    q = make_quotes(bot, rows=[[1, "Only quote", "Someguy"]])
    monkeypatch.setattr(bot.core("tools"), "my_rand", lambda a, b: 0)
    result = q.send_quote(-1)
    assert result == "#1 - Only quote [By: Someguy]"


def test_send_quote_no_quotes_exist(bot):
    q = make_quotes(bot)
    result = q.send_quote(-1)
    assert result == "No quotes exist. Add some!"


def test_del_quote_removes_row(bot):
    q = make_quotes(bot, rows=[[1, "Hello world", "Someguy"]])
    result = q.del_quote(1)
    assert result == "Quote removed."
    assert q.send_quote(1) == "Quote with id of 1 not found. (Highest quote ID is 0.)"


def test_del_quote_not_found(bot):
    q = make_quotes(bot, rows=[[1, "Hello world", "Someguy"]])
    result = q.del_quote(99)
    assert "not found" in result


# -- search/by --------------------------------------------------------------------

def test_search_quote_finds_matches(bot):
    q = make_quotes(bot, rows=[[1, "Hello world", "Someguy"], [2, "Goodbye", "Otherguy"]])
    result = q.search_quote("Hello")
    assert result.startswith("1 quote(s) with keyword")


def test_search_quote_no_matches(bot):
    q = make_quotes(bot, rows=[[1, "Hello world", "Someguy"]])
    result = q.search_quote("Nope")
    assert result == "No quotes found with such keyword!"


def test_by_quote_capitalizes_name(bot):
    q = make_quotes(bot, rows=[[1, "Hello world", "Someguy"]])
    result = q.by_quote("someguy")
    assert result.startswith("1 quote(s) by username")


def test_by_quote_no_matches(bot):
    q = make_quotes(bot, rows=[[1, "Hello world", "Someguy"]])
    result = q.by_quote("nobody")
    assert result == "No quotes found by such username!"


# -- command_handler dispatch ------------------------------------------------------

def test_command_handler_random_quote_sends_output(bot, monkeypatch):
    q = make_quotes(bot, rows=[[1, "Hello world", "Someguy"]])
    monkeypatch.setattr(bot.core("tools"), "my_rand", lambda a, b: 0)
    sent = []
    monkeypatch.setattr(bot, "send_output", lambda name, msg, origin: sent.append((name, msg, origin)))
    result = q.command_handler("Asker", "quotes", "tell")
    assert result is None
    assert sent == [("Asker", "#1 - Hello world [By: Someguy]", "tell")]


def test_command_handler_by_id(bot, monkeypatch):
    q = make_quotes(bot, rows=[[1, "Hello world", "Someguy"]])
    sent = []
    monkeypatch.setattr(bot, "send_output", lambda name, msg, origin: sent.append((name, msg, origin)))
    q.command_handler("Asker", "quotes 1", "tell")
    assert sent == [("Asker", "#1 - Hello world [By: Someguy]", "tell")]


def test_command_handler_add(bot, monkeypatch):
    q = make_quotes(bot)
    sent = []
    monkeypatch.setattr(bot, "send_output", lambda name, msg, origin: sent.append((name, msg, origin)))
    q.command_handler("Someguy", "quotes add A wise saying", "tell")
    assert sent == [("Someguy", "Thank you, your quote has been added as id #1", "tell")]


def test_command_handler_delete(bot, monkeypatch):
    q = make_quotes(bot, rows=[[1, "Hello world", "Someguy"]])
    sent = []
    monkeypatch.setattr(bot, "send_output", lambda name, msg, origin: sent.append((name, msg, origin)))
    q.command_handler("Someguy", "quotes del 1", "tell")
    assert sent == [("Someguy", "Quote removed.", "tell")]


def test_command_handler_gc_calls_send_irc(bot, monkeypatch):
    q = make_quotes(bot, rows=[[1, "Hello world", "Someguy"]])
    irc_calls = []
    monkeypatch.setattr(bot, "send_output", lambda *a, **k: None)
    monkeypatch.setattr(bot, "send_irc", lambda prefix, name, msg: irc_calls.append(msg))
    q.command_handler("Someguy", "quotes 1", "gc")
    assert irc_calls == ["#1 - Hello world [By: Someguy]"]
