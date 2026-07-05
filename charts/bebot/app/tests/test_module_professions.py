from bebot.commodities.base import BotError
from bebot.main_modules.professions import Professions


def make_professions(bot) -> Professions:
    return Professions(bot)


# -- construction --------------------------------------------------------

def test_registers_as_professions_module(bot):
    prof = make_professions(bot)
    assert bot.core("professions") is prof


def test_ao_cache_and_units_populated_by_default(bot):
    prof = make_professions(bot)
    assert prof.cache["Adventurer"] == "adv"
    assert prof.cache["Meta-Physicist"] == "mp"
    assert "artillery" in prof.units
    assert "Adventurer" in prof.units["artillery"]


def test_aoc_game_uses_aoc_cache_and_has_no_units(bot):
    bot.game = "AoC"
    prof = make_professions(bot)
    assert prof.cache["Barbarian"] == "barb"
    assert "Adventurer" not in prof.cache
    assert prof.units == {}


# -- full_name ------------------------------------------------------------

def test_full_name_from_shortcut(bot):
    prof = make_professions(bot)
    assert prof.full_name("adv") == "Adventurer"


def test_full_name_from_shortcut_case_insensitive(bot):
    prof = make_professions(bot)
    assert prof.full_name("ADV") == "Adventurer"


def test_full_name_from_full_name_normalizes_case(bot):
    prof = make_professions(bot)
    assert prof.full_name("adventurer") == "Adventurer"
    assert prof.full_name("META-PHYSICIST") == "Meta-Physicist"


def test_full_name_unknown_returns_bot_error(bot):
    prof = make_professions(bot)
    result = prof.full_name("nonsense")
    assert isinstance(result, BotError)
    assert "nonsense" in result.description
    assert result.is_error is True


# -- shortcut (faithfully-ported casing bug, see module docstring) -------

def test_shortcut_single_word_full_name_matches(bot):
    prof = make_professions(bot)
    assert prof.shortcut("adventurer") == "adv"


def test_shortcut_multi_word_full_name_fails_due_to_ported_bug(bot):
    prof = make_professions(bot)
    # "Martial Artist" -> lower/capitalize/dash-replace -> "Martial artist"
    # which matches neither a cache key nor a cache value -- this mirrors
    # the PHP original's behavior exactly (see docstring).
    result = prof.shortcut("Martial Artist")
    assert isinstance(result, BotError)


def test_shortcut_of_a_shortcut_fails_due_to_ported_bug(bot):
    prof = make_professions(bot)
    # "adv" -> "Adv" which matches neither a full name key nor a shortcut
    # value ("adv") because of the case mismatch -- ported bug.
    result = prof.shortcut("adv")
    assert isinstance(result, BotError)


def test_shortcut_unknown_returns_bot_error(bot):
    prof = make_professions(bot)
    result = prof.shortcut("nonsense")
    assert isinstance(result, BotError)


# -- get_professions / get_profession_array -------------------------------

def test_get_professions_joins_full_names(bot):
    prof = make_professions(bot)
    result = prof.get_professions()
    assert "Adventurer" in result
    assert result.split(", ")[0] == "Adventurer"


def test_get_professions_custom_separator(bot):
    prof = make_professions(bot)
    result = prof.get_professions("|")
    assert "|" in result
    assert ", " not in result


def test_get_profession_array_returns_all_full_names(bot):
    prof = make_professions(bot)
    result = prof.get_profession_array()
    assert result == list(AO_ORDER)


AO_ORDER = [
    "Adventurer",
    "Agent",
    "Bureaucrat",
    "Doctor",
    "Enforcer",
    "Engineer",
    "Fixer",
    "Keeper",
    "Martial Artist",
    "Meta-Physicist",
    "Nano-Technician",
    "Shade",
    "Soldier",
    "Trader",
]


# -- get_shortcuts / get_shortcut_array ------------------------------------

def test_get_shortcuts_joins_shortcuts(bot):
    prof = make_professions(bot)
    result = prof.get_shortcuts()
    assert "adv" in result.split(", ")


def test_get_shortcut_array_returns_all_shortcuts(bot):
    prof = make_professions(bot)
    result = prof.get_shortcut_array()
    assert result[0] == "adv"
    assert "mp" in result


# -- get_unit_array ---------------------------------------------------------

def test_get_unit_array_returns_all_units(bot):
    prof = make_professions(bot)
    assert set(prof.get_unit_array()) == {
        "artillery",
        "control",
        "extermination",
        "infantry",
        "support",
    }


def test_get_unit_array_empty_for_aoc(bot):
    bot.game = "AoC"
    prof = make_professions(bot)
    assert prof.get_unit_array() == []


# -- get_units / get_unit_list ----------------------------------------------

def test_get_units_by_full_name(bot):
    prof = make_professions(bot)
    units = prof.get_units("Trader")
    assert set(units) == {"artillery", "control", "support"}


def test_get_units_by_shortcut(bot):
    prof = make_professions(bot)
    units = prof.get_units("trader")
    assert set(units) == {"artillery", "control", "support"}


def test_get_units_profession_in_no_units(bot):
    prof = make_professions(bot)
    assert prof.get_units("Shade") == []


def test_get_units_unknown_profession_returns_bot_error(bot):
    prof = make_professions(bot)
    result = prof.get_units("nonsense")
    assert isinstance(result, BotError)


def test_get_unit_list_joins_units(bot):
    prof = make_professions(bot)
    result = prof.get_unit_list("trader", " ")
    parts = result.split(" ")
    assert set(parts) == {"artillery", "control", "support"}


def test_get_unit_list_unknown_profession_returns_bot_error(bot):
    prof = make_professions(bot)
    result = prof.get_unit_list("nonsense")
    assert isinstance(result, BotError)
