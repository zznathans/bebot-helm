"""Ported from Modules/BansManagerUi.php (class `BanManager`).

Chat-command UI for banning/unbanning characters and browsing the ban
list/history, built on top of already-ported Core modules:
`core("security")` (the actual ban bookkeeping -- `set_ban()`/`rem_ban()`),
`core("player")` (name validation via `id()`), `core("tools")`
(`sanitize_player()`/`chatcmd()`/`make_blob()`), `core("colors")`
(`colorize()`), `core("online")` (`in_chat()`), `core("chat")`
(`pgroup_kick()`), `core("settings")` (the `Ban/*` settings), and
`core("autouseradd")` (already ported at main_modules/auto_user_add.py --
this module only flips its `checked` dict entry via `bot.core("autouseradd")`,
it does not reimplement any of that module's logic).

Scope notes / intentional deviations from the PHP:
  * `core("security").set_ban()`/`rem_ban()` were ported with narrower
    signatures than the PHP originals: `set_ban(admin, target, reason,
    endtime)` (4 args -- the PHP call passes `$source` twice,
    `set_ban($source, $user, $source, $reason, $endtime)`; the duplicate
    3rd arg has nowhere to go in the ported method, so it's dropped here)
    and `rem_ban(admin, target)` (2 args -- the PHP call's 3rd `$reason`
    argument, e.g. `rem_ban($source, $user, $source)` or
    `rem_ban("Cron", $unban[0], "Temporary ban ran out,")`, is likewise
    dropped since the ported `rem_ban()` doesn't persist an unban reason
    anywhere).
  * `ban_history()`/`show_ban_list()` in the PHP reference a `$link`
    variable in their Back/Next `chatcmd()` calls that is never assigned
    anywhere in either function's scope (it's only ever assigned inside
    `ban_search()`) -- a latent PHP bug that silently resolves to an empty
    string. This port reproduces the actual runtime behavior (no link
    suffix on those two Back/Next buttons) rather than the apparent intent.
  * The "MoreBots" relay fan-out in `add_ban()`/`del_ban()` drops the PHP's
    `usleep(500000)` pacing delay between each relayed `send_tell()`. That
    was a blocking half-second sleep tolerable in single-threaded PHP; this
    port runs on asyncio, where a blocking `time.sleep()` in a command
    handler would stall the whole bot's event loop for every configured
    extra bot. The fan-out itself (resolving each configured bot and
    relaying the ban/unban command) is ported faithfully; only the sleep is
    cut. `Bot.send_tell()`'s existing `chat_queue`/`low`-priority mechanism
    is the anti-flood path in this port instead.
  * Timestamps (`banned_at`/`banned_until`) are rendered with a fixed UTC
    "%Y-%m-%d %H:%M:%S" format instead of `gmdate($this->bot->core("settings")
    ->get("Time", "FormatString"), ...)`, matching the precedent already set
    in main_modules/alts.py's `make_info_blob()` and main_modules/afk.py's
    `msgs()`: nothing in this port consumes the `Time/FormatString` setting
    yet (see main_modules/time.py's docstring).
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone

from ..commodities.base import BaseActiveModule, BotError

_PAGER = 20

_TIME_UNITS = {
    "h": 60 * 60,
    "d": 60 * 60 * 24,
    "w": 60 * 60 * 24 * 7,
    "m": 60 * 60 * 24 * 30,
    "y": 60 * 60 * 24 * 365,
}


def _fmt(ts) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _as_skip(value) -> int:
    """PHP: `if ($skip == '' || !is_numeric($skip)) { $skip = 0; }`."""
    if value is None or value == "" or not str(value).isdigit():
        return 0
    return int(value)


class BansManagerUi(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("bansmanagerui")
        self.register_command(
            "all", "ban", "GUEST",
            {"history": "LEADER", "search": "LEADER", "add": "ADMIN", "del": "ADMIN"},
        )
        self.help["description"] = "Handling the bans for <botname>."
        banlist_help = "Shows the list of all currently banned characters."
        self.help["command"] = {
            "banlist": banlist_help,
            "ban": banlist_help,
            "ban list": banlist_help,
            "ban history": "Shows previously banned toons last issues with details.",
            "ban search": "Searches among currently + previously banned toons.",
            "ban add <name> <reason>": (
                "Bans <name> for <reason> from the bot forever - or until manually unbanned."
            ),
            "ban add <name> <time> <reason>": (
                "Bans <name> for <reason> from the bot for <time>. <time> has a base unit of "
                "minutes. Add 'h' for hours, 'd' for days, 'w' for weeks, 'm' for monthes, 'y' for "
                "years directly behind the number to change the time unit. '6h' as time would ban "
                "the character for 6h, after which the ban will be automatically deleted. The bot "
                "checks every 5 minutes for bans that have run out."
            ),
            "ban del <name>": "Unbans <name>.",
            "ban rem <name>": "Unbans <name>.",
        }
        self.register_alias("ban list", "banlist")
        self.register_alias("ban history", "banhistory")
        self.register_alias("ban search", "bansearch")
        self.register_alias("ban", "blacklist")
        self.register_event("cron", "5min")
        self.bot.core("settings").create("Ban", "ReqReason", False, "is a Reason Required?")
        self.bot.core("settings").create(
            "Ban", "MoreBots", "",
            "Anymore bots (where main bot is ADMIN) that should reflect same ban table? "
            "This has to be a comma-separated list.",
        )

    # -- cron ------------------------------------------------------------------
    def cron(self, duration=None) -> None:
        now = int(time.time())
        unbans = self.bot.db.select(
            f"SELECT nickname FROM #___users WHERE user_level = -1 AND banned_until > 0 AND banned_until <= {now}"
        ) or []
        for row in unbans:
            nickname = row[0]
            self.bot.core("security").rem_ban("Cron", nickname)
            self.auto_user_readd(nickname)

    # -- dispatch ----------------------------------------------------------------
    def command_handler(self, name, msg, origin):
        info = re.match(r"^ban (\d+)$", msg, re.I) or re.match(r"^ban list (\d+)$", msg, re.I)
        if info:
            return self.show_ban_list(info.group(1))
        if re.match(r"^ban$", msg, re.I) or re.match(r"^ban list$", msg, re.I):
            return self.show_ban_list(0)
        info = re.match(r"^ban history (\d+)$", msg, re.I)
        if info:
            return self.ban_history(info.group(1))
        if re.match(r"^ban history$", msg, re.I):
            return self.ban_history(0)
        info = re.match(r"^ban search (\d+) (.+)$", msg, re.I)
        if info:
            return self.ban_search(info.group(1), info.group(2))
        info = re.match(r"^ban search (.+)$", msg, re.I)
        if info:
            return self.ban_search(0, info.group(1))
        info = re.match(r"^ban add ([a-z0-9-]+) ([0-9]+[hdwmy]?)$", msg, re.I)
        if info:
            return self.add_ban(name, info.group(1), info.group(2), "")
        info = re.match(r"^ban add ([a-z0-9-]+)$", msg, re.I)
        if info:
            return self.add_ban(name, info.group(1), "0", "")
        info = re.match(r"^ban add ([a-z0-9-]+) ([0-9]+[hdwmy]?) (.+)$", msg, re.I)
        if info:
            return self.add_ban(name, info.group(1), info.group(2), info.group(3))
        info = re.match(r"^ban add ([a-z0-9-]+) (.+)$", msg, re.I)
        if info:
            return self.add_ban(name, info.group(1), "0", info.group(2))
        info = re.match(r"^ban del ([a-z0-9-]+)$", msg, re.I)
        if info:
            return self.del_ban(name, info.group(1))
        info = re.match(r"^ban rem ([a-z0-9-]+)$", msg, re.I)
        if info:
            return self.del_ban(name, info.group(1))
        return self.bot.send_help(name, "ban")

    # -- listing / search / history -----------------------------------------------
    def _render_ban(self, ban, with_unban_link: bool) -> str:
        tools = self.bot.core("tools")
        colors = self.bot.core("colors")
        nickname, banned_by, banned_at, banned_for, banned_until = ban
        blob = "\n" + nickname + " " + tools.chatcmd("whois " + nickname, "[WHOIS]")
        if with_unban_link:
            blob += " " + tools.chatcmd("ban del " + nickname, "[UNBAN]")
        blob += "\n"
        blob += colors.colorize("blob_text", "Banned by: ") + (banned_by or "") + "\n"
        blob += colors.colorize("blob_text", "Banned at: ") + _fmt(banned_at) + "\n"
        blob += colors.colorize("blob_text", "Reason: ") + (banned_for or "") + "\n"
        if banned_until and banned_until > 0:
            blob += colors.colorize(
                "blob_text", f"Temporary ban until {_fmt(banned_until)}.\n"
            )
        else:
            blob += colors.colorize("blob_text", "Permanent ban.\n")
        return blob

    def ban_search(self, skip=0, string: str | None = None):
        skip = _as_skip(skip)
        pager = _PAGER
        range_ = skip + pager
        link = ""
        if string:
            kword = string
            link = " " + kword
            escaped = self.bot.db.real_escape_string(kword) if hasattr(self.bot.db, "real_escape_string") else kword
            where = (
                " WHERE banned_until IS NOT NULL AND banned_at IS NOT NULL AND "
                f"(banned_by LIKE '%{escaped}%' OR banned_for LIKE '%{escaped}%' OR nickname LIKE '%{escaped}%')"
            )
        else:
            where = " WHERE banned_by IS NOT NULL AND banned_for IS NOT NULL"
        total_row = self.bot.db.select("SELECT COUNT(*) FROM #___users" + where)
        total = total_row[0][0] if total_row else 0
        if range_ > total:
            range_ = total
        banned = self.bot.db.select(
            "SELECT nickname, banned_by, banned_at, banned_for, banned_until FROM #___users"
            + where + f" ORDER BY banned_at DESC LIMIT {skip}, {pager}"
        )
        if not banned:
            return "Nobody found banned!"
        banlist = f"##blob_title## ::: Searched banned characters for {self.bot.botname} :::##end##\n"
        for ban in banned:
            banlist += self._render_ban(ban, with_unban_link=False)
        tools = self.bot.core("tools")
        back = skip - pager
        if back >= 0:
            banlist += " " + tools.chatcmd("bansearch " + str(back) + link, "Back") + " "
        if range_ < total:
            banlist += " " + tools.chatcmd("bansearch " + str(range_) + link, "Next") + " "
        first = skip + 1
        return (
            f"##highlight##{first}-{range_} / {total}##end## Characters searched as Banned ::: "
            + tools.make_blob("click to view", banlist)
        )

    def ban_history(self, skip=0):
        skip = _as_skip(skip)
        pager = _PAGER
        range_ = skip + pager
        now = int(time.time())
        total_row = self.bot.db.select(
            f"SELECT COUNT(*) FROM #___users WHERE banned_until < {now} "
            "AND banned_until IS NOT NULL AND banned_at IS NOT NULL"
        )
        total = total_row[0][0] if total_row else 0
        if range_ > total:
            range_ = total
        banned = self.bot.db.select(
            f"SELECT nickname, banned_by, banned_at, banned_for, banned_until FROM #___users WHERE banned_until < {now} "
            f"AND banned_until IS NOT NULL AND banned_at IS NOT NULL ORDER BY banned_at DESC LIMIT {skip}, {pager}"
        )
        if not banned:
            return "Nobody was banned!"
        banlist = f"##blob_title## ::: All previously banned characters for {self.bot.botname} :::##end##\n"
        for ban in banned:
            banlist += self._render_ban(ban, with_unban_link=False)
        tools = self.bot.core("tools")
        back = skip - pager
        if back >= 0:
            banlist += " " + tools.chatcmd("banhistory " + str(back), "Back") + " "
        if range_ < total:
            banlist += " " + tools.chatcmd("banhistory " + str(range_), "Next") + " "
        first = skip + 1
        return (
            f"##highlight##{first}-{range_} / {total}##end## Characters previously Banned ::: "
            + tools.make_blob("click to view", banlist)
        )

    def show_ban_list(self, skip=0):
        skip = _as_skip(skip)
        pager = _PAGER
        range_ = skip + pager
        total_row = self.bot.db.select("SELECT COUNT(*) FROM #___users WHERE user_level = -1")
        total = total_row[0][0] if total_row else 0
        if range_ > total:
            range_ = total
        banned = self.bot.db.select(
            "SELECT nickname, banned_by, banned_at, banned_for, banned_until FROM #___users "
            f"WHERE user_level = -1 ORDER BY nickname LIMIT {skip}, {pager}"
        )
        if not banned:
            return "Nobody is banned!"
        banlist = f"##blob_title## ::: All banned characters for {self.bot.botname} :::##end##\n"
        for ban in banned:
            banlist += self._render_ban(ban, with_unban_link=True)
        tools = self.bot.core("tools")
        back = skip - pager
        if back >= 0:
            banlist += " " + tools.chatcmd("banlist " + str(back), "Back") + " "
        if range_ < total:
            banlist += " " + tools.chatcmd("banlist " + str(range_), "Next") + " "
        first = skip + 1
        return (
            f"##highlight##{first}-{range_} / {total}##end## Characters Banned ::: "
            + tools.make_blob("click to view", banlist)
        )

    # -- ban / unban --------------------------------------------------------------
    def _relay_to_morebots(self, command_suffix: str) -> None:
        morebots = self.bot.core("settings").get("Ban", "MoreBots")
        if not morebots:
            return
        player = self.bot.core("player")
        for raw in str(morebots).split(","):
            botname = raw.strip()
            if not botname:
                continue
            idb = player.id(botname)
            botname = botname.lower().capitalize()
            # Faithful port of the PHP `if (!$idb instanceof BotError || $idb != 0)`:
            # a BotError is never loosely-equal to 0, so this condition is always
            # true regardless of whether `botname` actually resolved -- i.e. it
            # never skips a relay in practice, in the original either. Kept as-is
            # (not "fixed") since the brief is a faithful port, not a bugfix.
            if not isinstance(idb, BotError) or idb != 0:
                self.bot.send_tell(botname, "ban " + command_suffix, 1, False)

    def add_ban(self, source, user, duration, reason):
        tools = self.bot.core("tools")
        user = tools.sanitize_player(user)
        uid = self.bot.core("player").id(user)
        if isinstance(uid, BotError) or uid == 0:
            return f"##highlight##{user} ##end##is no valid character name!"
        if reason == "":
            if self.bot.core("settings").get("Ban", "ReqReason"):
                return "Reason Required for adding Bans"
            reason = "None given."
        if duration == "0":
            endtime = 0
        else:
            timesize = 60
            for suffix, size in _TIME_UNITS.items():
                if suffix in duration.lower():
                    timesize = size
                    break
            match = re.match(r"\d+", duration)
            amount = int(match.group(0)) if match else 0
            endtime = int(time.time()) + amount * timesize
        ban = self.bot.core("security").set_ban(source, user, reason, endtime)
        if not isinstance(ban, BotError):
            if self.bot.core("online").in_chat(user):
                self.bot.core("chat").pgroup_kick(user)
        self._relay_to_morebots(f"add {user} {duration} {reason}")
        return ban

    def del_ban(self, source, user):
        tools = self.bot.core("tools")
        user = tools.sanitize_player(user)
        uid = self.bot.core("player").id(user)
        if uid == 0:
            return f"##highlight##{user} ##end##is no valid character name!"
        ban = self.bot.core("security").rem_ban(source, user)
        self.auto_user_readd(user)
        self._relay_to_morebots(f"rem {user}")
        return ban

    def auto_user_readd(self, name) -> None:
        if self.bot.exists_module("autouseradd"):
            self.bot.core("autouseradd").checked[name] = False
