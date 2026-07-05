from bebot.commodities.base import BotError
from bebot.main_modules.player import Player
from bebot.main_modules.preferences import Preferences
from bebot.main_modules.tools import Tools
from fakes import FakeAccessControl, FakePlayer


def make_prefs(bot, access_control=None) -> Preferences:
    Tools(bot)
    bot.register_module(access_control or FakeAccessControl(allow=True), "access_control")
    bot.register_module(FakePlayer(ids={"Someplayer": 12345}, names={12345: "Someplayer"}), "player")
    return Preferences(bot)


def make_prefs_with_real_player(bot) -> tuple[Preferences, Player]:
    """Uses the real Player module so unknown-name lookups actually raise BotError."""
    Tools(bot)
    bot.register_module(FakeAccessControl(allow=True), "access_control")
    player = Player(bot)
    return Preferences(bot), player


# -- construction --------------------------------------------------------

def test_creates_tables_on_construction(bot):
    make_prefs(bot)
    create_queries = [q for q in bot.db.queries if "CREATE TABLE" in q]
    assert len(create_queries) == 2
    assert any("preferences_def" in q for q in create_queries)
    assert any("preferences" in q and "preferences_def" not in q for q in create_queries)


def test_registers_as_prefs_module(bot):
    module = make_prefs(bot)
    assert bot.core("prefs") is module


# -- connect() / caching of defaults --------------------------------------

def test_connect_populates_default_cache(bot, monkeypatch):
    module = make_prefs(bot)
    monkeypatch.setattr(
        bot.db, "select",
        lambda sql, *a, **kw: [{"module": "Colors", "name": "Theme", "value": "Dark"}],
    )
    module.connect()
    assert module.cache["def"] == {"colors": {"theme": "Dark"}}


def test_connect_with_no_definitions_yields_empty_cache(bot, monkeypatch):
    module = make_prefs(bot)
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [])
    module.connect()
    assert module.cache["def"] == {}


# -- buddy() login/logout caching -----------------------------------------

def test_buddy_login_caches_customized_prefs(bot, monkeypatch):
    module = make_prefs(bot)
    monkeypatch.setattr(
        bot.db, "select",
        lambda sql, *a, **kw: [{"value": "Light", "module": "Colors", "name": "Theme"}],
    )
    module.buddy("Someplayer", 1)
    assert module.cache[12345] == {"colors": {"theme": "Light"}}


def test_buddy_logout_clears_cache(bot, monkeypatch):
    module = make_prefs(bot)
    module.cache[12345] = {"colors": {"theme": "Light"}}
    module.buddy("Someplayer", 0)
    assert 12345 not in module.cache


def test_buddy_logout_for_uncached_user_is_a_noop(bot, monkeypatch):
    module = make_prefs(bot)
    # Should not raise even though 12345 was never cached.
    module.buddy("Someplayer", 0)
    assert 12345 not in module.cache


# -- exists() --------------------------------------------------------------

def test_exists_true_for_known_definition(bot):
    module = make_prefs(bot)
    module.cache["def"] = {"colors": {"theme": "Dark"}}
    assert module.exists("Colors", "Theme") is True
    assert module.exists("colors", "theme") is True


def test_exists_false_for_unknown_definition(bot):
    module = make_prefs(bot)
    module.cache["def"] = {"colors": {"theme": "Dark"}}
    assert module.exists("Colors", "Bogus") is False
    assert module.exists("Bogus", "Theme") is False


# -- get() -------------------------------------------------------------------

def test_get_specific_setting_returns_default_when_no_override(bot):
    module = make_prefs(bot)
    module.cache["def"] = {"colors": {"theme": "Dark"}}
    assert module.get("Someplayer", "colors", "theme") == "Dark"


def test_get_specific_setting_returns_user_override(bot):
    module = make_prefs(bot)
    module.cache["def"] = {"colors": {"theme": "Dark"}}
    module.cache[12345] = {"colors": {"theme": "Light"}}
    assert module.get("Someplayer", "colors", "theme") == "Light"


def test_get_specific_setting_accepts_numeric_uid_directly(bot):
    module = make_prefs(bot)
    module.cache["def"] = {"colors": {"theme": "Dark"}}
    module.cache[12345] = {"colors": {"theme": "Light"}}
    assert module.get(12345, "colors", "theme") == "Light"
    assert module.get("12345", "colors", "theme") == "Light"


def test_get_unknown_setting_returns_none(bot):
    module = make_prefs(bot)
    module.cache["def"] = {"colors": {"theme": "Dark"}}
    assert module.get("Someplayer", "colors", "bogus_setting") is None


def test_get_unset_player_returns_false(bot):
    module, _player = make_prefs_with_real_player(bot)
    assert module.get("NeverSeenBefore", "colors", "theme") is False


def test_get_all_prefs_for_known_user_merges_def_and_overrides(bot):
    module = make_prefs(bot)
    module.cache["def"] = {"colors": {"theme": "Dark"}, "shortcuts": {"enabled": "1"}}
    module.cache[12345] = {"colors": {"theme": "Light"}}
    result = module.get("Someplayer")
    # Shallow merge: "colors" entry comes entirely from the user's cache.
    assert result == {"colors": {"theme": "Light"}, "shortcuts": {"enabled": "1"}}


def test_get_all_prefs_for_unknown_user_lists_modules_from_db(bot, monkeypatch):
    module = make_prefs(bot)
    module.cache["def"] = {}
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [["Colors"], ["Shortcuts"]])
    result = module.get("Someplayer")
    assert result == {"colors": {}, "shortcuts": {}}


def test_get_module_prefs_for_known_user_merges_overrides(bot):
    module = make_prefs(bot)
    module.cache["def"] = {"colors": {"theme": "Dark", "font": "Arial"}}
    module.cache[12345] = {"colors": {"theme": "Light"}}
    result = module.get("Someplayer", "colors")
    assert result == {"theme": "Light", "font": "Arial"}


def test_get_module_prefs_for_unknown_user_reads_defaults_from_db(bot, monkeypatch):
    module = make_prefs(bot)
    module.cache["def"] = {}
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [["Theme", "Dark"], ["Font", "Arial"]])
    result = module.get("Someplayer", "Colors")
    assert result == {"theme": "Dark", "font": "Arial"}


# -- change() -----------------------------------------------------------------

def test_change_no_op_when_value_already_set(bot):
    module = make_prefs(bot)
    module.cache["def"] = {"colors": {"theme": "Dark"}}
    module.cache[12345] = {"colors": {"theme": "Light"}}
    result = module.change("Someplayer", "colors", "theme", "Light")
    assert "already set to 'Light'" in result
    assert module.cache[12345]["colors"]["theme"] == "Light"


def test_change_to_default_deletes_override(bot):
    module = make_prefs(bot)
    module.cache["def"] = {"colors": {"theme": "Dark"}}
    module.cache[12345] = {"colors": {"theme": "Light"}}
    result = module.change("Someplayer", "colors", "theme", "Dark")
    assert "reset to default value 'Dark'" in result
    assert "theme" not in module.cache[12345]["colors"]
    delete_queries = [q for q in bot.db.queries if q.startswith("DELETE FROM #___preferences")]
    assert len(delete_queries) == 1


def test_change_from_default_inserts_row(bot):
    module = make_prefs(bot)
    module.cache["def"] = {"colors": {"theme": "Dark"}}
    result = module.change("Someplayer", "colors", "theme", "Light")
    assert "Preference was created" in result
    assert module.cache[12345]["colors"]["theme"] == "Light"
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___preferences ")]
    assert len(insert_queries) == 1


def test_change_between_two_non_default_values_updates_row(bot):
    module = make_prefs(bot)
    module.cache["def"] = {"colors": {"theme": "Dark"}}
    module.cache[12345] = {"colors": {"theme": "Light"}}
    result = module.change("Someplayer", "colors", "theme", "Blue")
    assert "changed to 'Blue'" in result
    assert module.cache[12345]["colors"]["theme"] == "Blue"
    update_queries = [q for q in bot.db.queries if q.startswith("UPDATE #___preferences SET")]
    assert len(update_queries) == 1


# -- change_default() ----------------------------------------------------------

def test_change_default_updates_def_cache(bot):
    module = make_prefs(bot)
    module.cache["def"] = {"colors": {"theme": "Dark"}}
    result = module.change_default("Admin", "colors", "theme", "Light")
    assert module.cache["def"]["colors"]["theme"] == "Light"
    assert "has been set to 'Light'" in result


def test_change_default_purges_matching_user_overrides(bot):
    module = make_prefs(bot)
    module.cache["def"] = {"colors": {"theme": "Dark"}}
    module.cache[12345] = {"colors": {"theme": "Light"}}
    module.change_default("Admin", "colors", "theme", "Light")
    # The user's override now equals the new default, so it's dropped along
    # with the now-empty module dict and the now-empty user cache entry.
    assert 12345 not in module.cache


def test_change_default_keeps_user_overrides_that_differ(bot):
    module = make_prefs(bot)
    module.cache["def"] = {"colors": {"theme": "Dark"}}
    module.cache[12345] = {"colors": {"theme": "Blue"}}
    module.change_default("Admin", "colors", "theme", "Light")
    assert module.cache[12345]["colors"]["theme"] == "Blue"


# -- create() ------------------------------------------------------------------

def test_create_inserts_new_definition(bot, monkeypatch):
    module = make_prefs(bot)
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [])
    module.create("colors", "Theme", "Which theme to use", "dark", "Dark;Light")
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___preferences_def")]
    assert len(insert_queries) == 1
    assert "'Colors'" in insert_queries[0]
    assert "'Dark'" in insert_queries[0]


def test_create_updates_existing_definition_when_changed(bot, monkeypatch):
    module = make_prefs(bot)
    # ID, description, possible_values, default_value
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [[1, "old desc", "Dark;Light", "Dark"]])
    module.create("colors", "Theme", "new desc", "dark", "Dark;Light")
    update_queries = [q for q in bot.db.queries if q.startswith("UPDATE #___preferences_def SET description")]
    assert len(update_queries) == 1


def test_create_no_op_when_definition_unchanged(bot, monkeypatch):
    module = make_prefs(bot)
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [[1, "same desc", "Dark;Light", "Dark"]])
    module.create("colors", "Theme", "same desc", "dark", "Dark;Light")
    assert not any(q.startswith("UPDATE #___preferences_def") for q in bot.db.queries)
    assert not any(q.startswith("INSERT INTO #___preferences_def") for q in bot.db.queries)


# -- show_modules() / show_prefs() --------------------------------------------

def test_show_modules_lists_module_links(bot):
    module = make_prefs(bot)
    module.cache["def"] = {}
    module.cache[12345] = {"colors": {"theme": "Light"}, "shortcuts": {"enabled": "1"}}
    result = module.show_modules("Someplayer")
    assert "preferences show colors" in result
    assert "preferences show shortcuts" in result


def test_show_prefs_marks_current_value_and_default(bot, monkeypatch):
    module = make_prefs(bot)
    module.cache["def"] = {"colors": {"theme": "dark"}}
    module.cache[12345] = {"colors": {"theme": "light"}}
    monkeypatch.setattr(
        bot.db, "select",
        lambda sql, *a, **kw: [
            {"name": "Theme", "description": "Which theme", "default_value": "dark", "possible_values": "dark;light"}
        ],
    )
    result = module.show_prefs("Someplayer", "colors")
    assert "Preferences for colors" in result
    # The current override value ("light") is rendered as plain text, not a link.
    assert ">light<" not in result
    assert "preferences set colors Theme dark" in result


def test_show_prefs_hides_default_buttons_when_access_denied(bot, monkeypatch):
    module = make_prefs(bot, access_control=FakeAccessControl(allow=False))
    module.cache["def"] = {"colors": {"theme": "dark"}}
    # Pre-populate the user's cache entry so get(name, module) takes the
    # cache-merge path instead of calling bot.db.select() a second time
    # (which is monkeypatched below to answer the show_prefs() query only).
    module.cache[12345] = {"colors": {"theme": "dark"}}
    monkeypatch.setattr(
        bot.db, "select",
        lambda sql, *a, **kw: [
            {"name": "Theme", "description": "Which theme", "default_value": "dark", "possible_values": "dark;light"}
        ],
    )
    result = module.show_prefs("Someplayer", "colors")
    assert "preferences default colors" not in result
