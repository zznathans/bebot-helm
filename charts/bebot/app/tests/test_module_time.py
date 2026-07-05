from datetime import datetime, timezone

from fakes import FakeAccessControl, FakeSettings

from bebot.main_modules.time import TimeCore


class _FakeAccessControlWithCreate(FakeAccessControl):
    """FakeAccessControl doesn't implement create() -- register_command() calls
    it to register the access level required for the "time" command."""

    def create(self, channel, command, access):
        pass


class _FakeSettingsWithCreate(FakeSettings):
    """FakeSettings doesn't implement create() -- TimeCore.__init__ calls it
    to register the (currently otherwise-unused) FormatString setting."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.created: list[tuple] = []

    def create(self, module, setting, value, longdesc, defaultoptions="", hidden=False, disporder=1):
        self.created.append((module, setting, value, longdesc))


def make_time_core(bot) -> TimeCore:
    bot.register_module(_FakeSettingsWithCreate(), "settings")
    bot.register_module(_FakeAccessControlWithCreate(), "access_control")
    return TimeCore(bot)


def test_registers_module_and_command(bot):
    time_core = make_time_core(bot)
    assert bot.core("time") is time_core
    assert bot.exists_command("all", "time")
    assert bot.get_command_handler("gc", "time") == "TimeCore"


def test_creates_format_string_setting(bot):
    bot.register_module(_FakeSettingsWithCreate(), "settings")
    bot.register_module(_FakeAccessControlWithCreate(), "access_control")
    settings = bot.core("settings")
    TimeCore(bot)
    assert settings.created == [("Time", "FormatString", "F jS, Y H:i", settings.created[0][3])]
    assert "gmdate" in settings.created[0][3]


def test_command_handler_returns_time_string(bot):
    time_core = make_time_core(bot)
    reply = time_core.command_handler("Someuser", "time", "tell")
    assert reply.startswith("It is currently ")
    assert isinstance(reply, str)


def test_command_handler_includes_ao_year_for_ao_game(bot):
    bot.game = "Ao"
    time_core = make_time_core(bot)
    reply = time_core.command_handler("Someuser", "time", "tell")
    assert "Rubi-Ka Universal Time" in reply
    assert str(time_core.ao_year()) in reply


def test_command_handler_omits_ao_year_for_non_ao_game(bot):
    bot.game = "Conan"
    time_core = make_time_core(bot)
    reply = time_core.command_handler("Someuser", "time", "tell")
    assert "Rubi-Ka" not in reply


def test_show_time_ignores_args(bot):
    time_core = make_time_core(bot)
    # command_handler ignores msg/origin entirely -- any input just shows the time.
    assert time_core.command_handler("A", "time foo bar", "gc") == time_core.command_handler("A", "time", "tell")


def test_ao_year_matches_current_utc_year_plus_offset(bot):
    time_core = make_time_core(bot)
    expected = 27474 + datetime.now(timezone.utc).year
    assert time_core.ao_year() == expected


def test_get_dhms_splits_seconds(bot):
    time_core = make_time_core(bot)
    # 1 day, 2 hours, 3 minutes, 4 seconds
    total = 86400 + 2 * 3600 + 3 * 60 + 4
    assert time_core.get_dhms(total) == {"days": 1, "hours": 2, "minutes": 3, "seconds": 4}


def test_get_dhms_zero(bot):
    time_core = make_time_core(bot)
    assert time_core.get_dhms(0) == {"days": 0, "hours": 0, "minutes": 0, "seconds": 0}


def test_format_seconds_positive(bot):
    time_core = make_time_core(bot)
    assert time_core.format_seconds(3661) == "01:01:01"


def test_format_seconds_negative(bot):
    time_core = make_time_core(bot)
    assert time_core.format_seconds(-3661) == "-01:01:01"


def test_format_seconds_zero(bot):
    time_core = make_time_core(bot)
    assert time_core.format_seconds(0) == "00:00:00"


def test_parse_time_plain_seconds(bot):
    time_core = make_time_core(bot)
    assert time_core.parse_time("45") == 45


def test_parse_time_minutes_suffix(bot):
    time_core = make_time_core(bot)
    assert time_core.parse_time("5m") == 300


def test_parse_time_hours_suffix(bot):
    time_core = make_time_core(bot)
    assert time_core.parse_time("2h") == 7200


def test_parse_time_days_suffix(bot):
    time_core = make_time_core(bot)
    assert time_core.parse_time("3d") == 3 * 86400


def test_parse_time_hms_colon_format(bot):
    time_core = make_time_core(bot)
    # "1:02:03" with no letter -> seconds-mode field progression: 1*3600 + 2*60 + 3
    assert time_core.parse_time("1:02:03") == 3600 + 120 + 3


def test_parse_time_invalid_returns_zero(bot):
    time_core = make_time_core(bot)
    assert time_core.parse_time("not-a-number") == 0


def test_time_ago_minutes_only(bot):
    time_core = make_time_core(bot)
    import time as time_module

    when = int(time_module.time()) - 125  # ~2 minutes ago
    result = time_core.time_ago(when)
    assert result.endswith("ago")
    assert "mins" in result


def test_time_ago_days_and_hours(bot):
    time_core = make_time_core(bot)
    import time as time_module

    when = int(time_module.time()) - (2 * 86400 + 3 * 3600 + 4 * 60)
    result = time_core.time_ago(when)
    assert result.startswith("2 days")
    assert "hours" in result
    assert result.endswith("ago")
