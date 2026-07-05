from bebot.main_modules.command_alias import CommandAlias
from bebot.main_modules.rally import Rally
from bebot.main_modules.tools import Tools
from fakes import FakeAccessControl, FakeSecurity


class _FakeAccessControlWithCreate(FakeAccessControl):
    def create(self, channel, command, access):
        pass


class FakeRallyDb:
    """In-memory stand-in for bot.db, understanding the handful of SQL
    shapes rally.py issues against #___rally and #___land_control_zones."""

    def __init__(self, zone_rows=None):
        self.zone_rows = zone_rows or {}  # name/short/zoneid -> (zoneid, area)
        self.saved: dict[str, str] = {}
        self.queries: list[str] = []

    def query(self, sql: str) -> bool:
        self.queries.append(sql)
        if sql.startswith("INSERT INTO #___rally"):
            # VALUES ('name', 'rally')
            inside = sql.split("VALUES", 1)[1].strip().strip("()")
            name_part, rally_part = inside.split("', '")
            name = name_part.strip("'")
            rally = rally_part.strip("'")
            self.saved[name] = rally
        elif sql.startswith("DELETE FROM #___rally"):
            name = sql.split("name = '", 1)[1].rstrip("'")
            self.saved.pop(name, None)
        return True

    def select(self, sql: str, as_dict: bool = False):
        if "#___land_control_zones" in sql:
            return []  # LandControlZones.php isn't ported; always empty.
        if "SELECT name, rally FROM #___rally" in sql:
            return [(name, rally) for name, rally in sorted(self.saved.items())]
        if "SELECT name FROM #___rally WHERE name" in sql:
            name = sql.split("name = '", 1)[1].rstrip("'")
            return [(name,)] if name in self.saved else []
        if "SELECT rally FROM #___rally WHERE name" in sql:
            name = sql.split("name = '", 1)[1].rstrip("'")
            return [(self.saved[name],)] if name in self.saved else []
        return []

    def real_escape_string(self, value) -> str:
        return str(value).replace("'", "\\'")

    def define_tablename(self, table: str, use_prefix) -> str:
        return table


def make_module(bot, monkeypatch, access: bool = True, zone_rows=None) -> Rally:
    fake_db = FakeRallyDb(zone_rows=zone_rows)
    monkeypatch.setattr(bot, "db", fake_db)
    bot.register_module(_FakeAccessControlWithCreate(), "access_control")
    bot.register_module(FakeSecurity(access=access), "security")
    Tools(bot)
    CommandAlias(bot)
    return Rally(bot)


# -- construction / registration --------------------------------------------------

def test_registers_as_rally_module(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    assert bot.core("rally") is module


def test_registers_rally_command_on_all_channels(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    for channel in ("tell", "gc", "pgmsg"):
        assert bot.commands[channel]["rally"] is module


def test_help_describes_commands(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    assert "rally" in module.help["command"]
    assert "rally clear" in module.help["command"]


def test_creates_rally_table(bot, monkeypatch):
    make_module(bot, monkeypatch)
    assert any("CREATE TABLE IF NOT EXISTS rally" in q for q in bot.db.queries)


# -- unknown command --------------------------------------------------------------

def test_command_handler_rejects_non_rally_command(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.command_handler("Someuser", "other stuff", "tell")
    assert "Unknown Command" in result


# -- get_rally / set_rally --------------------------------------------------------

def test_get_rally_when_none_set(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.command_handler("Someuser", "rally", "tell")
    assert result == "No rally point has been set."


def test_set_rally_basic_coords(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.command_handler("Someuser", "rally Foo 100 200", "tell")
    assert result == "Rally point has been set."
    assert module.rallyinfo == ["Foo", "100", "200", "", False]


def test_set_rally_with_notes(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.command_handler("Someuser", "rally Foo 100 200 bring pets", "tell")
    assert result == "Rally point has been set."
    assert module.rallyinfo == ["Foo", "100", "200", "bring pets", False]


def test_set_rally_via_set_keyword(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.command_handler("Someuser", "rally set Foo 100 200", "tell")
    assert result == "Rally point has been set."
    assert module.rallyinfo == ["Foo", "100", "200", "", False]


def test_set_rally_ao_paste_format(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    msg = "rally - 123, 456, 789 (12 34 y 56 5000)"
    result = module.command_handler("Someuser", msg, "tell")
    assert result == "Rally point has been set."
    assert module.rallyinfo == ["5000", "123", "456", "", False]


def test_set_rally_invalid_shows_usage(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.command_handler("Someuser", "rally nonsense", "tell")
    assert "To set Rally" in result


def test_get_rally_after_set_shows_info(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    module.command_handler("Someuser", "rally Foo 100 200 note here", "tell")
    result = module.command_handler("Someuser", "rally", "tell")
    assert "Zone:" in result
    assert "Foo" in result
    assert "100, 200" in result
    assert "note here" in result
    # No zone number resolved (land_control_zones table not populated) -> no waypoint link.
    assert "Set Waypoint" not in result


# -- clear_rally --------------------------------------------------------------------

def test_clear_rally_requires_leader(bot, monkeypatch):
    module = make_module(bot, monkeypatch, access=False)
    module.rallyinfo = ["Foo", "1", "2", "", False]
    result = module.command_handler("Someuser", "rally clear", "tell")
    assert "LEADER" in result
    assert module.rallyinfo


def test_clear_rally_clears_when_leader(bot, monkeypatch):
    module = make_module(bot, monkeypatch, access=True)
    module.rallyinfo = ["Foo", "1", "2", "", False]
    result = module.command_handler("Someuser", "rally clear", "tell")
    assert result == "Rally has been cleared."
    assert module.rallyinfo is False


# -- save / list / load / del --------------------------------------------------------

def test_save_rally_requires_rallyinfo(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.command_handler("Someuser", "rally save myrally", "tell")
    assert result == "No rally point has been set."


def test_save_load_list_del_roundtrip(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    module.command_handler("Someuser", "rally Foo 100 200 bring pets", "tell")

    save_result = module.command_handler("Someuser", "rally save myrally", "tell")
    assert "saved as ##highlight##myrally##end##" in save_result

    dup_result = module.command_handler("Someuser", "rally save myrally", "tell")
    assert dup_result == "Name already exists"

    list_result = module.command_handler("Someuser", "rally list", "tell")
    assert "myrally" in list_result

    module.rallyinfo = False
    load_result = module.command_handler("Someuser", "rally load myrally", "tell")
    assert "loaded" in load_result
    assert module.rallyinfo[0] == "Foo"
    assert module.rallyinfo[1] == "100"
    assert module.rallyinfo[2] == "200"

    del_result = module.command_handler("Someuser", "rally del myrally", "tell")
    assert "deleted" in del_result
    assert module.command_handler("Someuser", "rally load myrally", "tell") == "Rally not found"


def test_list_rally_none_saved(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.command_handler("Someuser", "rally list", "tell")
    assert result == "No Saved Rally's Found"


def test_save_requires_leader(bot, monkeypatch):
    module = make_module(bot, monkeypatch, access=False)
    module.rallyinfo = ["Foo", "1", "2", "", False]
    result = module.command_handler("Someuser", "rally save myrally", "tell")
    assert "LEADER" in result
