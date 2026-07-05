"""Ported from Modules/Calc.php.

Simple/continuous chat calculator. The PHP original builds a snippet of
PHP source (`"$y=" . $calc . ";"`) and runs it through `eval()` to do the
actual arithmetic -- that's obviously not something to reproduce in
Python (arbitrary code execution from a chat message). Instead
`_safe_eval()` below parses the expression with `ast` and only allows
numeric literals, `+ - * / %`, parentheses and unary +/-, which covers
every operator the PHP's own `is_numeric()`-based pre-filter allowed
through in the first place (it stripped `. , + - * / \\ x X % ( ) <space>`
before checking numeric-ness, i.e. it only ever intended to allow digits
and those operator characters). Note `x`/`X` were stripped for that
numeric pre-check but never substituted for `*` before being handed to
PHP's `eval()` -- so a calc containing a literal `x`/`X` would already
fail there with a parse error in the original too; this port preserves
that (an `x`/`X` character makes `_safe_eval` raise, falling through to
the "Wrong syntax" message) rather than silently reinterpreting it as
multiplication.

Continuation feature: if a user's next `calc` starts with an operator
(`+ - * / %`) and they have a previous expression cached, the new chunk
is appended to (or, for `* / %`, wrapped-and-appended to) the previous
expression string, so `calc 5`, then `calc +3` behaves like a running
calculator. This mirrors the PHP's `$this->calcu[$name]` bookkeeping.
"""
from __future__ import annotations

import ast
import operator

from ..commodities.base import BaseActiveModule

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}
_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class CalcError(Exception):
    pass


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        try:
            return _ALLOWED_BINOPS[type(node.op)](left, right)
        except ZeroDivisionError as exc:
            raise CalcError("division by zero") from exc
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_eval_node(node.operand))
    raise CalcError(f"disallowed expression: {ast.dump(node)}")


def _safe_eval(expr: str):
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise CalcError("syntax error") from exc
    return _eval_node(tree)


def _format_number(value) -> str:
    formatted = f"{value:,.2f}".replace(",", " ")
    if formatted.endswith(".00"):
        formatted = formatted[: -len(".00")]
    return formatted


_STRIP_CHARS = ".,+-*/\\xX%() "


class Calc(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("calc")
        self.register_command("all", "calc", "GUEST")
        self.bot.core("settings").create(
            "Calc", "ShowEquation", True, "Should the equation be shown when doing calculations?"
        )
        self.help["description"] = "Performs simple calculations"
        self.help["command"] = {}
        self.help["command"]["calc <expression>"] = "Shows the result of the matematical <expression>"
        self.calcu: dict[str, str] = {}

    def command_handler(self, name, msg, origin):
        if msg[:5].lower() == "calc " and msg[5:].strip():
            return self.do_calcs(name, msg[5:])
        if msg.strip().lower() == "calc":
            return self.show_calc(name)
        self.bot.send_help(name)
        return False

    def do_calcs(self, name, calc: str):
        test = calc
        for ch in _STRIP_CHARS:
            test = test.replace(ch, "")
        if not test or not test.isdigit():
            return "Wrong syntax, please /tell <botname> <pre>help <pre>calc"

        leading_op = calc[:1] if calc[:1] in "+-*/%" else None
        if leading_op and name in self.calcu:
            try:
                previous_value = _safe_eval(self.calcu[name])
            except CalcError:
                return "Wrong syntax, please /tell <botname> <pre>help <pre>calc"
            expr_display = _format_number(previous_value).replace(" ", "") + calc
            if leading_op in ("+", "-"):
                full_expr = self.calcu[name] + calc
            else:
                full_expr = f"({self.calcu[name]}){calc}"
            self.calcu[name] = full_expr
        else:
            full_expr = calc
            expr_display = calc
            self.calcu[name] = calc

        try:
            result = _safe_eval(full_expr)
        except CalcError:
            return "Wrong syntax, please /tell <botname> <pre>help <pre>calc"

        if self.bot.core("settings").get("Calc", "ShowEquation"):
            return f"{expr_display} = {_format_number(result)}"
        return result

    def show_calc(self, name):
        if name in self.calcu:
            try:
                result = _safe_eval(self.calcu[name])
            except CalcError:
                return "Wrong syntax, please /tell <botname> <pre>help <pre>calc"
            return f"{self.calcu[name]} = {result}"
        return "You've not made any calculations since my last restart."
