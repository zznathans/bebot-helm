"""Ported from Main/15_CommandAlias.php."""
from __future__ import annotations

from ..commodities.base import BasePassiveModule


class CommandAlias(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("command_alias")
        db = bot.db
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('command_alias', False)} "
            "(alias VARCHAR(100) NOT NULL, command VARCHAR(30) NOT NULL)"
        )
        self.alias: dict[str, str] = {}
        self.alias_sub: dict[str, dict[str, str]] = {}
        for alias, command in db.select("SELECT alias, command FROM #___command_alias") or []:
            self.register(command, alias)

    def register(self, command: str, alias: str) -> None:
        if alias.lower() == "comalias":
            return
        parts = alias.split(" ", 2)
        if len(parts) > 1 and parts[1]:
            self.alias_sub.setdefault(parts[0].lower(), {})[parts[1].lower()] = command
        else:
            self.alias[parts[0].lower()] = command

    def replace(self, msg: str) -> str:
        parts = msg.split(" ", 2)
        if len(parts) > 1 and parts[1] and parts[1].lower() in self.alias_sub.get(parts[0].lower(), {}):
            parts[0] = self.alias_sub[parts[0].lower()][parts[1].lower()]
            del parts[1]
        elif parts[0].lower() in self.alias:
            parts[0] = self.alias[parts[0].lower()]
        return " ".join(parts)

    def add(self, msg: str) -> str:
        first, _, rest = msg.partition(" ")
        first = first.lower()
        if first in self.alias:
            return f"##highlight##{first}##end## is already an alias of ##highlight##{self.alias[first]}##end##!"
        if first == "comalias":
            return f"##highlight##{first}##end## Cannot be set as an alias!"
        db = self.bot.db
        db.query(
            "INSERT INTO #___command_alias (alias, command) VALUES "
            f"('{db.real_escape_string(first)}', '{db.real_escape_string(rest)}')"
        )
        self.alias[first] = rest
        return f"##highlight##{first}##end## is now an alias of ##highlight##{rest}##end##!"

    def exists(self, alias: str) -> bool:
        return alias.lower() in self.alias

    def delete(self, alias: str) -> str:
        alias = alias.lower()
        db = self.bot.db
        row = db.select(f"SELECT alias FROM #___command_alias WHERE alias = '{db.real_escape_string(alias)}'")
        if row:
            db.query(f"DELETE FROM #___command_alias WHERE alias = '{db.real_escape_string(alias)}'")
            self.alias.pop(alias, None)
            return f"Alias ##highlight##{alias}##end## deleted."
        if alias in self.alias:
            return f"Alias ##highlight##{alias}##end## cannot be deleted."
        return f"Alias ##highlight##{alias}##end## not found."
