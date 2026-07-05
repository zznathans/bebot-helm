"""Ported from Main/15_OnlineDb.php.

Tracks who's online in guild chat ("gc") and the private group ("pg") per
bot, drives reinvite-on-reconnect, and offers the online-state/last-seen
lookups other modules (notably alts.py) render into blobs.

Scope cuts, matching established precedent elsewhere in this port:
  * Schema-version migration (`update_online_table()`'s v1 -> v5 dance --
    dropping `profession`/`ailevel`/`status_irc(_changetime)` columns and
    adding `reinvite`/`level`) is dropped the same way settings.py/
    access_control.py/player_notes.py already do it: the #___online table
    is created directly with the final (v5) schema below instead of
    migrating an older layout forward. There's nothing to migrate for a
    fresh Python port.
  * The IRC bridge (`status_irc` tracking, `register_event("irc", ...)`)
    isn't ported -- see the cut noted in commodities/base.py/bot.py for
    IRC/relay bridges generally; Bot.register_event()'s "irc" branch is
    already a documented no-op.
  * `pgroup_tablename()`/`gc_tablename()`/`full_tablename()` build raw SQL
    FROM-clause fragments joining against `#___whois` (an un-ported table
    -- see main_modules/player.py's docstring on Core/Ao/Whois.php). They
    are ported faithfully as string builders since nothing here executes
    them directly, but any caller that does run one of these queries will
    get no whois-joined columns until that module exists.
  * `logoff()`'s `unset($this->bot->glob["online"][$name])` line referred
    to an ad-hoc PHP `$bot->glob` registry that has no equivalent anywhere
    in this Python port's `Bot` class (see bot.py) -- dropped, the
    #___online table update is the part that matters.
  * `core("notify").check(name)` in `buddy()` is ported as a faithful,
    unguarded cross-module call. Main/15_Notify.php is being ported by a
    different engineer in parallel and isn't wired in yet, so until it
    lands this resolves via Bot.core()'s DummyModule fallback (which logs
    and returns an error string -- truthy, so buddy() will currently
    proceed as if notify.check() always passes; this mirrors how any
    not-yet-ported dependency behaves through that fallback and isn't
    specific to this module).
  * "Last seen" timestamps are stored/returned as raw unix timestamps
    (ints), not gmdate()-formatted strings -- rendering is the caller's
    job (see main_modules/alts.py's make_info_blob()).

Cross-module interface with main_modules/alts.py (the two are circularly
dependent in the PHP original, hence porting them together):
  * Online calls `bot.core("alts").main(name) -> str` and
    `bot.core("alts").get_alts(main) -> list[str]` from get_last_seen()
    when `checkalts=True`.
  * Alts calls `bot.core("online").get_online_state(alt) -> dict` and
    `bot.core("online").get_last_seen(alt) -> int | False` from its
    make_info_blob().
"""
from __future__ import annotations

import time

from ..commodities.base import BasePassiveModule, BotError


def _norm(name) -> str:
    """PHP's `ucfirst(strtolower($x))` -- Python's str.capitalize() matches exactly."""
    return str(name).capitalize()


class Online(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        db = bot.db
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('online', False)} "
            "(nickname VARCHAR(25) NOT NULL, "
            "botname VARCHAR(25) NOT NULL, "
            "status_gc INT(1) DEFAULT '0', "
            "status_gc_changetime INT(11) DEFAULT '0', "
            "status_pg INT(1) DEFAULT '0', "
            "status_pg_changetime INT(11) DEFAULT '0', "
            "reinvite INT(1) DEFAULT '0', "
            "level INT(1) DEFAULT '0', "
            "PRIMARY KEY (nickname, botname))"
        )
        self.register_module("online")
        self.register_event("pgjoin")
        self.register_event("pgleave")
        self.register_event("buddy")
        self.register_event("connect")
        self.register_event("disconnect")
        self.register_event("privgroup")
        self.register_event("gmsg", "org")

        chan = "both" if self.bot.guildbot else "pgroup"
        settings = self.bot.core("settings")
        settings.create(
            "Online", "Channel", chan,
            "For which channels should the online status be shown? In pure raidbots Guild channel means "
            "display online status for all buddies.",
            "both;pgroup;guild",
        )
        settings.create(
            "Online", "OtherBots", "",
            "Which other bots should be included in the online listings? This has to be a comma-seperated list.",
        )
        settings.create(
            "Reinvite", "Enabled", True,
            "Should reinviting of users in the chat group after a restart be on or off?",
        )
        settings.create(
            "Reinvite", "Silent", True,
            "Should the reinvite be silent without any output, or not? On means silent, Off means notifies are sent.",
        )
        if self.bot.guildbot:
            reinvnot = f"You are reinvited to the guest channel of {self.bot.guildname}!"
        else:
            reinvnot = f"You are reinvited to {self.bot.botname}!"
        settings.create("Reinvite", "Notify", reinvnot, "The notify sent on reinvites of silent is disabled.")

        self.last_seen: dict[str, int] = {}
        self.guest_cache: dict[str, str] = {}
        self.org_cache: dict[str, str] = {}
        rows = db.select("SELECT nickname, last_seen FROM #___users WHERE last_seen > 0") or []
        for nickname, last_seen in rows:
            self.last_seen[_norm(nickname)] = last_seen

    # -- events -----------------------------------------------------------------
    def gmsg(self, name, group, msg) -> None:
        if not self.in_org(name):
            self.buddy(name, 1)

    def privgroup(self, name, msg) -> None:
        if not self.in_chat(name):
            self.pgjoin(name)

    def pgjoin(self, name) -> None:
        self.status_change(name, "pg", 1)
        self.guest_cache[_norm(name)] = _norm(name)
        # Mark name for reinvite to chat group (UPDATE works as status_change() creates any needed entries).
        self.bot.db.query(
            f"UPDATE #___online SET reinvite = '1' WHERE nickname = '{name}' AND botname = '{self.bot.botname}'"
        )

    def pgleave(self, name) -> None:
        self.status_change(name, "pg", 0)
        self.guest_cache.pop(_norm(name), None)
        self.bot.db.query(
            f"UPDATE #___online SET reinvite = '0' WHERE nickname = '{name}' AND botname = '{self.bot.botname}'"
        )

    def buddy(self, name, msg) -> None:
        if msg in (0, 1):
            if self.bot.core("notify").check(name):
                if name not in self.bot.other_bots:
                    if msg == 1:
                        self.status_change(name, "gc", 1)
                        self.org_cache[_norm(name)] = _norm(name)
                    else:
                        self.status_change(name, "gc", 0)
                        self.org_cache.pop(_norm(name), None)

    def connect(self) -> None:
        self.everyone_offline()
        inpg = self.bot.db.select(
            f"SELECT nickname FROM #___online WHERE botname = '{self.bot.botname}' AND reinvite = '1'"
        ) or []
        # Unset all reinvite flags for users not yet in pgroup (safety, some users may be faster than this function).
        self.bot.db.query(
            f"UPDATE #___online SET reinvite = '0' WHERE botname = '{self.bot.botname}' AND status_pg = '0'"
        )
        settings = self.bot.core("settings")
        if inpg and settings.get("Reinvite", "Enabled"):
            for row in inpg:
                nickname = row[0]
                # No online checks here: invites to offline characters are ignored by the chatserver anyway.
                self.bot.core("chat").pgroup_invite(nickname)
                if not settings.get("Reinvite", "Silent"):
                    self.bot.send_tell(nickname, settings.get("Reinvite", "Notify"))

    def disconnect(self) -> None:
        self.everyone_offline()

    # -- custom functions ---------------------------------------------------------
    def status_change(self, name, where: str, newstatus: int) -> bool:
        name = _norm(name)
        where = where.lower()
        if where == "gc":
            column = "status_gc"
        elif where == "pg":
            column = "status_pg"
        else:
            return False
        db = self.bot.db
        rows = db.select(f"SELECT user_level FROM #___users WHERE nickname = '{name}'") or []
        level = rows[0][0] if rows else 0
        now = int(time.time())
        sql = (
            f"INSERT INTO #___online (nickname, botname, {column}, {column}_changetime, level) "
            f"VALUES ('{name}', '{self.bot.botname}', '{newstatus}', '{now}', {level}) "
            f"ON DUPLICATE KEY UPDATE {column} = '{newstatus}', {column}_changetime = '{now}', level = {level}"
        )
        db.query(sql)
        # Update last seen field -- doesn't matter if logon or logoff, this is the last time we saw any change.
        db.query(f"UPDATE #___users SET last_seen = {now} WHERE nickname = '{name}'")
        self.last_seen[name] = now
        return True

    def everyone_offline(self) -> None:
        self.bot.db.query(
            f"UPDATE #___online SET status_gc = '0', status_pg = '0' WHERE botname = '{self.bot.botname}'"
        )

    def logoff(self, name) -> None:
        name = _norm(name)
        self.bot.db.query(
            f"UPDATE #___online SET status_gc = '0' WHERE nickname = '{name}' AND botname = '{self.bot.botname}'"
        )

    def pgroup_tablename(self) -> str:
        return (
            " #___online AS t1 LEFT JOIN #___whois AS t2 ON t1.nickname = t2.nickname AND t1.botname = "
            f"'{self.bot.botname}' AND t1.status_pg = 1 "
        )

    def gc_tablename(self) -> str:
        return (
            " #___online AS t1 LEFT JOIN #___whois AS t2 ON t1.nickname = t2.nickname AND t1.botname = "
            f"'{self.bot.botname}' AND t1.status_gc = 1 "
        )

    def full_tablename(self) -> str:
        return (
            " #___online AS t1 LEFT JOIN #___whois AS t2 ON t1.nickname = t2.nickname AND "
            f"{self.otherbots('t1.')} AND {self.channels('t1.')} "
        )

    def get_last_seen(self, name, checkalts: bool = False):
        if checkalts:
            main = self.bot.core("alts").main(name)
            alts = self.bot.core("alts").get_alts(main)
            lastseen = None
            if _norm(main) in self.last_seen:
                lastseen = (self.last_seen[_norm(main)], main)
            for alt in alts or []:
                seen = self.last_seen.get(_norm(alt))
                if seen is not None and (lastseen is None or seen > lastseen[0]):
                    lastseen = (seen, alt)
            return lastseen if lastseen is not None else False
        return self.last_seen.get(_norm(name), False)

    def get_online_state(self, name) -> dict:
        """Check if `name` is currently online.

        Returns a dict with a colorized text blurb in ['content'] and an
        integer in ['status']: -1 unknown/not tracked, 0 offline, 1 online.
        """
        chat = self.bot.core("chat")
        if not chat.buddy_exists(name):
            return {"content": "##white##Unknown##end##", "status": -1}
        if chat.buddy_online(name):
            return {"content": "##green##Online##end##", "status": 1}
        return {"content": "##red##Offline##end##", "status": 0}

    def in_chat(self, name) -> bool:
        """Checks if `name` is in the bot's private group."""
        return _norm(name) in self.guest_cache

    def in_org(self, name) -> bool:
        """Checks if `name` is in the bot's org/guild channel."""
        return _norm(name) in self.org_cache

    def otherbots(self, prefix: str = "") -> str:
        settings = self.bot.core("settings")
        other = settings.get("Online", "OtherBots")
        if other:
            botnames = []
            for raw in str(other).split(","):
                candidate = raw.strip()
                pid = self.bot.core("player").id(candidate)
                if pid and not isinstance(pid, BotError):
                    botnames.append(f"{prefix}botname = '{candidate}'")
            botnames.append(f"{prefix}botname = '{self.bot.botname}'")
            return "(" + " OR ".join(botnames) + ")"
        return f"{prefix}botname = '{self.bot.botname}'"

    def channels(self, prefix: str = "") -> str:
        channel = str(self.bot.core("settings").get("Online", "Channel")).lower()
        if channel == "guild":
            return f"{prefix}status_gc = 1"
        if channel == "pgroup":
            return f"{prefix}status_pg = 1"
        return f"({prefix}status_gc = 1 OR {prefix}status_pg = 1)"

    def list_users(self, channel: str, botlist: str = ""):
        """Returns a list of nicknames currently online in `channel`.

        Valid channels: gc/guild, pg/pgroup/private, both/any/all, online.
        """
        channel = channel.lower()
        table = "online"
        if botlist:
            bots = [b.strip() for b in botlist.split(",")]
            botpart = "AND (" + " OR ".join(f"botname='{_norm(b)}'" for b in bots) + ") "
        else:
            botpart = f"AND botname = '{self.bot.botname}' "
        if channel in ("gc", "guild"):
            where_clause = "status_gc = 1"
        elif channel in ("pg", "pgroup", "private"):
            where_clause = "status_pg = 1"
        elif channel in ("both", "any", "all"):
            where_clause = "status_gc = 1 OR status_pg = 1"
        elif channel == "online":
            where_clause = "user_level = 2 AND notify = 1"
            table = "users"
            botpart = ""
        else:
            self.error.set(f"Unknown channel '{channel}' in online->list()")
            return self.error
        query = f"SELECT nickname FROM #___{table} WHERE ({where_clause}) {botpart}ORDER BY nickname"
        users = self.bot.db.select(query, True) or []
        if not users:
            self.error.set(f"No users found in {channel}")
            return self.error
        return [user["nickname"] for user in users]
