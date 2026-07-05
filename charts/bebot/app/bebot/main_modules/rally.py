"""Ported (reduced) from Modules/Rally.php.

Cut vs. the PHP original:
  * `table_update()` -- a one-time data patch that INSERTs 17 extra rows
    into `#___land_control_zones` (Jobe Research, Nascense.../Elysium/
    Scheol/Adonis/Penumbra zones) when that table is found with exactly
    263 rows -- is dropped entirely. It exists purely to backfill zone data
    for Modules/Ao/LandControlZones.php, which isn't ported anywhere in
    this codebase (`grep -rl land_control_zones` over the ported
    main_modules turns up nothing), so there is no `#___land_control_zones`
    table for it to patch.
  * The zone-name/zone-id lookups in `set_rally()` (`SELECT area FROM
    #___land_control_zones WHERE zoneid = ...` / `SELECT zoneid FROM
    #___land_control_zones WHERE area = ... OR short = ...`) are ported
    as-is rather than dropped, since they degrade gracefully: with no
    `#___land_control_zones` table populated (same un-ported
    LandControlZones.php as above), the lookup simply finds nothing and
    `zonenum` stays `False`, exactly like the PHP behaves today on any
    non-AO-tower install. This means the "Set Waypoint" clickable link in
    `get_rally()` will not appear unless a `#___land_control_zones` table
    happens to be populated by something else, matching upstream's
    behaviour when that companion module isn't loaded.
"""
from __future__ import annotations

import re

from ..commodities.base import BaseActiveModule


def _is_numeric(value: str) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


class Rally(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.rallyinfo = False

        self.register_module("rally")
        self.register_command("all", "rally", "MEMBER")

        self.help["description"] = "Sets a rallying point for the raid."
        self.help["command"] = {
            "rally": "Shows the current rally point.",
            "rally <playfield> <x-coord> <y-coord> <notes>": (
                "Sets a rally point in playfield <playfield> at <x-coord> X <y-coord>, "
                "<notes> is optional"
            ),
            "rally clear": "Clear the rally point.",
            "rally save <name>": "save current rally point as <name>.",
            "rally list": "List Saved rally points.",
            "rally load <name>": "Load Saved rally point <name>.",
            "rally del <name>": "Delete saved rally point <name>.",
        }
        self.help["note"] = "<playfield> may also be the last parameter given."

        db = bot.db
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('rally', True)} "
            "(name varchar(50) NOT NULL, rally VARCHAR(200) NOT NULL, PRIMARY KEY (name))"
        )

    # -- dispatch -----------------------------------------------------------------
    def command_handler(self, name, msg, origin):
        parts = msg.split(" ", 1)
        if parts[0].lower() != "rally":
            return f"Error Unknown Command ##highlight##{parts[0]}##end## in Rally Module"
        rest = parts[1] if len(parts) > 1 else ""
        rest = rest.strip()
        sub_parts = rest.split(" ", 1)
        subcommand = sub_parts[0].lower()
        arg = sub_parts[1] if len(sub_parts) > 1 else ""

        if subcommand in ("rem", "del"):
            return self.del_rally(name, arg)
        if subcommand == "clear":
            return self.clear_rally(name)
        if subcommand == "list":
            return self.list_rally(name)
        if subcommand == "load":
            return self.load_rally(name, arg)
        if subcommand == "save":
            return self.save_rally(name, arg)
        if subcommand == "":
            return self.get_rally()

        # "rally set <playfield> <x> <y> <notes>" drops the leading "set";
        # any other unrecognized first word is treated as the start of
        # "<playfield> <x> <y> <notes>" and rejoined whole.
        if subcommand == "set":
            candidate = arg
        else:
            candidate = rest

        match = re.match(r"^([ a-zA-Z0-9]+) ([0-9]+) ([0-9]+)$", candidate, re.I)
        if match:
            return self.set_rally(match.group(1), match.group(2), match.group(3), "")
        match = re.match(r"^([ a-zA-Z0-9]+) ([0-9]+) ([0-9]+) (.*)$", candidate, re.I)
        if match:
            return self.set_rally(match.group(1), match.group(2), match.group(3), match.group(4))
        match = re.match(
            r"^- ([0-9].+), ([0-9].+), ([0-9].+) \(([0-9].+) ([0-9].+) y ([0-9].+) ([0-9]+)\)$",
            candidate,
            re.I,
        )
        if match:
            return self.set_rally(match.group(7), match.group(1), match.group(2), "")
        match = re.match(
            r"^- ([0-9].+), ([0-9].+), ([0-9].+) \(([0-9].+) ([0-9].+) y ([0-9].+) ([0-9]+)\) (.*)$",
            candidate,
            re.I,
        )
        if match:
            return self.set_rally(match.group(7), match.group(1), match.group(2), match.group(8))
        return "To set Rally: <pre>rally &lt;playfield&gt; &lt;x-coord&gt; &lt;y-coord&gt; &lt;notes&gt;"

    # -- rally point management -----------------------------------------------------
    def set_rally(self, zone, x, y, note):
        db = self.bot.db
        e = ""
        if _is_numeric(zone):
            rows = db.select(f"SELECT area FROM #___land_control_zones WHERE zoneid = {zone}")
            if rows:
                zonenum = zone
                zone = rows[0][0]
                e = "and Way"
            else:
                zonenum = False
        else:
            escaped = db.real_escape_string(zone)
            rows = db.select(
                f"SELECT zoneid FROM #___land_control_zones WHERE area = '{escaped}' OR short = '{escaped}'"
            )
            if rows:
                zonenum = rows[0][0]
                e = "and Way"
            else:
                zonenum = False
        self.rallyinfo = [zone, x, y, note, zonenum]
        return f"Rally {e}point has been set."

    def get_rally(self):
        rally = self.rallyinfo
        if not rally:
            return "No rally point has been set."
        result = (
            f"Rally info: [<font color=#ffffff>Zone:</font> <font color=#ffff00>{rally[0]}</font>] "
            f"[<font color=#ffffff>Coords:</font> <font color=#ffff00>{rally[1]}, {rally[2]}</font>] "
            f"[<font color=#ffffff>Note:</font><font color=#ffff00> {rally[3]}</font>]"
        )
        if rally[4]:
            tools = self.bot.core("tools")
            inside = (
                f" :: Rally info::<br><font color=#ffffff>Zone:</font> <font color=#ffff00>{rally[0]}</font><Br>"
                f"<font color=#ffffff>Coords:</font> <font color=#ffff00>{rally[1]}, {rally[2]}</font><br>"
                f"<font color=#ffffff>Note:</font><font color=#ffff00> {rally[3]}</font><br><br>"
                + tools.chatcmd(f"{rally[1]} {rally[2]} {rally[4]}", "Set Waypoint", "waypoint")
            )
            result += " :: " + tools.make_blob("Click for Waypoint", inside)
        return result

    def clear_rally(self, name):
        if self.bot.core("security").check_access(name, "LEADER"):
            self.rallyinfo = False
            return "Rally has been cleared."
        return "You must be a ##highlight##LEADER##end## or higher to clear the rally point."

    def list_rally(self, name):
        if not self.bot.core("security").check_access(name, "LEADER"):
            return "You must be a ##highlight##LEADER##end## or higher to view the saved rally points."
        rows = self.bot.db.select("SELECT name, rally FROM #___rally ORDER BY name")
        if not rows:
            return "No Saved Rally's Found"
        tools = self.bot.core("tools")
        inside = "  :: Saved Rally's :: \n"
        for row in rows:
            inside += (
                f"\n{row[0]} :: " + tools.chatcmd(f"rally load {row[0]}", "LOAD")
                + " :: " + tools.chatcmd(f"rally del {row[0]}", "DELETE")
            )
        return "Saved rally points :: " + tools.make_blob("click to view", inside)

    def save_rally(self, name, msg):
        if not self.bot.core("security").check_access(name, "LEADER"):
            return "You must be a ##highlight##LEADER##end## or higher to save the rally point."
        if not self.rallyinfo:
            return "No rally point has been set."
        if not msg:
            return "Name needed to save rally as"
        db = self.bot.db
        escaped = db.real_escape_string(msg)
        check = db.select(f"SELECT name FROM #___rally WHERE name = '{escaped}'")
        if check:
            return "Name already exists"
        rally = ";".join(str(part) for part in self.rallyinfo)
        rally_escaped = db.real_escape_string(rally)
        db.query(f"INSERT INTO #___rally (name, rally) VALUES ('{escaped}', '{rally_escaped}')")
        return f"Rally has been saved as ##highlight##{msg}##end##."

    def load_rally(self, name, msg):
        if not self.bot.core("security").check_access(name, "LEADER"):
            return "You must be a ##highlight##LEADER##end## or higher to load a rally point."
        if not msg:
            return "Name needed to save rally as"
        db = self.bot.db
        escaped = db.real_escape_string(msg)
        check = db.select(f"SELECT rally FROM #___rally WHERE name = '{escaped}'")
        if not check:
            return "Rally not found"
        self.rallyinfo = check[0][0].split(";", 4)
        return f"Rally ##highlight##{msg}##end## has been loaded."

    def del_rally(self, name, msg):
        if not self.bot.core("security").check_access(name, "LEADER"):
            return "You must be a ##highlight##LEADER##end## or higher to delete saved rally points."
        if not msg:
            return "Name needed to delete saved rally"
        db = self.bot.db
        escaped = db.real_escape_string(msg)
        check = db.select(f"SELECT name FROM #___rally WHERE name = '{escaped}'")
        if not check:
            return "Rally not found"
        db.query(f"DELETE FROM #___rally WHERE name = '{escaped}'")
        return f"Rally ##highlight##{msg}##end## has been deleted."
