from bebot.main_modules.bot_statistics import BotStatistics
from bebot.main_modules.bot_statistics_ui import BotStatisticsUi
from bebot.main_modules.tools import Tools
from fakes import FakeAccessControl


class _FakeAccessControlWithCreate(FakeAccessControl):
    """FakeAccessControl doesn't implement create() -- register_command()
    calls it to register the access level required for the "bots"/"environ"
    commands."""

    def create(self, channel, command, access):
        pass


def _select_dispatch(bots_rows=None, summary_rows=None, log_rows=None):
    """A bot.db.select() stand-in that answers the query shapes issued by
    core("bot_statistics")'s start()/check_bots()/up_bots(), while leaving
    every other query behaving like the default FakeMySQL (empty result).
    """
    bots_rows = bots_rows if bots_rows is not None else []
    summary_rows = summary_rows if summary_rows is not None else []
    log_rows = log_rows if log_rows is not None else []

    def fake_select(sql, *a, **kw):
        if "FROM #___bots_log" in sql:
            return list(log_rows)
        if "ORDER BY dim, online DESC" in sql:
            return list(summary_rows)
        if "FROM #___bots WHERE" in sql:
            return list(bots_rows)
        return []

    return fake_select


def make_module(bot, monkeypatch, bots_rows=None, summary_rows=None, log_rows=None) -> BotStatisticsUi:
    """Builds a real BotStatisticsUi wired to a real core("bot_statistics")
    BotStatistics module (integration-style, per the task brief), with
    bot.db.select faked to serve the query shapes both modules issue.
    """
    bot.register_module(_FakeAccessControlWithCreate(), "access_control")
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [])
    Tools(bot)
    BotStatistics(bot)
    module = BotStatisticsUi(bot)
    monkeypatch.setattr(
        bot.db, "select", _select_dispatch(bots_rows, summary_rows, log_rows)
    )
    return module


# -- construction / registration -----------------------------------------------

def test_registers_as_bot_statistics_ui_module(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    assert bot.core("bot_statistics_ui") is module


def test_registers_bots_and_environ_commands_on_all_channels(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    for channel in ("tell", "gc", "pgmsg"):
        assert bot.commands[channel]["bots"] is module
        assert bot.commands[channel]["environ"] is module


# -- environ ----------------------------------------------------------------------

def test_check_environ_reports_python_and_os_and_unknown_sql_when_no_conn(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.check_environ("Char1", "tell", "")
    assert "OS:" in result
    assert "Python:" in result
    assert "SQL: unknown" in result


def test_check_environ_reports_sql_server_version_when_conn_present(bot, monkeypatch):
    module = make_module(bot, monkeypatch)

    class _FakeConn:
        def get_server_info(self):
            return "8.0.99-fake"

    monkeypatch.setattr(bot.db, "conn", _FakeConn(), raising=False)
    result = module.check_environ("Char1", "tell", "")
    assert "SQL: 8.0.99-fake" in result


def test_command_handler_dispatches_environ(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.command_handler("Char1", "environ", "tell")
    assert "OS:" in result and "Python:" in result


# -- bots: summary listing (no bot given) ----------------------------------------

def test_check_bots_no_bots_found(bot, monkeypatch):
    module = make_module(bot, monkeypatch, summary_rows=[])
    module.bot.accessallbots = True
    result = module.check_bots("Char1", "tell", "")
    assert result == "No Bots Found."


def test_check_bots_summary_lists_all_bots(bot, monkeypatch):
    import time

    now = time.time()
    summary_rows = [
        ("Testbot", "5", now - 3600, now),
        ("Otherbot", "5", now - 7200, now - 4000),
    ]
    module = make_module(bot, monkeypatch, summary_rows=summary_rows)
    module.bot.accessallbots = True
    result = module.check_bots("Char1", "tell", "")
    assert "Bots ::" in result
    assert "Testbot" in result
    assert "Otherbot" in result


# -- bots: single bot lookup (accessallbots True) --------------------------------

def test_check_bots_accessallbots_true_bot_not_found(bot, monkeypatch):
    module = make_module(bot, monkeypatch, bots_rows=[])
    module.bot.accessallbots = True
    result = module.check_bots("Char1", "tell", "Unknownbot")
    assert result == "Bot not Found."


def test_check_bots_accessallbots_true_single_arg_uses_own_dimension(bot, monkeypatch):
    import time

    now = time.time()
    rows = [("Otherbot", str(bot.dimension), now - 100, now, now - 500, 0, 0)]
    module = make_module(bot, monkeypatch, bots_rows=rows)
    module.bot.accessallbots = True
    result = module.check_bots("Char1", "tell", "Otherbot")
    assert "Bot Stats for" in result
    assert "Otherbot" in result


def test_check_bots_accessallbots_true_bot_and_dim(bot, monkeypatch):
    import time

    now = time.time()
    rows = [("Otherbot", "7", now - 100, now, now - 500, 0, 0)]
    module = make_module(bot, monkeypatch, bots_rows=rows)
    module.bot.accessallbots = True
    result = module.check_bots("Char1", "tell", "Otherbot 7")
    assert "Bot Stats for" in result
    assert "Otherbot" in result


# -- bots: accessallbots False ignores user-supplied args ------------------------

def test_check_bots_accessallbots_false_ignores_args_uses_own_bot(bot, monkeypatch):
    import time

    now = time.time()
    rows = [(bot.botname, str(bot.dimension), now - 100, now, now - 500, 0, 0)]
    module = make_module(bot, monkeypatch, bots_rows=rows)
    assert module.bot.accessallbots is False
    result = module.check_bots("Char1", "tell", "SomeOtherBot 99")
    assert "Bot Stats for" in result
    assert bot.botname in result


def test_check_bots_accessallbots_false_with_empty_msg(bot, monkeypatch):
    import time

    now = time.time()
    rows = [(bot.botname, str(bot.dimension), now - 100, now, now - 500, 0, 0)]
    module = make_module(bot, monkeypatch, bots_rows=rows)
    result = module.check_bots("Char1", "tell", "")
    assert "Bot Stats for" in result
    assert bot.botname in result


# -- command_handler dispatch for "bots" -----------------------------------------

def test_command_handler_dispatches_bots_no_args(bot, monkeypatch):
    import time

    now = time.time()
    rows = [(bot.botname, str(bot.dimension), now - 100, now, now - 500, 0, 0)]
    module = make_module(bot, monkeypatch, bots_rows=rows)
    result = module.command_handler("Char1", "bots", "tell")
    assert "Bot Stats for" in result


def test_command_handler_dispatches_bots_with_args(bot, monkeypatch):
    import time

    now = time.time()
    rows = [("Otherbot", "7", now - 100, now, now - 500, 0, 0)]
    module = make_module(bot, monkeypatch, bots_rows=rows)
    module.bot.accessallbots = True
    result = module.command_handler("Char1", "bots Otherbot 7", "tell")
    assert "Bot Stats for" in result
    assert "Otherbot" in result


def test_command_handler_unrecognized_command_returns_error(bot, monkeypatch):
    module = make_module(bot, monkeypatch)
    result = module.command_handler("Char1", "frobnicate", "tell")
    assert "Broken plugin" in result
    assert "frobnicate" in result
