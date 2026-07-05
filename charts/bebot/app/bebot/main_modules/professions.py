"""Ported (reduced) from Core/Professions.php.

Utility lookups for profession full names, shortcuts, and (for the
classic Anarchy Online ruleset) the "unit" groupings used by
Modules/Ao/Symbiants.php etc.

Cuts / notes:
  * The PHP constructor issued `DROP TABLE IF EXISTS #___professions`,
    a leftover from a long-gone DB-backed incarnation of this module --
    it never creates or uses that table itself. Kept here (via
    `bot.db.query(...)`) purely for faithfulness; it's a no-op against
    the fake/real DB either way.
  * The AoC (Age of Conan) profession table is ported faithfully via
    `bot.game`, but this codebase's `Bot` currently hardcodes
    `self.game = "Ao"` (see bebot/bot.py), so the AoC branch is
    presently unreachable dead code here just as it is upstream absent
    an AoC-flavored bot.
  * `shortcut()` is ported byte-for-byte including a pre-existing bug
    in the original: it normalizes the input with
    `str_replace('-', ' ', ucfirst(strtolower($profession)))` *before*
    both the full-name lookup AND the "is it already a shortcut"
    in_array check, so passing an actual shortcut (e.g. "adv") almost
    never round-trips (it becomes "Adv", which matches neither a
    cache key nor a cache value). This method is never actually called
    anywhere else in the PHP codebase, so the bug is harmless upstream;
    it's reproduced here rather than silently "fixed" since fixing
    behavior isn't in scope for a straight port.
  * `get_unit_list()` deviates slightly from the PHP original: PHP's
    `implode($separator, $this->get_units($profession))` would choke
    (implode() expects an array) if `get_units()` returns a BotError
    for an unrecognized profession. Here we check for that case first
    and propagate the BotError instead of trying to join it.
"""
from __future__ import annotations

from ..commodities.base import BasePassiveModule, BotError

AOC_PROFESSIONS: dict[str, str] = {
    "Barbarian": "barb",
    "Conqueror": "conq",
    "Guardian": "guard",
    "Priest of Mitra": "pom",
    "Tempest of Set": "tos",
    "Bear Shaman": "bs",
    "Dark Templar": "dt",
    "Assassin": "ass",
    "Ranger": "rang",
    "Necromancer": "necro",
    "Herald of Xotli": "hox",
    "Demonologist": "demo",
}

AO_PROFESSIONS: dict[str, str] = {
    "Adventurer": "adv",
    "Agent": "agent",
    "Bureaucrat": "crat",
    "Doctor": "doc",
    "Enforcer": "enf",
    "Engineer": "eng",
    "Fixer": "fixer",
    "Keeper": "keeper",
    "Martial Artist": "ma",
    "Meta-Physicist": "mp",
    "Nano-Technician": "nt",
    "Shade": "shade",
    "Soldier": "sol",
    "Trader": "trader",
}

AO_UNITS: dict[str, list[str]] = {
    "artillery": ["Adventurer", "Agent", "Fixer", "Soldier", "Trader"],
    "control": ["Bureaucrat", "Engineer", "Meta-Physicist", "Trader"],
    "extermination": ["Bureaucrat", "Meta-Physicist", "Nano-Technician"],
    "infantry": ["Adventurer", "Enforcer", "Keeper", "Martial Artist"],
    "support": [
        "Adventurer",
        "Doctor",
        "Fixer",
        "Keeper",
        "Martial Artist",
        "Meta-Physicist",
        "Trader",
    ],
}


class Professions(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        bot.db.query("DROP TABLE IF EXISTS #___professions")
        self.register_module("professions")
        if str(getattr(bot, "game", "")).lower() == "aoc":
            self.cache: dict[str, str] = dict(AOC_PROFESSIONS)
            self.units: dict[str, list[str]] = {}
        else:
            self.cache = dict(AO_PROFESSIONS)
            self.units = {unit: list(profs) for unit, profs in AO_UNITS.items()}

    def full_name(self, shortcut: str):
        """Full name for `shortcut`, or the correctly-cased full name if it
        already is one. Returns a BotError if it's neither."""
        self.error.reset()
        lowered = shortcut.lower()
        for full, short in self.cache.items():
            if short == lowered:
                return full
        for full in self.cache:
            if full.lower() == lowered:
                return full
        self.error.set(f"##highlight##'{shortcut}'##end## is not a valid profession name or shortcut.")
        return self.error

    def shortcut(self, profession: str):
        """Shortcut for `profession`, or `profession` unchanged if it
        already is a shortcut. Returns a BotError if it's neither.

        See the module docstring for a pre-existing casing bug carried
        over faithfully from the PHP original.
        """
        self.error.reset()
        normalized = profession.lower().capitalize().replace("-", " ")
        if normalized in self.cache:
            return self.cache[normalized]
        if normalized in self.cache.values():
            return normalized
        self.error.set(f"'{profession}' is not a valid profession name or shortcut.")
        return self.error

    def get_professions(self, separator: str = ", ") -> str:
        return separator.join(self.cache.keys())

    def get_profession_array(self) -> list[str]:
        return list(self.cache.keys())

    def get_shortcuts(self, separator: str = ", ") -> str:
        return separator.join(self.cache.values())

    def get_shortcut_array(self) -> list[str]:
        return list(self.cache.values())

    def get_unit_array(self) -> list[str]:
        return list(self.units.keys())

    def get_units(self, profession: str):
        """All units `profession` (full name or shortcut) is a member of."""
        full = self.full_name(profession)
        if isinstance(full, BotError):
            return full
        return [unit for unit, professions in self.units.items() if full in professions]

    def get_unit_list(self, profession: str, separator: str = ", "):
        units = self.get_units(profession)
        if isinstance(units, BotError):
            return units
        return separator.join(units)
