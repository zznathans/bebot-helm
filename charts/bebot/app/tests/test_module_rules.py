"""Tests for main_modules/rules.py (ported from Modules/Rules.php)."""
from __future__ import annotations

import os

from bebot.main_modules.rules import Rules
from bebot.main_modules.tools import Tools


def make_rules(bot) -> Rules:
    Tools(bot)
    return Rules(bot)


def test_registers_as_rules_module(bot, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    module = make_rules(bot)
    assert bot.core("rules") is module


def test_registers_rules_command_on_all_channels(bot, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    module = make_rules(bot)
    for channel in ("tell", "gc", "pgmsg"):
        assert bot.commands[channel]["rules"] is module


def test_no_rules_file_returns_header_only(bot, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    module = make_rules(bot)
    result = module.make_rules()
    assert "RULES" in result
    assert "<botname>'s Rules ::" in result


def test_uses_bot_specific_rules_file(bot, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs(tmp_path / "Text")
    (tmp_path / "Text" / f"{bot.botname}Rules.txt").write_text("Be nice.")
    module = make_rules(bot)
    result = module.make_rules()
    assert "Be nice." in result


def test_falls_back_to_default_rules_file(bot, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs(tmp_path / "Text")
    (tmp_path / "Text" / "Rules.txt").write_text("Generic rules.")
    module = make_rules(bot)
    result = module.make_rules()
    assert "Generic rules." in result


def test_bot_specific_file_takes_priority(bot, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs(tmp_path / "Text")
    (tmp_path / "Text" / f"{bot.botname}Rules.txt").write_text("Specific rules.")
    (tmp_path / "Text" / "Rules.txt").write_text("Generic rules.")
    module = make_rules(bot)
    result = module.make_rules()
    assert "Specific rules." in result
    assert "Generic rules." not in result


def test_command_handler_dispatches_to_make_rules(bot, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    module = make_rules(bot)
    result = module.command_handler("Bob", "rules", "tell")
    assert "RULES" in result
