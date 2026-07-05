"""Ported (reduced) from Core/Statistics.php.

This is the small "statistics" core module -- not to be confused with the
much larger Core/BotStatistics.php ("bot_statistics"), which is a separate
module being ported independently.

The table is created directly with its (only ever existing) schema; the PHP
original has no schema-version migration logic to drop here.

`capture_statistic()` is a straight port: when the "Statistics" > "Enabled"
setting is on, it accumulates a running count per (module, action, comment)
tuple, doing a read-then-write (SELECT ... then UPDATE or INSERT) exactly as
the PHP did -- including the same lack of transactional protection against a
race between the SELECT and the following UPDATE/INSERT.
"""
from __future__ import annotations

from ..commodities.base import BasePassiveModule


class Statistics(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        db = bot.db
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('statistics', True)} "
            "(id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, "
            "module VARCHAR(100) NOT NULL, "
            "action VARCHAR(100) NOT NULL, "
            "comment VARCHAR(100) default '', "
            "count INT(10) unsigned NOT NULL)"
        )
        self.register_module("statistics")
        self.bot.core("settings").create("Statistics", "Enabled", False, "Capture Statistics?")

    def capture_statistic(self, module: str, action: str, comment: str = "", count: int = 1) -> None:
        if not self.bot.core("settings").get("Statistics", "Enabled"):
            return
        db = self.bot.db
        total_count = db.select(
            f"SELECT count FROM #___statistics WHERE module = '{module}' "
            f"AND action = '{action}' AND comment = '{comment}'"
        )
        if total_count:
            new_total = total_count[0][0] + count
            db.query(
                f"UPDATE #___statistics SET count = '{new_total}' WHERE module = '{module}' "
                f"AND action = '{action}' AND comment = '{comment}'"
            )
            return
        db.query(
            f"INSERT INTO #___statistics (module, action, comment, count) "
            f"VALUES ('{module}','{action}','{comment}',{count})"
        )
