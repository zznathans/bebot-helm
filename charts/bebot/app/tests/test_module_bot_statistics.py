import time

from bebot.main_modules.bot_statistics import BotStatistics
from bebot.main_modules.tools import Tools


def make_bot_statistics(bot, monkeypatch, select_results=None) -> BotStatistics:
    """select_results: either a fixed list (returned for every select() call)
    or a callable(sql) -> rows, so tests can vary the answer per-query."""
    Tools(bot)
    if select_results is None:
        monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [])
    elif callable(select_results):
        monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: select_results(sql))
    else:
        monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: select_results)
    return BotStatistics(bot)


# -- construction / start() -------------------------------------------------

def test_creates_both_tables_on_construction(bot, monkeypatch):
    make_bot_statistics(bot, monkeypatch)
    create_queries = [q for q in bot.db.queries if "CREATE TABLE" in q]
    assert len(create_queries) == 2
    assert any("bots_log" in q for q in create_queries)
    assert any("bots (" in q for q in create_queries)


def test_registers_as_bot_statistics_module(bot, monkeypatch):
    module = make_bot_statistics(bot, monkeypatch)
    assert bot.core("bot_statistics") is module


def test_start_inserts_new_row_when_no_existing_row(bot, monkeypatch):
    module = make_bot_statistics(bot, monkeypatch, select_results=[])
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___bots (")]
    assert len(insert_queries) == 1
    assert f"'{bot.botname}'" in insert_queries[0]
    assert module.online is False


def test_start_with_prior_real_session_logs_and_reopens(bot, monkeypatch):
    # online(2) < time(3) => bot was up long enough to count as a real session.
    row = [(bot.botname, str(bot.dimension), 1000, 2000)]
    module = make_bot_statistics(bot, monkeypatch, select_results=row)
    log_inserts = [q for q in bot.db.queries if q.startswith("INSERT INTO #___bots_log")]
    assert len(log_inserts) == 1
    assert "1000, 2000" in log_inserts[0]
    update_queries = [q for q in bot.db.queries if q.startswith("UPDATE #___bots SET online")]
    assert len(update_queries) == 1
    assert module.online is True


def test_start_with_crashloop_row_does_not_log(bot, monkeypatch):
    # online(2000) >= time(1000): never ticked past online, so no session to log.
    row = [(bot.botname, str(bot.dimension), 2000, 1000)]
    module = make_bot_statistics(bot, monkeypatch, select_results=row)
    log_inserts = [q for q in bot.db.queries if q.startswith("INSERT INTO #___bots_log")]
    assert log_inserts == []
    assert module.online is True


# -- up_bots -----------------------------------------------------------------

def test_up_bots_unknown_when_no_row(bot, monkeypatch):
    module = make_bot_statistics(bot, monkeypatch, select_results=[])
    assert module.up_bots("someone", "tell") == "Status: Unknown ..."


def test_up_bots_online(bot, monkeypatch):
    now = time.time()
    row = [(bot.botname, str(bot.dimension), now - 100, now - 10, now - 500, 0, 0)]
    module = make_bot_statistics(bot, monkeypatch, select_results=row)
    result = module.up_bots("someone", "tell")
    assert result.startswith("Status: Online for")


def test_up_bots_offline(bot, monkeypatch):
    now = time.time()
    row = [(bot.botname, str(bot.dimension), now - 1000, now - 500, now - 5000, 0, 0)]
    module = make_bot_statistics(bot, monkeypatch, select_results=row)
    result = module.up_bots("someone", "tell")
    assert result.startswith("Status: Offline for")


# -- check_bots: single bot ---------------------------------------------------

def test_check_bots_not_found(bot, monkeypatch):
    def selects(sql):
        if "FROM #___bots WHERE" in sql:
            return []
        return []

    module = make_bot_statistics(bot, monkeypatch, select_results=selects)
    assert module.check_bots("someone", "tell", bot="OtherBot") == "Bot not Found."


def test_check_bots_single_bot_online_report(bot, monkeypatch):
    now = time.time()
    start = now - (60 * 60 * 24 * 2)  # installed 2 days ago

    def selects(sql):
        if sql.startswith("SELECT bot, dim, online, time, start, total, restarts FROM #___bots"):
            return [(bot.botname, str(bot.dimension), now - 100, now - 10, start, 0, 1)]
        if sql.startswith("SELECT start, end FROM #___bots_log"):
            return [(start, now - 3600)]
        return []

    module = make_bot_statistics(bot, monkeypatch, select_results=selects)
    result = module.check_bots("someone", "tell", bot=bot.botname)
    assert result.startswith(f"Bot Stats for ##highlight##{bot.botname}##end## ::")
    assert "Last 24 Hours:" in result
    assert "Last 7 Days:" in result
    assert "Last 30 Days:" in result
    assert "Since Install:" in result
    assert "##green##Online##end##" in result


def test_check_bots_single_bot_offline_report(bot, monkeypatch):
    now = time.time()
    start = now - (60 * 60 * 24 * 2)

    def selects(sql):
        if sql.startswith("SELECT bot, dim, online, time, start, total, restarts FROM #___bots"):
            return [(bot.botname, str(bot.dimension), now - 2000, now - 1000, start, 0, 0)]
        if sql.startswith("SELECT start, end FROM #___bots_log"):
            return []
        return []

    module = make_bot_statistics(bot, monkeypatch, select_results=selects)
    result = module.check_bots("someone", "tell", bot=bot.botname)
    assert "##red##Offline##end##" in result
    assert "Restarts: 0" in result


def test_check_bots_no_prior_log_entries_still_produces_report(bot, monkeypatch):
    now = time.time()
    start = now - 3600  # just installed an hour ago

    def selects(sql):
        if sql.startswith("SELECT bot, dim, online, time, start, total, restarts FROM #___bots"):
            return [(bot.botname, str(bot.dimension), now - 100, now - 10, start, 0, 0)]
        if sql.startswith("SELECT start, end FROM #___bots_log"):
            return []
        return []

    module = make_bot_statistics(bot, monkeypatch, select_results=selects)
    result = module.check_bots("someone", "tell", bot=bot.botname)
    assert "Bot Stats for" in result
    assert "Percent:" in result


# -- check_bots: all bots ------------------------------------------------------

def test_check_bots_no_bots_found(bot, monkeypatch):
    module = make_bot_statistics(bot, monkeypatch, select_results=[])
    assert module.check_bots("someone", "tell") == "No Bots Found."


def test_check_bots_lists_all_bots_grouped_by_dim(bot, monkeypatch):
    now = time.time()

    def selects(sql):
        if sql.startswith("SELECT bot, dim, online, time FROM #___bots ORDER BY"):
            return [
                ("BotOne", "5", now - 100, now - 10),
                ("BotTwo", "5", now - 5000, now - 4000),
                ("BotThree", "irc", now - 100, now - 10),
            ]
        return []

    module = make_bot_statistics(bot, monkeypatch, select_results=selects)
    result = module.check_bots("someone", "tell")
    assert result.startswith("Bots ::")
    assert "RK 5" in result
    assert "##orange##irc " in result
    assert "BotOne" in result
    assert "BotTwo" in result
    assert "BotThree" in result


# -- timedif -------------------------------------------------------------------

def test_timedif_minutes_singular(bot, monkeypatch):
    module = make_bot_statistics(bot, monkeypatch)
    assert module.timedif(0, 60) == "1 Minute"


def test_timedif_minutes_plural(bot, monkeypatch):
    module = make_bot_statistics(bot, monkeypatch)
    assert module.timedif(0, 300) == "5 Minutes"


def test_timedif_hours_and_minutes(bot, monkeypatch):
    module = make_bot_statistics(bot, monkeypatch)
    dif = 2 * 3600 + 5 * 60
    assert module.timedif(0, dif) == "2 Hours and 5 Minutes"


def test_timedif_hours_only_when_showmins_false(bot, monkeypatch):
    module = make_bot_statistics(bot, monkeypatch)
    dif = 3 * 3600 + 5 * 60
    assert module.timedif(0, dif, False) == "3 Hours"


def test_timedif_days_hours_minutes(bot, monkeypatch):
    module = make_bot_statistics(bot, monkeypatch)
    dif = 2 * 86400 + 3 * 3600 + 10 * 60
    assert module.timedif(0, dif) == "2 Days, 3 Hours and 10 Minutes"


def test_timedif_days_only_when_showmins_false(bot, monkeypatch):
    module = make_bot_statistics(bot, monkeypatch)
    dif = 5 * 86400 + 2 * 3600
    assert module.timedif(0, dif, False) == "5 Days, 2 Hours"


def test_timedif_single_day_single_hour_single_minute_no_plural(bot, monkeypatch):
    module = make_bot_statistics(bot, monkeypatch)
    dif = 1 * 86400 + 1 * 3600 + 1 * 60
    assert module.timedif(0, dif) == "1 Day, 1 Hour and 1 Minute"


# -- cron ----------------------------------------------------------------------

def test_cron_updates_heartbeat_time(bot, monkeypatch):
    module = make_bot_statistics(bot, monkeypatch)
    before = len(bot.db.queries)
    module.cron(60)
    new_queries = bot.db.queries[before:]
    assert any(q.startswith("UPDATE #___bots SET time = ") for q in new_queries)
    assert module.online is True


def test_cron_24hour_with_no_old_log_entries_does_nothing_extra(bot, monkeypatch):
    module = make_bot_statistics(bot, monkeypatch, select_results=[])
    before = len(bot.db.queries)
    module.cron(86400)
    new_queries = bot.db.queries[before:]
    assert not any("total = total" in q for q in new_queries)


def test_cron_24hour_folds_old_log_entries_into_totals(bot, monkeypatch):
    old_log_rows = [(42, 1000, 4600)]  # 3600 seconds online, one session

    def selects(sql):
        if sql.startswith("SELECT ID, start, end FROM #___bots_log"):
            return old_log_rows
        return []

    module = make_bot_statistics(bot, monkeypatch, select_results=selects)
    before = len(bot.db.queries)
    module.cron(86400)
    new_queries = bot.db.queries[before:]
    total_updates = [q for q in new_queries if "total = total + 3600" in q]
    assert len(total_updates) == 1
    assert "restarts = restarts + 1" in total_updates[0]
    deletes = [q for q in new_queries if q == "DELETE FROM #___bots_log WHERE ID = 42"]
    assert len(deletes) == 1


# -- disconnect ------------------------------------------------------------------

def test_disconnect_writes_final_heartbeat_when_online(bot, monkeypatch):
    row = [(bot.botname, str(bot.dimension), 1000, 2000)]
    module = make_bot_statistics(bot, monkeypatch, select_results=row)
    assert module.online is True
    before = len(bot.db.queries)
    module.disconnect()
    new_queries = bot.db.queries[before:]
    assert any(q.startswith("UPDATE #___bots SET time = ") for q in new_queries)


def test_disconnect_does_nothing_when_never_online(bot, monkeypatch):
    module = make_bot_statistics(bot, monkeypatch, select_results=[])
    assert module.online is False
    before = len(bot.db.queries)
    module.disconnect()
    assert bot.db.queries[before:] == []
