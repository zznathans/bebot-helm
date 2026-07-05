"""Tests for main_modules/calc.py (ported from Modules/Calc.php)."""
from __future__ import annotations

from bebot.main_modules.calc import Calc
from bebot.main_modules.settings import Settings


def make_calc(bot) -> Calc:
    Settings(bot)
    return Calc(bot)


# -- construction / registration ------------------------------------------------

def test_registers_as_calc_module(bot):
    module = make_calc(bot)
    assert bot.core("calc") is module


def test_registers_calc_command_on_all_channels(bot):
    module = make_calc(bot)
    for channel in ("tell", "gc", "pgmsg"):
        assert bot.commands[channel]["calc"] is module


def test_help_describes_command(bot):
    module = make_calc(bot)
    assert "calc <expression>" in module.help["command"]


# -- do_calcs / command_handler ------------------------------------------------

def test_simple_addition_shows_equation(bot):
    module = make_calc(bot)
    assert module.command_handler("Bob", "calc 2+2", "tell") == "2+2 = 4"


def test_simple_multiplication(bot):
    module = make_calc(bot)
    assert module.command_handler("Bob", "calc 6*7", "tell") == "6*7 = 42"


def test_division_formats_decimal(bot):
    module = make_calc(bot)
    assert module.command_handler("Bob", "calc 5/2", "tell") == "5/2 = 2.50"


def test_invalid_expression_returns_wrong_syntax(bot):
    module = make_calc(bot)
    result = module.command_handler("Bob", "calc hello", "tell")
    assert result == "Wrong syntax, please /tell <botname> <pre>help <pre>calc"


def test_show_equation_false_returns_raw_number(bot):
    module = make_calc(bot)
    module.bot.core("settings").save("Calc", "ShowEquation", False)
    result = module.command_handler("Bob", "calc 2+2", "tell")
    assert result == 4


def test_continuation_addition_uses_previous_result(bot):
    module = make_calc(bot)
    module.command_handler("Bob", "calc 5", "tell")
    result = module.command_handler("Bob", "calc +3", "tell")
    assert result == "5+3 = 8"


def test_continuation_multiplication_wraps_previous_expr(bot):
    module = make_calc(bot)
    module.command_handler("Bob", "calc 5", "tell")
    result = module.command_handler("Bob", "calc *3", "tell")
    assert result == "5*3 = 15"


def test_continuation_is_per_user(bot):
    module = make_calc(bot)
    module.command_handler("Bob", "calc 5", "tell")
    result = module.command_handler("Alice", "calc +3", "tell")
    # Alice has no prior calc, so "+3" alone is evaluated as-is.
    assert result == "+3 = 3"


def test_show_calc_alone_repeats_last_calculation(bot):
    module = make_calc(bot)
    module.command_handler("Bob", "calc 2+2", "tell")
    result = module.command_handler("Bob", "calc", "tell")
    assert result == "2+2 = 4"


def test_show_calc_with_no_history(bot):
    module = make_calc(bot)
    result = module.command_handler("Bob", "calc", "tell")
    assert result == "You've not made any calculations since my last restart."


def test_unrecognized_message_sends_help_and_returns_false(bot):
    module = make_calc(bot)
    result = module.command_handler("Bob", "something else", "tell")
    assert result is False
