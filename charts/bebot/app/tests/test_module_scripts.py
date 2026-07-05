"""Tests for main_modules/scripts.py (ported from Modules/Scripts.php)."""
from __future__ import annotations

from bebot.main_modules.scripts import Scripts
from bebot.main_modules.tools import Tools


def make_scripts(bot, tmp_path) -> Scripts:
    Tools(bot)
    module = Scripts(bot)
    module.path = tmp_path / "Extras" / "Scripts"
    return module


# -- construction / registration ------------------------------------------------

def test_registers_as_scripts_module(bot, tmp_path):
    module = make_scripts(bot, tmp_path)
    assert bot.core("scripts") is module


def test_registers_scripts_and_script_commands(bot, tmp_path):
    module = make_scripts(bot, tmp_path)
    for channel in ("tell", "gc", "pgmsg"):
        assert bot.commands[channel]["scripts"] is module
        assert bot.commands[channel]["script"] is module


# -- make_list ------------------------------------------------------------------

def test_make_list_missing_dir_reports_zero(bot, tmp_path):
    module = make_scripts(bot, tmp_path)
    result = module.make_list()
    assert result.startswith("0 script(s) found")


def test_make_list_ignores_gitkeep_and_dirs(bot, tmp_path):
    module = make_scripts(bot, tmp_path)
    module.path.mkdir(parents=True)
    (module.path / ".gitkeep").write_text("")
    (module.path / "subdir").mkdir()
    (module.path / "greet.txt").write_text("hello")
    result = module.make_list()
    assert result.startswith("1 script(s) found")
    assert "greet.txt" in result


def test_make_list_counts_multiple_files(bot, tmp_path):
    module = make_scripts(bot, tmp_path)
    module.path.mkdir(parents=True)
    (module.path / "a.txt").write_text("a")
    (module.path / "b.txt").write_text("b")
    result = module.make_list()
    assert result.startswith("2 script(s) found")


# -- make_script ------------------------------------------------------------------

def test_make_script_returns_content_with_header(bot, tmp_path):
    module = make_scripts(bot, tmp_path)
    module.path.mkdir(parents=True)
    (module.path / "greet.txt").write_text("hello world")
    result = module.make_script("greet.txt")
    assert "Script (greet.txt)::" in result
    assert "hello world" in result
    assert ":::: Script [greet.txt] ::::" in result


def test_make_script_missing_file(bot, tmp_path):
    module = make_scripts(bot, tmp_path)
    module.path.mkdir(parents=True)
    result = module.make_script("nope.txt")
    assert result == "Specified script not found ..."


def test_make_script_rejects_gitkeep(bot, tmp_path):
    module = make_scripts(bot, tmp_path)
    module.path.mkdir(parents=True)
    (module.path / ".gitkeep").write_text("")
    result = module.make_script(".gitkeep")
    assert result == "Specified script not found ..."


def test_make_script_rejects_path_traversal(bot, tmp_path):
    module = make_scripts(bot, tmp_path)
    module.path.mkdir(parents=True)
    secret = tmp_path / "secret.txt"
    secret.write_text("do not read me")
    result = module.make_script("../../secret.txt")
    assert result == "Specified script not found ..."


def test_make_script_rejects_path_separator(bot, tmp_path):
    module = make_scripts(bot, tmp_path)
    module.path.mkdir(parents=True)
    result = module.make_script("sub/greet.txt")
    assert result == "Specified script not found ..."


# -- command_handler dispatch -------------------------------------------------------

def test_command_handler_no_args_lists(bot, tmp_path):
    module = make_scripts(bot, tmp_path)
    result = module.command_handler("Bob", "scripts", "tell")
    assert result.startswith("0 script(s) found")


def test_command_handler_with_arg_shows_script(bot, tmp_path):
    module = make_scripts(bot, tmp_path)
    module.path.mkdir(parents=True)
    (module.path / "greet.txt").write_text("hi")
    result = module.command_handler("Bob", "script greet.txt", "tell")
    assert "Script (greet.txt)::" in result
