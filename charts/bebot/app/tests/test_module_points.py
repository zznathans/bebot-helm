"""Tests for main_modules/points.py (ported from Modules/Points.php)."""
from __future__ import annotations

from bebot.commodities.base import BotError
from bebot.main_modules.points import Points
from bebot.main_modules.settings import Settings
from bebot.main_modules.tools import Tools
from fakes import FakeAccessControl


class _FakeAccessControlWithCreate(FakeAccessControl):
    def create(self, channel, command, access):
        pass

    def create_subcommand(self, channel, command, subcommand, access):
        pass


class FakeAlts:
    def __init__(self, mains=None, alts=None):
        self.mains = dict(mains or {})
        self.alts_map = dict(alts or {})

    def main(self, name):
        return self.mains.get(name, name)

    def get_alts(self, main):
        return self.alts_map.get(main, [])


class FakeSecurity:
    def __init__(self, access=True):
        self.access = access

    def check_access(self, player, level):
        return self.access


class FakePlayer:
    def __init__(self, bot, ids: dict[str, int] | None = None):
        self.bot = bot
        self.ids = dict(ids or {})

    def id(self, name):
        if name in self.ids:
            return self.ids[name]
        error = BotError(self.bot, "player")
        error.set(f"Unable to find player '{name}'", log=False)
        return error


class FakeDb:
    """Tracks a single in-memory raid_points table + log, keyed by id."""

    def __init__(self, points=None):
        # points: {id: [nickname, points, raiding, raidingas]}
        self.points = {pid: list(row) for pid, row in (points or {}).items()}
        self.logs: list[tuple] = []
        self.queries: list[str] = []

    def query(self, sql: str) -> bool:
        self.queries.append(sql)
        if sql.startswith("INSERT INTO #___raid_points_log"):
            return True
        if "#___raid_points" not in sql:
            return True
        if sql.startswith("UPDATE #___raid_points SET nickname"):
            pid = int(sql.rsplit("= ", 1)[1])
            nickname = sql.split("nickname = '")[1].split("'")[0]
            self.points.setdefault(pid, ["", 0, 0, ""])[0] = nickname
        elif sql.startswith("UPDATE #___raid_points SET points = points -"):
            pid = int(sql.rsplit("= ", 1)[1])
            amount = float(sql.split("points - ")[1].split(" WHERE")[0])
            self.points[pid][1] -= amount
        elif sql.startswith("UPDATE #___raid_points SET points = points +"):
            pid = int(sql.rsplit("= ", 1)[1])
            amount = float(sql.split("points + ")[1].split(" WHERE")[0])
            self.points[pid][1] += amount
        elif "INSERT INTO #___raid_points (id, nickname, points) VALUES" in sql:
            pid = int(sql.split("VALUES (")[1].split(",")[0])
            nickname = sql.split("', '")[0].split(", '")[1]
            amount = float(sql.split("', ")[1].split(")")[0])
            if pid in self.points:
                self.points[pid][1] += amount
            else:
                self.points[pid] = [nickname, amount, 0, ""]
        elif sql.startswith("UPDATE #___raid_points SET points = 0"):
            pid = int(sql.rsplit("= ", 1)[1])
            self.points[pid][1] = 0
        return True

    def select(self, sql: str, as_dict: bool = False):
        if "#___raid_points_log" in sql:
            return list(self.logs)
        if "#___raid_points" in sql and "points > 0" in sql and "LIMIT 25" in sql:
            rows = [(r[0], r[1]) for r in self.points.values() if r[1] > 0]
            return sorted(rows, key=lambda r: -r[1])[:25]
        if "#___raid_points" in sql and "points > 0" in sql:
            rows = [(pid, r[0], r[1]) for pid, r in self.points.items() if r[1] > 0]
            return sorted(rows, key=lambda r: -r[2])
        if "SELECT points, nickname" in sql:
            pid = int(sql.rsplit("= ", 1)[1])
            if pid in self.points:
                row = self.points[pid]
                return [(row[1], row[0])]
            return []
        if "SELECT points FROM" in sql:
            pid = int(sql.rsplit("= ", 1)[1])
            if pid in self.points:
                return [(self.points[pid][1],)]
            return []
        return []

    def real_escape_string(self, value) -> str:
        return str(value).replace("'", "\\'")

    def define_tablename(self, table: str, use_prefix) -> str:
        return table


def make_points(bot, monkeypatch, ids=None, points=None, alts=None, security=None, db=None) -> tuple[Points, FakeDb]:
    fake_db = db if db is not None else FakeDb(points=points)
    monkeypatch.setattr(bot, "db", fake_db)
    bot.register_module(_FakeAccessControlWithCreate(), "access_control")
    bot.register_module(FakePlayer(bot, ids), "player")
    bot.register_module(alts or FakeAlts(), "alts")
    bot.register_module(security or FakeSecurity(), "security")
    Settings(bot)
    Tools(bot)
    return Points(bot), fake_db


# -- construction ------------------------------------------------------------

def test_registers_as_points_module(bot, monkeypatch):
    module, _ = make_points(bot, monkeypatch)
    assert bot.core("points") is module


# -- show_points ---------------------------------------------------------------

def test_show_points_self_reports_own_balance(bot, monkeypatch):
    sent = []
    module, _ = make_points(bot, monkeypatch, ids={"Guy": 5}, points={5: ["Guy", 12.5, 0, ""]})
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))

    module.show_points("Guy", False)

    assert "12.5" in sent[0][1]


def test_show_points_no_balance_reports_zero(bot, monkeypatch):
    sent = []
    module, _ = make_points(bot, monkeypatch, ids={"Guy": 5})
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))

    module.show_points("Guy", False)

    assert "##highlight##0##end##" in sent[0][1]


def test_show_points_other_requires_admin(bot, monkeypatch):
    sent = []
    module, _ = make_points(bot, monkeypatch, ids={"Guy": 5, "Other": 6}, security=FakeSecurity(access=False))
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))

    module.show_points("Guy", "Other")

    assert "must be an admin" in sent[0][1]


def test_show_points_other_reports_target_balance_when_admin(bot, monkeypatch):
    sent = []
    module, _ = make_points(
        bot, monkeypatch, ids={"Guy": 5, "Other": 6}, points={6: ["Other", 30, 0, ""]},
        security=FakeSecurity(access=True),
    )
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))

    module.show_points("Guy", "Other")

    assert "Other has ##highlight##30##end##" in sent[0][1]


def test_show_points_unknown_target_reports_does_not_exist(bot, monkeypatch):
    sent = []
    module, _ = make_points(bot, monkeypatch, ids={"Guy": 5}, security=FakeSecurity(access=True))
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))

    module.show_points("Guy", "Ghost")

    assert "does not exist" in sent[0][1]


# -- give_points -----------------------------------------------------------------

def test_give_points_disabled_by_default(bot, monkeypatch):
    sent = []
    module, _ = make_points(bot, monkeypatch, ids={"Guy": 5, "Other": 6}, points={5: ["Guy", 10, 0, ""]})
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))

    module.give_points("Guy", "Other", "5")

    assert "disabled" in sent[0][1]


def test_give_points_transfers_between_accounts_when_enabled(bot, monkeypatch):
    sent = []
    module, db = make_points(bot, monkeypatch, ids={"Guy": 5, "Other": 6}, points={5: ["Guy", 10, 0, ""]})
    module.bot.core("settings").save("Points", "Transfer", True)
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))

    module.give_points("Guy", "Other", "4")

    assert db.points[5][1] == 6
    assert db.points[6][1] == 4
    assert "gave ##highlight##4.0##end##" in sent[0][1]


def test_give_points_rejects_non_numeric_amount(bot, monkeypatch):
    sent = []
    module, _ = make_points(bot, monkeypatch, ids={"Guy": 5, "Other": 6}, points={5: ["Guy", 10, 0, ""]})
    module.bot.core("settings").save("Points", "Transfer", True)
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))

    module.give_points("Guy", "Other", "abc")

    assert "not a valid points value" in sent[0][1]


def test_give_points_rejects_insufficient_balance(bot, monkeypatch):
    sent = []
    module, _ = make_points(bot, monkeypatch, ids={"Guy": 5, "Other": 6}, points={5: ["Guy", 2, 0, ""]})
    module.bot.core("settings").save("Points", "Transfer", True)
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))

    module.give_points("Guy", "Other", "5")

    assert "don't have that much" in sent[0][1]


def test_command_handler_blocks_give_during_active_bid(bot, monkeypatch):
    module, _ = make_points(bot, monkeypatch, ids={"Guy": 5, "Other": 6}, points={5: ["Guy", 10, 0, ""]})
    module.bot.core("settings").save("Points", "Transfer", True)

    class FakeBidding:
        bid = True

    bot.register_module(FakeBidding(), "bidding")

    result = module.command_handler("Guy", "points give Other 5", "tell")

    assert "forbidden" in result


# -- add_points / rem_points --------------------------------------------------

def test_add_points_credits_account_and_logs(bot, monkeypatch):
    module, db = make_points(bot, monkeypatch, ids={"Guy": 5, "Other": 6}, points={6: ["Other", 3, 0, ""]})

    result = module.add_points("Guy", "Other", "7", "raid reward")

    assert result is True
    assert db.points[6][1] == 10
    assert db.queries[-1].startswith("INSERT INTO #___raid_points_log")


def test_add_points_unknown_player_returns_false(bot, monkeypatch):
    module, _ = make_points(bot, monkeypatch, ids={"Guy": 5})

    result = module.add_points("Guy", "Ghost", "7", "raid reward")

    assert result is False


def test_rem_points_debits_account(bot, monkeypatch):
    module, db = make_points(bot, monkeypatch, ids={"Guy": 5, "Other": 6}, points={6: ["Other", 10, 0, ""]})

    result = module.rem_points("Guy", "Other", "4", "penalty")

    assert result is True
    assert db.points[6][1] == 6


# -- transfer_points / tomain_points -------------------------------------------

def test_transfer_points_requires_superadmin(bot, monkeypatch):
    sent = []
    module, _ = make_points(bot, monkeypatch, security=FakeSecurity(access=False))
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))

    module.transfer_points("Guy", "on")

    assert "must be a superadmin" in sent[0][1]


def test_transfer_points_enables_when_superadmin(bot, monkeypatch):
    sent = []
    module, _ = make_points(bot, monkeypatch, security=FakeSecurity(access=True))
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))

    module.transfer_points("Guy", "on")

    assert bot.core("settings").get("Points", "Transfer") is True
    assert "enabled" in sent[0][1]


def test_tomain_points_check_reports_current_state(bot, monkeypatch):
    sent = []
    module, _ = make_points(bot, monkeypatch)
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))

    module.tomain_points("Guy", "check")

    assert "option is off" in sent[0][1]


# -- top_points / all_points ---------------------------------------------------

def test_top_points_lists_accounts_with_balance(bot, monkeypatch):
    sent = []
    module, _ = make_points(
        bot, monkeypatch, points={5: ["Guy", 20, 0, ""], 6: ["Other", 40, 0, ""]},
    )
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))

    module.top_points("Guy")

    assert "Other" in sent[0][1]
    assert "Guy" in sent[0][1]


def test_top_points_reports_when_empty(bot, monkeypatch):
    sent = []
    module, _ = make_points(bot, monkeypatch)
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))

    module.top_points("Guy")

    assert "no one with raidpoints" in sent[0][1]


# -- view_log --------------------------------------------------------------------

def test_view_log_denies_viewing_others_logs_without_superadmin(bot, monkeypatch):
    module, _ = make_points(bot, monkeypatch, security=FakeSecurity(access=False))

    result = module.view_log("Guy", "Other", "")

    assert "must be an ##highlight##superadmin##end##" in result


def test_view_log_shows_own_logs(bot, monkeypatch):
    module, db = make_points(bot, monkeypatch)
    db.logs = [("Guy", 5, "Admin", 1_700_000_000, "reward")]

    result = module.view_log("Guy", "", "")

    assert "Logs for Guy and his alts" in result
    assert result.startswith("Logs for Guy and his alts :: ")


def test_view_log_reports_no_logs(bot, monkeypatch):
    module, _ = make_points(bot, monkeypatch)

    result = module.view_log("Guy", "", "")

    assert "No logs Found" in result
