"""Ported from Modules/Points.php -- raid-point economy (`points` command).

Schema-migration code (update_table's version-1..4 ALTERs, folded in from
older raid_points layouts) is dropped -- the table is created directly
with the final (v5) schema, matching the precedent set by settings.py,
player_notes.py etc.

`points give`'s "no bidding in progress" guard checks `core("bidding")`,
which doesn't exist yet (Bid.php isn't ported); `exists_module()` degrades
that check to always-false (no active bid can ever block a give), which
is the correct behavior until Bid lands -- documented here rather than
silently dropped.
"""
from __future__ import annotations

import time

from ..commodities.base import BaseActiveModule, BotError

ACCESS_SUBCOMMANDS = {
    "add": "SUPERADMIN",
    "del": "SUPERADMIN",
    "rem": "SUPERADMIN",
    "transfer": "SUPERADMIN",
    "tomain": "SUPERADMIN",
    "all": "SUPERADMIN",
}


def _round(num) -> str:
    text = f"{float(num):.2f}"
    whole, _, frac = text.partition(".")
    return whole if frac == "00" else text


class Points(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        db = bot.db
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('raid_points', True)} "
            "(id INT NOT NULL PRIMARY KEY, nickname VARCHAR(20), "
            "points decimal(11,2) default '0.00', raiding TINYINT DEFAULT '0', raidingas VARCHAR(20))"
        )
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('raid_points_log', True)} "
            "(id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, name VARCHAR(20), "
            "points decimal(11,2) default '0.00', by_who VARCHAR(20), time INT, why VARCHAR(500))"
        )
        bot.core("settings").create("Points", "Transfer", False, "Can points be transfered?")
        bot.core("settings").create("Points", "To_Main", False, "Are points shared over all alts (hidden) ?", "", True)
        self.help["description"] = "Manage raid points"
        self.help["command"] = {}
        self.help["command"]["points [name]"] = (
            "Shows the amount of points in [name]s account. If [name] is not given it shows the "
            "points in your account"
        )
        self.help["command"]["points give <name> <points>"] = "Gives <points> points to player <name>"
        self.help["command"]["points add <name> <points> <why>"] = (
            "Adds <points> points to player <name>s point account"
        )
        self.help["command"]["points [del/rem] <name> <points> <why>"] = (
            "Removes <points> points from player <name>s point account"
        )
        self.help["command"]["points transfer <(on|off)>"] = "Turns ability to give points on or off."
        self.help["command"]["points tomain <(on|off)>"] = (
            "Turns ability to concentrate points at main on (which turns alt confirmation on also) or off."
        )
        self.help["command"]["points all"] = "Shows all players points for admin."
        self.help["command"]["points top"] = "Shows the 25 biggest point accounts."
        self.help["command"]["points log"] = "Shows your character points log."
        self.register_command("all", "points", "GUEST", ACCESS_SUBCOMMANDS)
        self.register_module("points")

    def command_handler(self, name, msg, origin):
        parts = msg.split(" ", 4)
        while len(parts) < 5:
            parts.append("")
        sub = parts[1].lower()
        if sub == "give":
            if self.bot.exists_module("bidding") and self.bot.core("bidding").bid:
                return "Error: giving point is ##highlight##forbidden##end## during a bid"
            self.give_points(name, parts[2], parts[3])
        elif sub == "add":
            if len(parts[4]) < 5:
                return "Error: Reason required, min ##highlight##5##end## letters"
            self.add_points(name, parts[2], parts[3], parts[4])
        elif sub in ("del", "rem"):
            if len(parts[4]) < 5:
                return "Error: Reason required, min ##highlight##5##end## letters"
            self.rem_points(name, parts[2], parts[3], parts[4])
        elif sub == "transfer":
            self.transfer_points(name, parts[2])
        elif sub == "tomain":
            self.tomain_points(name, parts[2])
        elif sub == "all":
            self.all_points(name)
        elif sub == "top":
            self.top_points(name)
        elif sub in ("log", "logs"):
            return self.view_log(name, parts[2], parts[3])
        elif sub == "":
            self.show_points(name, False)
        else:
            self.show_points(name, parts[1])
        return False

    def show_points(self, name, target):
        db = self.bot.db
        if not target or target.lower() == name.lower():
            result = db.select(f"SELECT points, nickname FROM #___raid_points WHERE id = {self.points_to(name)}")
            if result:
                if result[0][1] == "":
                    db.query(
                        f"UPDATE #___raid_points SET nickname = '{self.points_to_name(name)}' "
                        f"WHERE id = {self.points_to(name)}"
                    )
                points = _round(result[0][0])
            else:
                points = 0
            self.bot.send_tell(name, f"You have ##highlight##{points}##end## raidpoints.")
            return
        if self.bot.core("security").check_access(name, "admin"):
            if isinstance(self.bot.core("player").id(target), BotError):
                self.bot.send_tell(name, f"Player ##highlight##{target}##end## does not exist.")
                return
            result = db.select(f"SELECT points, nickname FROM #___raid_points WHERE id = {self.points_to(target)}")
            if result:
                if result[0][1] == "":
                    db.query(
                        f"UPDATE #___raid_points SET nickname = '{self.points_to_name(target)}' "
                        f"WHERE id = {self.points_to(target)}"
                    )
                points = _round(result[0][0])
            else:
                points = 0
            self.bot.send_tell(name, f"Player {target} has ##highlight##{points}##end## raidpoints.")
        else:
            self.bot.send_tell(name, "You must be an admin to view others points")

    def all_points(self, name):
        self.bot.send_tell(name, "Fetching full list of points, this might take a while.")
        result = self.bot.db.select("SELECT nickname, points FROM #___raid_points WHERE points > 0 ORDER BY points DESC")
        inside = "##blob_title##:::: All raidpoints ::::##end####blob_text##\n\n"
        for nickname, points in result or []:
            space = " " * max(round(-len(nickname) * 1.5), 0)
            inside += f"##highlight##{nickname}##end##{space} - ##highlight##{_round(points)}##end##\n"
        self.bot.send_tell(
            name, "All raidpoints :: " + self.bot.core("tools").make_blob("click to view", inside)
        )

    def top_points(self, name):
        result = self.bot.db.select(
            "SELECT nickname, points FROM #___raid_points WHERE points > 0 ORDER BY points DESC LIMIT 25"
        )
        if not result:
            self.bot.send_tell(name, "Im sorry but there appears to be no one with raidpoints yet")
            return
        inside = "##blob_title##:::: Top 25 raidpoints ::::##end####blob_text##\n\n"
        for num, (nickname, points) in enumerate(result, start=1):
            space = " " * max(round(-len(nickname) * 1.5), 0)
            inside += f"{num}. ##highlight##{nickname}##end##{space} - ##highlight##{_round(points)}##end##\n"
        self.bot.send_tell(name, "Top 25 raidpoints :: " + self.bot.core("tools").make_blob("click to view", inside))

    def tomain_points(self, name, toggle):
        name = self.bot.core("tools").sanitize_player(name)
        toggle = toggle.lower()
        check = False
        add = ""
        stat = False
        txt = "disabled"
        if toggle == "on":
            stat = True
            txt = "enabled"
            add = " All points have been transfered."
        elif toggle == "check":
            check = True
            if not self.bot.core("settings").get("Points", "To_main"):
                add = " To_main option is off ; points are given to any character."
            else:
                add = " To_main option is on ; points are concentrated on mains."
        else:
            stat = False
            txt = "disabled"
            add = " No points have been transfered."

        if not check:
            self.bot.core("settings").save("Points", "To_main", stat)

        if stat:
            self.bot.core("settings").save("Alts", "Confirmation", True)
            db = self.bot.db
            result = db.select("SELECT id, nickname, points FROM #___raid_points WHERE points > 0") or []
            for res_id, nickname, points in result:
                if res_id != self.points_to(nickname):
                    db.query(f"UPDATE #___raid_points SET points = 0 WHERE id = {res_id}")
                    resu = db.select(f"SELECT nickname, points FROM #___raid_points WHERE id = {self.points_to(nickname)}")
                    if not resu:
                        db.query(
                            "INSERT INTO #___raid_points (id, nickname, points, raiding) VALUES "
                            f"({self.points_to(nickname)}, '{self.points_to_name(nickname)}', {points}, 0)"
                        )
                    else:
                        db.query(
                            f"UPDATE #___raid_points SET points = {points + resu[0][1]} "
                            f"WHERE id = {self.points_to(nickname)}"
                        )

        if check:
            self.bot.send_tell(name, add)
        else:
            self.bot.send_tell(name, f"Points going to the main character's account is now ##highlight##{txt}##end##.{add}")

    def check_alts(self, main):
        main = self.bot.core("tools").sanitize_player(main)
        if not self.bot.core("settings").get("Points", "To_main"):
            return
        db = self.bot.db
        alts = self.bot.core("alts").get_alts(main) or []
        for alt in alts:
            result = db.select(
                f"SELECT id, nickname, points FROM #___raid_points WHERE points != 0 AND id = {self.points_to(alt, False)}"
            )
            if result:
                res_id, nickname, points = result[0]
                if res_id != self.points_to(nickname):
                    resu = db.select(f"SELECT nickname, points FROM #___raid_points WHERE id = {self.points_to(nickname)}")
                    if not resu:
                        db.query(
                            "INSERT INTO #___raid_points (id, nickname, points, raiding) VALUES "
                            f"({self.points_to(nickname)}, '{self.points_to_name(nickname)}', {points}, 0)"
                        )
                    else:
                        db.query(
                            f"UPDATE #___raid_points SET points = {points + resu[0][1]} "
                            f"WHERE id = {self.points_to(nickname)}"
                        )
                    db.query(f"UPDATE #___raid_points SET points = 0 WHERE id = {res_id}")
            result = db.select(f"SELECT id FROM #___raid_points WHERE raiding = 1 AND id = {self.points_to(alt, False)}")
            if result:
                db.query(f"UPDATE #___raid_points SET raiding = 0 WHERE id = {result[0][0]}")
                db.query(f"UPDATE #___raid_points SET raiding = 1 WHERE id = {self.points_to(alt)}")

    def transfer_points(self, name, toggle):
        if not self.bot.core("security").check_access(name, "superadmin"):
            self.bot.send_tell(name, "You must be a superadmin to do this")
            return
        stat = toggle.lower() == "on"
        txt = "enabled" if stat else "disabled"
        self.bot.core("settings").save("Points", "Transfer", stat)
        self.bot.send_tell(name, f"Transfering points has been ##highlight##{txt}##end##.")

    def give_points(self, name, who, num):
        who = self.bot.core("tools").sanitize_player(who)
        if not self.bot.core("settings").get("Points", "Transfer"):
            self.bot.send_tell(name, "Transfering points has been ##highlight##disabled##end##.")
            return
        if not _is_numeric(num):
            self.bot.send_tell(name, f"{num} is not a valid points value.")
            return
        num = float(num)
        result = self.bot.db.select(f"SELECT points FROM #___raid_points WHERE id = {self.points_to(name)}")
        if self.bot.core("settings").get("Points", "To_Main"):
            main = self.points_to_name(who)
            is_self = name == main
            alts = self.bot.core("alts").get_alts(main) or []
            if any(name == alt for alt in alts):
                is_self = True
            if is_self:
                self.bot.send_tell(name, "No use to send points to yourself!")
                return
        if not result:
            self.bot.send_tell(name, "You have no points.")
            return
        if num > result[0][0]:
            self.bot.send_tell(name, "You don't have that much points.")
            return
        if isinstance(self.bot.core("player").id(who), BotError):
            self.bot.send_tell(name, f"Player ##highlight##{who}##end## does not exist.")
            return
        db = self.bot.db
        db.query(f"UPDATE #___raid_points SET points = points - {num} WHERE id = {self.points_to(name)}")
        db.query(
            "INSERT INTO #___raid_points (id, nickname, points) VALUES "
            f"({self.points_to(who)}, '{self.points_to_name(who)}', {num}) "
            "ON DUPLICATE KEY UPDATE points = points + VALUES(points)"
        )
        self.bot.send_tell(name, f"You gave ##highlight##{num}##end## raidpoints to ##highlight##{who}##end##.")
        self.bot.send_tell(who, f"You got ##highlight##{num}##end## raidpoints from ##highlight##{name}##end##.")

    def add_points(self, name, who, num, why, silent: bool = False):
        who = self.bot.core("tools").sanitize_player(who)
        if not _is_numeric(num):
            self.bot.send_tell(name, f"{num} is not a valid points value.")
            return False
        if isinstance(self.bot.core("player").id(who), BotError):
            self.bot.send_tell(name, f"Player ##highlight##{who}##end## does not exist.")
            return False
        num = float(num)
        self.bot.db.query(
            "INSERT INTO #___raid_points (id, nickname, points) VALUES "
            f"({self.points_to(who)}, '{self.points_to_name(who)}', {num}) "
            "ON DUPLICATE KEY UPDATE points = points + VALUES(points)"
        )
        if not silent:
            self.bot.send_output(
                "",
                f"##highlight##{name}##end## added ##highlight##{num}##end## raidpoints to ##highlight##{who}##end##'s account.",
                "both",
            )
            self.bot.send_tell(name, f"You added ##highlight##{num}##end## raidpoints to ##highlight##{who}##end##'s account.")
            self.bot.send_tell(who, f"##highlight##{name}##end## added ##highlight##{num}##end## raidpoints to your account.({why})")
        self.log(name, who, num, why)
        return True

    def rem_points(self, name, who, num, why, silent: bool = False):
        who = self.bot.core("tools").sanitize_player(who)
        if not _is_numeric(num):
            self.bot.send_tell(name, f"{num} is not a valid points value.")
            return False
        if isinstance(self.bot.core("player").id(who), BotError):
            self.bot.send_tell(name, f"Player ##highlight##{who}##end## does not exist.")
            return False
        num = float(num)
        self.bot.db.query(f"UPDATE #___raid_points SET points = points - {num} WHERE id = {self.points_to(who)}")
        if not silent:
            self.bot.send_output(
                "",
                f"##highlight##{name}##end## removed ##highlight##{num}##end## raidpoints from ##highlight##{who}##end##'s account.",
                "both",
            )
            self.bot.send_tell(name, f"You removed ##highlight##{num}##end## raidpoints from ##highlight##{who}##end##'s account.")
            self.bot.send_tell(who, f"##highlight##{name}##end## removed ##highlight##{num}##end## raidpoints from your account. ({why})")
        self.log(name, who, -num, why)
        return True

    def points_to(self, name, tomain: bool = True):
        name = self.bot.core("tools").sanitize_player(name)
        if not tomain or not self.bot.core("settings").get("Points", "To_main"):
            return self.bot.core("player").id(name)
        main = self.bot.core("alts").main(name)
        return self.bot.core("player").id(main)

    def points_to_name(self, name, tomain: bool = True):
        name = self.bot.core("tools").sanitize_player(name)
        if not tomain or not self.bot.core("settings").get("Points", "To_main"):
            return name
        return self.bot.core("alts").main(name)

    def log(self, name, who, num, why):
        name = self.bot.core("tools").sanitize_player(name)
        who = self.bot.core("tools").sanitize_player(who)
        db = self.bot.db
        db.query(
            "INSERT INTO #___raid_points_log (name, points, by_who, time, why) VALUES "
            f"('{who}', {num}, '{name}', {int(time.time())}, '{db.real_escape_string(why)}')"
        )

    def view_log(self, name, timeorname, time2):
        if not timeorname:
            timeorname = name
        own_logs = False
        main = None
        alts = []
        if not _is_numeric(timeorname):
            main = self.bot.core("alts").main(timeorname)
            alts = self.bot.core("alts").get_alts(main) or []
            if main.lower() == name.lower():
                own_logs = True
            elif any(alt.lower() == name.lower() for alt in alts):
                own_logs = True

        if not (own_logs or self.bot.core("security").check_access(name, "superadmin")):
            return "You must be an ##highlight##superadmin##end## to view others point logs"

        if _is_numeric(timeorname):
            return "point logs view by time disabled"

        field = "name"
        value = f"= '{main}'"
        for alt in alts:
            value += f" OR {field} = '{alt}'"
        for_whom = f"{main} and his alts"

        logs = self.bot.db.select(
            f"SELECT name, points, by_who, time, why FROM #___raid_points_log WHERE {field} {value} ORDER BY time DESC, id"
        )
        if not logs:
            return f"No logs Found for {for_whom}"
        inside = f" :: Logs for {for_whom} ::##seablue##"
        for log_name, points, by_who, ts, why in logs:
            color = "green" if points >= 0 else "red"
            stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts))
            inside += f"\n\n{stamp} GMT"
            inside += f"\n##highlight##{log_name}##end##: ##{color}##{points}##end## points by ##highlight##{by_who}##end## ({why})"
        return f"Logs for {for_whom} :: " + self.bot.core("tools").make_blob("click to view", inside)


def _is_numeric(value) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False
