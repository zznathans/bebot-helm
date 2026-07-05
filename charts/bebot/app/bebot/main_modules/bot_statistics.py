"""Ported from Core/BotStatistics.php.

Registers itself as bot.core("bot_statistics"). Tracks this bot's own
online/offline history across restarts in two tables:

  - #___bots: one row per (bot, dim) holding the timestamp the current
    online period started (`online`), the last heartbeat timestamp
    (`time`, refreshed every cron tick), the timestamp the bot was first
    ever seen (`start`), and cumulative `total` online-seconds / `restarts`
    counted for periods older than 30 days (folded in from bots_log by the
    24-hour cron, see cron() below).
  - #___bots_log: one row per completed online-period ("session") that
    hasn't yet been folded into the `total`/`restarts` counters above.

On construction, start() either creates the initial row for this
(bot, dim) or -- if the bot was online long enough since the last cron
tick to be considered a real session rather than crash-loop noise --
closes out the previous session into bots_log and opens a new one.

Cut vs. the PHP original:
  - The "Bots"/"DB" setting (an alternate-database-name prefix for these
    two tables, letting multiple bots share one physical DB while keeping
    stats elsewhere) is dropped. Nothing else in this port implements that
    kind of cross-database table redirection, and it isn't needed to run
    a single bot instance; the tables simply live in the bot's own schema.
  - The v1->v2->v3 schema-version migration chain (update_table(), and the
    underlying db.get_version/set_version/update_table dance) is dropped,
    matching the precedent in main_modules/settings.py and
    main_modules/access_control.py: the tables are created directly with
    their final schema (bots: ID, bot, dim, online, time, start, total,
    restarts; bots_log: ID, bot, dim, start, end) since there is nothing to
    migrate for a fresh Python port.
"""
from __future__ import annotations

import time

from ..commodities.base import BasePassiveModule


def _is_numeric(value: str) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


class BotStatistics(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.online = False
        db = bot.db
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('bots', False)} ("
            "ID INT NOT NULL auto_increment PRIMARY KEY, "
            "bot VARCHAR(20), "
            "dim VARCHAR(20) NOT NULL default '', "
            "online INT NOT NULL default '0', "
            "time INT NOT NULL default '0', "
            "start INT NOT NULL default '0', "
            "total INT NOT NULL default '0', "
            "restarts INT NOT NULL default '0'"
            ")"
        )
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('bots_log', False)} ("
            "ID INT NOT NULL auto_increment PRIMARY KEY, "
            "bot VARCHAR(20), "
            "dim VARCHAR(20) NOT NULL default '', "
            "start INT NOT NULL default '0', "
            "end INT NOT NULL default '0'"
            ")"
        )
        self.start()
        self.register_event("cron", "1min")
        self.register_event("cron", "24hour")
        self.register_event("disconnect")
        self.register_module("bot_statistics")

    def _current_dim(self) -> str:
        """Ao dimensions >= 90 are "shadowlevel" mirrors of dim-90; the PHP
        original folds those back onto the base dimension for stats purposes."""
        dimension = self.bot.dimension
        if str(self.bot.game).lower() == "ao" and int(dimension) >= 90:
            return str(int(dimension) - 90)
        return str(dimension)

    def start(self) -> None:
        dim = self._current_dim()
        now = int(time.time())
        result = self.bot.db.select(
            f"SELECT bot, dim, online, time FROM #___bots WHERE bot = '{self.bot.botname}' AND dim = '{dim}'"
        )
        if not result:
            self.bot.db.query(
                "INSERT INTO #___bots (bot, dim, online, time, start) VALUES "
                f"('{self.bot.botname}', '{dim}', {now}, 0, {now})"
            )
        else:
            row = result[0]
            if row[2] < row[3]:
                # The bot was online long enough for a cron tick to move `time`
                # past `online` -- a real session, not crash-loop noise. Close
                # it out into the log.
                self.bot.db.query(
                    "INSERT INTO #___bots_log (bot, dim, start, end) VALUES "
                    f"('{row[0]}', '{row[1]}', {row[2]}, {row[3]})"
                )
            self.bot.db.query(
                f"UPDATE #___bots SET online = {now} WHERE bot = '{self.bot.botname}' AND dim = '{dim}'"
            )
            self.online = True

    def up_bots(self, name, origin, bot=False, dim=False) -> str:
        """Short one-line status string ("Status: Online for X"), for
        embedding inline in other modules' output."""
        bot = bot or self.bot.botname
        dim = dim or self.bot.dimension
        result = self.bot.db.select(
            "SELECT bot, dim, online, time, start, total, restarts FROM #___bots "
            f"WHERE bot = '{bot}' AND dim = '{dim}' LIMIT 1"
        )
        if result:
            row = result[0]
            if row[3] + (60 * 3) > time.time():
                return "Status: Online for " + self.timedif(row[2], row[3])
            return "Status: Offline for " + self.timedif(row[3], time.time())
        return "Status: Unknown ..."

    def check_bots(self, name, origin, bot=False, dim=False) -> str:
        """Full stats blob: either a single bot's detailed uptime breakdown
        (24h/7d/30d/since-install) or, with no bot given, a summary listing
        of every tracked bot's current status."""
        db = self.bot.db
        if not dim:
            dim = self.bot.dimension
        if bot:
            bot = db.real_escape_string(bot)
            dim = db.real_escape_string(dim)
            result = db.select(
                "SELECT bot, dim, online, time, start, total, restarts FROM #___bots "
                f"WHERE bot = '{bot}' AND dim = '{dim}'"
            )
            if not result:
                return "Bot not Found."
            row = list(result[0])
            now = time.time()
            inside = f":::  Bot: {row[0]}  :::\n"
            inside += "\nStatus: "
            if row[3] + (60 * 3) > now:
                inside += "##green##Online##end## for " + self.timedif(row[2], row[3])
            else:
                inside += "##red##Offline##end## for " + self.timedif(row[3], now)
            log = db.select(
                f"SELECT start, end FROM #___bots_log WHERE bot = '{row[0]}' AND dim = '{row[1]}'"
            ) or []
            # Note: if the bot hasn't been running long enough for a full
            # day/week/month window, day/week/month get shrunk to "time since
            # install" below -- but matching the PHP original, the
            # day/week/month*time* cutoffs used to bucket log entries are
            # NOT recomputed afterwards, so they still reflect the original
            # (unshrunk) window boundary. This is preserved as a faithful
            # port rather than "fixed".
            day = 60 * 60 * 24
            daytime = now - day
            if daytime < row[4]:
                day = now - row[4]
            week = day * 7
            weektime = now - week
            if weektime < row[4]:
                week = now - row[4]
            month = day * 30
            monthtime = now - month
            if monthtime < row[4]:
                month = now - row[4]
            weekon = 0
            monthon = 0
            allon = 0
            dayon = 0
            restartd = -1
            restartw = -1
            restartm = -1
            restart = -1
            if row[3] + (60 * 3) > now:
                row[3] = now
            log = list(log) + [(row[2], row[3])]
            for start, end in log:
                if start > daytime:
                    restartd += 1
                    dayon += end - start
                elif end > daytime:
                    restartd += 1
                    dayon += end - daytime
                if start > weektime:
                    restartw += 1
                    weekon += end - start
                elif end > weektime:
                    restartw += 1
                    weekon += end - weektime
                if start > monthtime:
                    restartm += 1
                    monthon += end - start
                elif end > monthtime:
                    restartm += 1
                    monthon += end - monthtime
                restart += 1
                allon += end - start
            restart += row[6]
            allon += row[5]

            perc = round((dayon / day) * 100, 1) if day else 0.0
            if perc == 100 and dayon != day:
                perc = 99.9
            off = self.timedif(0, day - dayon, False)
            dayon_s = self.timedif(0, dayon, False)
            inside += f"\n\nLast 24 Hours:\n     Online: {dayon_s}\n     Offline: {off}\n     Restarts: {restartd}\n     Percent: {perc}%"

            perc = round((weekon / week) * 100, 1) if week else 0.0
            if perc == 100 and weekon != week:
                perc = 99.9
            off = self.timedif(0, week - weekon, False)
            weekon_s = self.timedif(0, weekon, False)
            inside += f"\n\nLast 7 Days:\n     Online: {weekon_s}\n     Offline: {off}\n     Restarts: {restartw}\n     Percent: {perc}%"

            perc = round((monthon / month) * 100, 1) if month else 0.0
            if perc == 100 and weekon != week:
                perc = 99.9
            off = self.timedif(0, month - monthon, False)
            monthon_s = self.timedif(0, monthon, False)
            inside += f"\n\nLast 30 Days:\n     Online: {monthon_s}\n     Offline: {off}\n     Restarts: {restartm}\n     Percent: {perc}%"

            sincestart = now - row[4]
            perc = round((allon / sincestart) * 100, 1) if sincestart else 0.0
            if perc == 100 and weekon != week:
                perc = 99.9
            off = self.timedif(0, sincestart - allon, False)
            allon_s = self.timedif(0, allon, False)
            inside += f"\n\nSince Install:\n     Online: {allon_s}\n     Offline: {off}\n     Restarts: {restart}\n     Percent: {perc}%"

            blob = self.bot.core("tools").make_blob("click to view", inside)
            return f"Bot Stats for ##highlight##{row[0]}##end## :: {blob}"

        result = db.select("SELECT bot, dim, online, time FROM #___bots ORDER BY dim, online DESC")
        if not result:
            return "No Bots Found."
        grouped: dict[str, str] = {}
        now = time.time()
        for name_, dim_, online_, time_ in result:
            if time_ + (60 * 3) > now:
                status = "##green##Online##end## for " + self.timedif(online_, time_)
            else:
                status = "##red##Offline##end## for " + self.timedif(time_, now)
            link = self.bot.core("tools").chatcmd(f"bots {name_} {dim_}", name_, origin)
            grouped[dim_] = grouped.get(dim_, "") + f"\n{link} is {status}"
        inside2 = ":::  Bots  :::\n"
        for key, value in grouped.items():
            label = f"RK {key}" if _is_numeric(key) else key
            inside2 += f"\n\n##orange##{label} \n##end##"
            inside2 += value
        blob = self.bot.core("tools").make_blob("click to view", inside2)
        return f"Bots :: {blob}"

    def timedif(self, low: float, high: float, showmins: bool = True) -> str:
        dif = high - low
        if dif < 60 * 60:
            mins = int(dif // 60)
            ms = "s" if mins > 1 else ""
            return f"{mins} Minute{ms}"
        if dif < 60 * 60 * 24:
            mins = int(dif // 60)
            hours = mins // 60
            minsrem = mins - (hours * 60)
            ms = "s" if minsrem > 1 else ""
            hs = "s" if hours > 1 else ""
            if showmins:
                return f"{hours} Hour{hs} and {minsrem} Minute{ms}"
            return f"{hours} Hour{hs}"
        mins = int(dif // 60)
        hours = mins // 60
        days = hours // 24
        minsrem = mins - (hours * 60)
        hoursrem = hours - (days * 24)
        ms = "s" if minsrem > 1 else ""
        hs = "s" if hoursrem > 1 else ""
        ds = "s" if days > 1 else ""
        if showmins:
            return f"{days} Day{ds}, {hoursrem} Hour{hs} and {minsrem} Minute{ms}"
        return f"{days} Day{ds}, {hoursrem} Hour{hs}"

    def cron(self, duration=None) -> None:
        self.online = True
        now = int(time.time())
        self.bot.db.query(
            f"UPDATE #___bots SET time = '{now}' WHERE bot = '{self.bot.botname}' AND dim = '{self.bot.dimension}'"
        )
        if duration == 86400:
            monthago = now - (60 * 60 * 24 * 30)
            log = self.bot.db.select(
                "SELECT ID, start, end FROM #___bots_log WHERE bot = "
                f"'{self.bot.botname}' AND dim = '{self.bot.dimension}' AND end < {monthago}"
            )
            for entry_id, start, end in log or []:
                total = end - start
                self.bot.db.query(
                    f"UPDATE #___bots SET total = total + {total}, restarts = restarts + 1 "
                    f"WHERE bot = '{self.bot.botname}' AND dim = '{self.bot.dimension}'"
                )
                self.bot.db.query(f"DELETE FROM #___bots_log WHERE ID = {entry_id}")

    def disconnect(self) -> None:
        if self.online:
            self.bot.db.query(
                f"UPDATE #___bots SET time = {int(time.time())} "
                f"WHERE bot = '{self.bot.botname}' AND dim = '{self.bot.dimension}'"
            )
