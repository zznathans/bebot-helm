from fakes import FakeSettings

from bebot.main_modules.statistics import Statistics


class _FakeSettingsWithCreate(FakeSettings):
    """FakeSettings doesn't implement create() -- Statistics.__init__ calls it
    to register the "Statistics" > "Enabled" setting."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.created: list[tuple] = []

    def create(self, module, setting, value, longdesc, defaultoptions="", hidden=False, disporder=1):
        self.created.append((module, setting, value, longdesc))


def make_statistics(bot, enabled=True) -> Statistics:
    fake_settings = _FakeSettingsWithCreate({("Statistics", "Enabled"): enabled})
    bot.register_module(fake_settings, "settings")
    return Statistics(bot)


# -- construction --------------------------------------------------------

def test_creates_table_on_construction(bot):
    make_statistics(bot)
    create_queries = [q for q in bot.db.queries if "CREATE TABLE" in q]
    assert len(create_queries) == 1
    assert "statistics" in create_queries[0]
    assert "count" in create_queries[0]


def test_registers_as_statistics_module(bot):
    module = make_statistics(bot)
    assert bot.core("statistics") is module


def test_registers_enabled_setting_default_false(bot):
    fake_settings = _FakeSettingsWithCreate()
    bot.register_module(fake_settings, "settings")
    Statistics(bot)
    assert ("Statistics", "Enabled", False, "Capture Statistics?") in fake_settings.created


# -- capture_statistic ----------------------------------------------------

def test_capture_statistic_does_nothing_when_disabled(bot):
    module = make_statistics(bot, enabled=False)
    module.capture_statistic("colors", "parse")
    assert not any("INSERT INTO #___statistics" in q for q in bot.db.queries)
    assert not any("UPDATE #___statistics" in q for q in bot.db.queries)


def test_capture_statistic_inserts_new_row_when_none_exists(bot, monkeypatch):
    module = make_statistics(bot, enabled=True)
    monkeypatch.setattr(bot.db, "select", lambda sql: [])
    module.capture_statistic("colors", "parse", "extra", 3)
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___statistics")]
    assert len(insert_queries) == 1
    assert "'colors'" in insert_queries[0]
    assert "'parse'" in insert_queries[0]
    assert "'extra'" in insert_queries[0]
    assert ",3)" in insert_queries[0]


def test_capture_statistic_default_count_is_one(bot, monkeypatch):
    module = make_statistics(bot, enabled=True)
    monkeypatch.setattr(bot.db, "select", lambda sql: [])
    module.capture_statistic("colors", "parse")
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___statistics")]
    assert ",1)" in insert_queries[0]


def test_capture_statistic_updates_existing_row(bot, monkeypatch):
    module = make_statistics(bot, enabled=True)
    monkeypatch.setattr(bot.db, "select", lambda sql: [[10]])
    module.capture_statistic("colors", "parse", "", 5)
    update_queries = [q for q in bot.db.queries if q.startswith("UPDATE #___statistics")]
    assert len(update_queries) == 1
    assert "count = '15'" in update_queries[0]
    assert "module = 'colors'" in update_queries[0]
    assert "action = 'parse'" in update_queries[0]
    assert not any(q.startswith("INSERT INTO #___statistics") for q in bot.db.queries)


def test_capture_statistic_filters_by_module_action_comment(bot, monkeypatch):
    captured = {}

    def fake_select(sql):
        captured["sql"] = sql
        return []

    module = make_statistics(bot, enabled=True)
    monkeypatch.setattr(bot.db, "select", fake_select)
    module.capture_statistic("mymodule", "myaction", "mycomment")
    assert "module = 'mymodule'" in captured["sql"]
    assert "action = 'myaction'" in captured["sql"]
    assert "comment = 'mycomment'" in captured["sql"]
