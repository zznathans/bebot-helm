"""Ported from Modules/OnlineCount.php (class `OnlineCounting`).

Chat commands (`count`/`check` and their `all`/`org`/`<profession>`
variants) that summarize who's currently in guild chat / the private
group, broken down by profession or organization, plus `/assist`-blob
generators for raid leaders. Built on the already-ported `core("online")`
(`full_tablename()`/`otherbots()`/`channels()` -- the SQL FROM/WHERE
fragment builders), `core("professions")` (full-name/shortcut lookups),
`core("colors")` (`colorize()`), and `core("tools")` (`chatcmd()`/
`make_blob()`).

Scope notes / intentional deviations from the PHP:
  * The PHP constructor never actually calls `register_module()` on itself
    (only `parent::__construct($bot, get_class($this))`, which just sets
    `$this->module_name` -- see Commodities/00_BasePassiveModule.php's
    constructor). Nothing else in the PHP tree looks this module up via
    `core("onlinecount")`/`core("onlinecounting")` either (grepped the
    whole BeBot source -- no hits outside this file and the changelog).
    This port still calls `self.register_module("onlinecount")` for
    consistency with every other module in this codebase (and so
    `bot.core("onlinecount")` resolves if anything ever wants it), which
    changes nothing observable since there was no prior registration to
    preserve or collide with.
  * Every query here (`get_prof()`, `get_org_members()`, `get_orgs()`,
    `count_all()`) joins against `#___whois` via
    `core("online").full_tablename()`/`pgroup_tablename()` etc. for the
    `profession`/`level`/`org_name`/`defender_rank_id` columns. Core/Ao/
    Whois.php is not ported anywhere in this codebase yet -- see
    main_modules/online.py's own docstring ("any caller that does run one
    of these queries will get no whois-joined columns until that module
    exists") and the same caveat already noted in alts.py, say.py,
    flexible_security.py, user.py, auto_user_add.py. This port is a
    faithful, unguarded translation of the same SQL-building calls; until
    a `whois` module creates `#___whois`, these commands will return "no
    one online"/empty-list results against a real database (in tests, the
    `db.select`/`db.query` stand-ins are monkeypatched directly, so this
    doesn't block testing the surrounding logic).
  * `core("colors")->define_scheme("counting", "text"/"number"/"name",
    ...)` (three custom named color schemes: `counting_text`,
    `counting_number`, `counting_name`) has no equivalent in this port's
    `main_modules/colors.py`, which only ships a small fixed
    `##tagname##` palette (see that module's own docstring: the DB-backed
    scheme/theme system isn't ported). `Colors.colorize()` already
    degrades gracefully for an unknown tag -- it just returns the text
    unchanged -- so the `colorize("counting_text", ...)` /
    `colorize("counting_number", ...)` / `colorize("counting_name", ...)`
    call sites are kept as faithful passthroughs (harmless no-ops today,
    and they'll start rendering colors for free the moment `colors.py`
    grows scheme support).
  * `htmlentities()` is approximated with `html.escape(..., quote=True)`.
    `make_org_assist()` in the PHP calls `get_org_members(htmlentities(
    $orgname))` on an `$orgname` that was *already* `htmlentities()`-escaped
    by every caller (`count_org()`/`check_org()`/`check_org_members()`
    escape once before calling `make_org_assist`, which escapes again
    internally) -- a latent double-escaping quirk, preserved here as-is
    rather than "fixed", since collapsing it would change behavior for
    org names containing `&`/`<`/`>`/quotes.
  * `$this->cp` ("profession" or "class", chosen from `$this->bot->game`)
    is computed once in `__init__` exactly like the PHP, using this
    port's `bot.game` (see main_modules/professions.py's docstring: this
    codebase's `Bot` currently hardcodes `self.game = "Ao"`, so the AoC
    branch -- and this module's `self.cp = "class"` branch -- is
    presently unreachable dead code here just as it is upstream absent an
    AoC-flavored bot).
"""
from __future__ import annotations

import html
import re

from ..commodities.base import BaseActiveModule, BotError


class OnlineCounting(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("onlinecount")
        self.register_command("all", "count", "GUEST")
        self.register_command("all", "check", "GUEST")

        self.cp = "class" if str(self.bot.game).lower() == "aoc" else "profession"

        self.help["description"] = "Lists characters in chat group"
        self.help["command"] = {
            "count all": f"Lists all professions and the number of characters of each {self.cp} in chat",
            "count": f"Lists all professions and the number of characters of each {self.cp} in chat",
            "count [prof]": "Lists all members of [prof] with level and alien level that are in chat.",
            "count org": "Lists the number of characters per organization currently online in chat.",
            "count org [orgname]": "Lists the number of characters online in chat that are in the organization [orgname].",
            "check all": "Offers assist on everybody online in chat.",
            "check": "Offers assist on everybody online in chat.",
            "check [prof]": "Offers assist on all members of [prof] in the chat.",
            "check org": "Offers assist on all characters in chat sorted by their organizations.",
            "check org [orgname]": "Offers assist on all characters online in chat that are in the organization [orgname].",
        }

    # -- dispatch ---------------------------------------------------------------
    def command_handler(self, name, msg, channel):
        if re.match(r"^count$", msg, re.I):
            return self.count_all()
        if re.match(r"^count all$", msg, re.I):
            return self.count_all()
        if re.match(r"^count org$", msg, re.I):
            return self.count_org()
        match = re.match(r"^count org (.*)$", msg, re.I)
        if match:
            return self.count_org_members(match.group(1))
        match = re.match(r"^count (.*)$", msg, re.I)
        if match:
            return self.count(match.group(1))
        if re.match(r"^check$", msg, re.I):
            return self.check_all()
        if re.match(r"^check all$", msg, re.I):
            return self.check_all()
        if re.match(r"^check org$", msg, re.I):
            return self.check_org()
        match = re.match(r"^check org (.*)$", msg, re.I)
        if match:
            return self.check_org_members(match.group(1))
        match = re.match(r"^check (.*)$", msg, re.I)
        if match:
            return self.check(match.group(1))
        return None

    # -- rendering helpers -------------------------------------------------------
    def make_assist(self, assist: list[str], title: str) -> str:
        return f"<a href='chatcmd://{' \\n '.join(assist)}'>{title}</a>"

    # -- queries ------------------------------------------------------------------
    def get_org_members(self, orgname: str):
        aodefrankid = ", t2.defender_rank_id" if str(self.bot.game).lower() == "ao" else ""
        return self.bot.db.select(
            f"SELECT DISTINCT(t1.nickname), t2.level{aodefrankid} FROM {self.bot.core('online').full_tablename()} "
            f"WHERE t2.org_name = '{html.escape(orgname, quote=True)}' ORDER BY t1.nickname ASC"
        )

    def get_prof(self, prof: str):
        profsearch = "!= ''" if prof == "" else f"= '{prof}'"
        aodefrankid = ", t2.defender_rank_id" if str(self.bot.game).lower() == "ao" else ""
        return self.bot.db.select(
            f"SELECT DISTINCT(t1.nickname), t2.level{aodefrankid} FROM {self.bot.core('online').full_tablename()} "
            f"WHERE t2.{self.cp} {profsearch} ORDER BY t1.nickname ASC"
        )

    def get_orgs(self):
        online = self.bot.core("online")
        innersql = (
            "SELECT t2.org_name as org, COUNT(DISTINCT t1.nickname) AS count FROM "
            f"{online.full_tablename()} WHERE t2.org_name != '' GROUP BY t2.org_name ORDER BY count DESC, org_name ASC"
        )
        sql = (
            f"SELECT t1.org AS org, t1.count AS count, SUM(t2.level) / t1.count AS avg_level FROM ({innersql}) AS t1, "
            "#___whois AS t2, #___online AS t3 WHERE t1.org = t2.org_name AND t2.nickname = t3.nickname AND "
            f"{online.otherbots('t3.')} AND {online.channels('t3.')} GROUP BY org ORDER BY t1.count DESC, t1.org ASC"
        )
        return self.bot.db.select(sql, True)

    def make_org_assist(self, orgname: str) -> str:
        # `orgname` is expected pre-escaped by callers -- see module docstring
        # on the faithfully-preserved double-htmlentities() quirk.
        org = self.get_org_members(html.escape(orgname, quote=True))
        if not org:
            return ""
        assist = [f"/assist {mem[0]}" for mem in org]
        return self.make_assist(assist, f"Check {html.escape(orgname, quote=True)}")

    # -- count* -------------------------------------------------------------------
    def count_all(self) -> str:
        professions = self.bot.core("professions")
        profession_list = "'" + professions.get_professions("', '") + "'"
        shortcut_array = dict(zip(professions.get_profession_array(), professions.get_shortcut_array()))
        profession_count = {shortcut: 0 for shortcut in shortcut_array.values()}

        online = self.bot.core("online")
        query = (
            f"SELECT t2.{self.cp} as profession, COUNT(DISTINCT t1.nickname) as count FROM "
            f"{online.full_tablename()} WHERE t2.{self.cp} IN ({profession_list}) GROUP BY {self.cp}"
        )
        online_count = self.bot.db.select(query, True) or []
        total_online = 0
        for profession in online_count:
            shortcut = shortcut_array.get(profession["profession"])
            if shortcut is not None:
                profession_count[shortcut] += profession["count"]
            total_online += profession["count"]

        output = f"Total: ##counting_number##{total_online}##end##"
        for shortcut, count in profession_count.items():
            output += f", {shortcut}: ##counting_number##{count}##end##"
        return self.bot.core("colors").colorize("counting_text", output)

    def count(self, shortcut: str):
        prof = self.bot.core("professions").full_name(shortcut)
        if isinstance(prof, BotError):
            return prof
        online = self.bot.core("online")
        pcount = self.bot.db.select(
            f"SELECT COUNT(DISTINCT t1.nickname) FROM {online.full_tablename()} WHERE t2.{self.cp} = '{prof}'"
        )
        if not pcount or pcount[0][0] == 0:
            return self.bot.core("colors").colorize("counting_text", f"No {prof} in chat!")
        profchars = self.get_prof(prof) or []
        colors = self.bot.core("colors")
        strings = []
        for curchar in profchars:
            helpstr = colors.colorize("counting_name", curchar[0]) + " ["
            helpstr += colors.colorize("counting_number", str(curchar[1])) + "/"
            helpstr += colors.colorize("counting_number", str(curchar[2])) + "]"
            strings.append(helpstr)
        retstr = f"{pcount[0][0]} {prof}s in chat: " + ", ".join(strings)
        return colors.colorize("counting_text", retstr)

    def count_org(self) -> str:
        counts = self.get_orgs() or []
        colors = self.bot.core("colors")
        if not counts:
            return colors.colorize("counting_text", "Nobody online!")
        online = self.bot.core("online")
        tcount = self.bot.db.select(
            f"SELECT count(DISTINCT nickname) as count FROM #___online WHERE {online.otherbots('')} AND "
            f"{online.channels('')}",
            True,
        )
        totalcount = tcount[0]["count"] if tcount else 0
        tools = self.bot.core("tools")
        orgs = []
        for org in counts:
            perc = (100 * org["count"] / totalcount) if totalcount else 0
            org_escaped = org["org"].replace("'", "`")
            orgcmd = tools.chatcmd(f"count org {org_escaped}", org_escaped)
            orgstr = f"{round(perc, 1)}% {orgcmd}: {org['count']} with an average level of {round(org['avg_level'], 1)}"
            orgs.append(orgstr)
        return tools.make_blob(
            "Online organizations",
            "##blob_title##Online organisations:##end##<br><br>" + "<br>".join(orgs),
        )

    def count_org_members(self, orgname: str):
        online = self.bot.core("online")
        orgname_escaped = html.escape(orgname, quote=True)
        pcount = self.bot.db.select(
            f"SELECT COUNT(DISTINCT t1.nickname) FROM {online.full_tablename()} "
            f"WHERE t2.org_name = '{orgname_escaped}'"
        )
        colors = self.bot.core("colors")
        if not pcount or pcount[0][0] == 0:
            return colors.colorize("counting_text", f"No member of {orgname_escaped} in chat!")
        profchars = self.get_org_members(orgname) or []
        strings = []
        for curchar in profchars:
            helpstr = colors.colorize("counting_name", curchar[0]) + " ["
            helpstr += colors.colorize("counting_number", str(curchar[1])) + "/"
            helpstr += colors.colorize("counting_number", str(curchar[2])) + "]"
            strings.append(helpstr)
        retstr = f"{pcount[0][0]} member of {orgname_escaped} in chat: " + ", ".join(strings)
        return colors.colorize("counting_text", retstr)

    # -- check* -------------------------------------------------------------------
    def check_all(self):
        online = self.get_prof("") or []
        if not online:
            return "Nobody online!"
        assist = [f"/assist {mem[0]}" for mem in online]
        return self.bot.core("tools").make_blob("Check all online", self.make_assist(assist, "Check all online"))

    def check(self, shortcut: str):
        prof = self.bot.core("professions").full_name(shortcut)
        if isinstance(prof, BotError):
            return prof
        profchars = self.get_prof(prof) or []
        if not profchars:
            return f"No {prof} in chat!"
        assist = [f"/assist {mem[0]}" for mem in profchars]
        return self.bot.core("tools").make_blob(f"Check {prof}", self.make_assist(assist, f"Check {prof}"))

    def check_org(self):
        orgs = self.get_orgs() or []
        if not orgs:
            return "Nobody online!"
        orgassist = []
        for org in orgs:
            orgblob = self.make_org_assist(html.escape(org["org"], quote=True))
            if orgblob != "":
                orgassist.append(orgblob)
        return self.bot.core("tools").make_blob("Check organizations", "\n".join(orgassist))

    def check_org_members(self, orgname: str):
        blob = self.make_org_assist(html.escape(orgname, quote=True))
        if blob == "":
            return f"Nobody of {html.escape(orgname, quote=True)} online!"
        return self.bot.core("tools").make_blob(f"Check {html.escape(orgname, quote=True)}", blob)
