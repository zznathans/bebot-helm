"""Ported from Modules/UserAdmin.php (class `UserAdmin`).

SUPERADMIN-only chat-command UI for auditing/pruning the bot's member,
buddy, alt, and whois data. Depends only on the already-ported
`core("chat")` (buddy add/remove/exists, char-id <-> name lookups) and
`core("tools")` (`chatcmd`/`make_blob`) modules, plus direct `bot.db`
queries and `bot.aoc.buddies` -- the PHP original's only `core(...)`
dependencies are `chat` and `tools` (verified against the source), so this
port is self-contained: no raid/points/Discord-bridge integration exists in
the original to begin with.

Scope notes / intentional deviations from the PHP:
  * `$this->bot->aoc->buddies` is read directly (an id -> flags dict kept
    live by `AOChat.on_packet()`, see aochat/protocol.py), matching the PHP
    original's direct field access -- there is no `core("chat")` wrapper
    for "give me the whole buddylist" and adding one isn't necessary since
    this is a read of plain data, not a fire-and-forget network action.
  * `#___whois` is queried directly with raw SQL exactly like `online.py`'s
    LEFT JOINs against the same table already do: Core/Ao/Whois.php itself
    isn't ported (see main_modules/alts.py's docstring for the standing
    rationale -- no synchronous blocking-socket equivalent in this asyncio
    port), but the table is still assumed to exist in the bot's database
    from the original PHP schema, so read/delete queries against it are
    kept as faithful call sites.
  * `where_sql()`/`to_db_value()` (the PHP module's generic ad-hoc SQL
    condition-builder, built around `mysql_escape_string`/magic-quotes
    handling that doesn't exist in Python) is dropped in favor of writing
    each concrete query directly, matching the precedent already set by
    admins_ui.py and settings_ui.py of reaching for `bot.db.select/query`
    directly rather than reimplementing a legacy PHP query-builder. Every
    value that ends up in a raw query here is already validated to be
    numeric by the dispatching regex (char ids, day counts) or comes from a
    fixed enum of level names, so there is no free-text user input to
    escape.
  * The local `make_blob()`/`make_cmd()` wrapper methods are collapsed into
    direct calls to `core("tools").make_blob()`/`core("tools").chatcmd()`
    (with a small `_cmd()` helper mirroring `make_cmd()`'s
    title/subcommand/botcmd-override signature) instead of being
    reimplemented locally, matching the same collapse already done in
    admins_ui.py/alts.py.
  * `FROM_UNIXTIME`/`DATE_FORMAT` (MySQL-session-timezone-dependent
    date rendering) is replaced with fixed UTC formatting in Python,
    matching the precedent set in main_modules/alts.py's docstring (no
    `gmdate()`/`Time/FormatString` support exists in this port -- see
    main_modules/time.py).
  * `show_overview()`'s `$this->bot->send_tell($name, ..., $origin, 1)`
    drops the `$origin` argument: the ported `Bot.send_tell()` has no
    such parameter (see bot.py) since the channel-bitmask routing it fed
    was already folded into `output_destination()`/`reply()` elsewhere in
    this port. `origin` is kept as a `command_handler()` parameter for
    interface parity (BaseActiveModule always passes it) but is otherwise
    unused here, the same kind of harmless unused-parameter cut already
    made for `user` in settings_ui.py's `change_setting()`.
  * Two latent PHP quirks are preserved as-is rather than "fixed", per this
    repo's standing precedent for inert-but-harmless upstream oddities
    (see alias.py's and settings_ui.py's docstrings for the same call):
      - `list_users()`'s per-level branch nests the "<b></b>\\n" suffix
        *inside* the `blob_header()` title argument instead of appending it
        afterwards like the other branches do, so it renders inside the
        `<font>` tag rather than after it.
      - `command_handler()`'s regex for `useradmin altlist clear
        (all|obsolete)` accepts `all`, but `clear_alts()` only implements
        the `obsolete` case (its `switch` has no `all` case) -- `useradmin
        altlist clear all` therefore silently returns `False` (no reply),
        exactly as it does in the PHP.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone

from ..commodities.base import BaseActiveModule
from .security import ANONYMOUS, BANNED, GUEST, MEMBER

_LEVEL_DECODE = {
    "all": None,
    "member": MEMBER,
    "guest": GUEST,
    "anonymous": ANONYMOUS,
    "banned": BANNED,
    "obsolete": "obsolete",
}
_LEVEL_ENCODE = {
    MEMBER: "member",
    GUEST: "guest",
    ANONYMOUS: "anonymous",
    BANNED: "banned",
}


def _last_seen_date(last_seen) -> str:
    if not last_seen:
        return "N/A"
    return datetime.fromtimestamp(last_seen, tz=timezone.utc).strftime("%Y-%m-%d")


def _last_seen_str(last_seen) -> str:
    return datetime.fromtimestamp(last_seen or 0, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class UserAdmin(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.version = "0.0.7"

        self.register_module("useradmin")
        self.register_command("all", "useradmin", "SUPERADMIN")

        self.help["description"] = "This module allows a superadmin to manage member data including buddy list."
        self.help["command"] = {
            "useradmin": "Show overview of members, buddies and stats.",
            "useradmin userlist": "Displays a list of all of the bot's users.",
            "useradmin userlist <all|member|guest|anonymous|banned|never>": "Displays a filtered list of the bot's users.",
            "useradmin userlist clear <guest|anonymous|banned|never>": "Purge users from the bot's users.",
            "useradmin memberlist": "Displays a list of all of the bot's members.",
            "useradmin memberlist main": "Displays a list of all of the bot's members which are main characters.",
            "useradmin memberlist alt": "Displays a list of all of the bot's members which are alt characters.",
            "useradmin memberlist cidle <#>": "Count of members who have been idle for <#> days.",
            "useradmin memberlist idle <#>": "List of members sorted by last seen who have been idle for <#> days.",
            "useradmin memberlist clear <#>": "Remove all users who have been idle for <#> days ; ALWAYS backup first as these datas might then be unrecoverable (except for AO org members possibly readded by rosterupdate).",
            "useradmin altlist list obsolete": "List obsolete entries in the alts table for characters who are no longer members of the bot.",
            "useradmin altlist clear obsolete": "Remove entries from the alts table for characters who are no longer members of the bot. Note: Semi-safe to run.. if people add alts before they are invited to guild, this might get lost though.",
            "useradmin buddylist": "Displays a list of all of the bot's buddies.",
            "useradmin buddylist missing": "Displays a list of members not currently added to the bot's buddylist.",
            "useradmin buddylist clear": "Wipes all of the bots buddies from the bot's buddylist. Note: Safe to run, you can always re-add members by running rosterupdate.",
            "useradmin buddylist fix": "Removes all buddies that ain't members nor guests, adds all missing members/guests. Note: Safe to run, you can always re-add members by running rosterupdate.",
            "useradmin buddy add <id>": "Add a character identified by id to the bot's buddylist.",
            "useradmin buddy remove <id>": "Remove a character identified by id from the bot's buddylist. Note: Safe to run, you can always re-add members by running rosterupdate.",
            "useradmin whois clear <all|member|guest|anonymous|banned|obsolete>": "Remove entries from the whois database. Note: Safe to run, whois database will build itself up again when characters gets added to bot or people run whois.",
        }
        self.help["notes"] = (
            "Important DISCLAIMER:\n"
            "Any use of this module is 100% at your own risk.\n"
            "You will be sole responsible if you happen to delete unrecoverable datas by mistake.\n"
            "So always backup your full database first before doing anymore command you may regret - too late."
        )

    # -- dispatch ---------------------------------------------------------------
    def command_handler(self, name, msg, origin):
        if re.match(r"^useradmin userlist$", msg, re.I):
            rv = self._list_users()
        elif (m := re.match(r"^useradmin userlist (all|member|guest|anonymous|banned|never)$", msg, re.I)):
            rv = self._list_users(m.group(1).lower())
        elif (m := re.match(r"^useradmin userlist clear (guest|anonymous|banned|never)$", msg, re.I)):
            rv = self._clear_users(m.group(1).lower())
        elif re.match(r"^useradmin memberlist$", msg, re.I):
            rv = self._list_members()
        elif (m := re.match(r"^useradmin memberlist (main|alt)$", msg, re.I)):
            rv = self._list_members(m.group(1))
        elif (m := re.match(r"^useradmin memberlist (cidle) (\d+)$", msg, re.I)):
            rv = self._list_members(m.group(1), int(m.group(2)))
        elif (m := re.match(r"^useradmin memberlist (idle) (\d+)$", msg, re.I)):
            rv = self._list_members(m.group(1), int(m.group(2)))
        elif (m := re.match(r"^useradmin memberlist clear (\d+)$", msg, re.I)):
            rv = self._clear_users(m.group(1))
        elif (m := re.match(r"^useradmin altlist clear (all|obsolete)$", msg, re.I)):
            rv = self._clear_alts(m.group(1).lower())
        elif re.match(r"^useradmin altlist list obsolete$", msg, re.I):
            rv = self._list_obsolete_alts()
        elif re.match(r"^useradmin buddylist$", msg, re.I):
            rv = self._list_buddies()
        elif re.match(r"^useradmin buddylist missing$", msg, re.I):
            rv = self._list_missing_buddies()
        elif re.match(r"^useradmin buddylist clear$", msg, re.I):
            rv = self._clear_buddies()
        elif re.match(r"^useradmin buddylist fix$", msg, re.I):
            rv = self._fix_buddies()
        elif (m := re.match(r"^useradmin buddy add (\d+)$", msg, re.I)):
            rv = self._add_buddy(m.group(1))
        elif (m := re.match(r"^useradmin buddy remove (\d+)$", msg, re.I)):
            rv = self._remove_buddy(m.group(1))
        elif (m := re.match(r"^useradmin whois clear (all|member|guest|anonymous|banned|obsolete)$", msg, re.I)):
            rv = self._clear_whois(m.group(1).lower())
        else:
            rv = self._show_overview(name, origin)
        return self._prefix_output(rv)

    def _prefix_output(self, rv):
        if not rv:
            return False
        return "##white####bluegray##[-UserAdmin-]##end## :: " + rv + "##end##"

    # -- blob helpers -------------------------------------------------------------
    def _blob_header(self, title: str | None = None) -> str:
        if title:
            return f"<font color='#8CB6FF'>UserAdmin :: {title}</font>\n"
        return "<font color='#8CB6FF'>UserAdmin</font>\n"

    def _blob_section_header(self, title: str) -> str:
        return f"<b></b>\n<font color='#9AD5D9'>{title}</font>\n"

    def _cmd(self, title: str, subcmd: str, botcmd: str = "useradmin") -> str:
        command = botcmd
        if subcmd:
            command += " " + subcmd
        return self.bot.core("tools").chatcmd(command, title)

    def _link_list(self, links, separator=" | ", prefix=" :: [ ", suffix=" ]") -> str:
        if not links:
            return ""
        return prefix + separator.join(links) + suffix

    def _section_overview(self, title: str, lines: list[dict]) -> str:
        output = self._blob_section_header(title) if title else ""
        for line in lines:
            if line["count"] is None:
                if line["links"]:
                    output += f"{line['title']}{self._link_list(line['links'])}\n"
                else:
                    output += f"{line['title']}\n"
            else:
                if line["count"] > 0 and line["links"]:
                    output += f"{line['title']}: ##seablue##{line['count']}##end##{self._link_list(line['links'])}\n"
                else:
                    output += f"{line['title']}: ##seablue##{line['count']}##end##\n"
        return output

    # -- user_level helpers ---------------------------------------------------
    def _user_level_decode(self, lvl: str):
        lvl = str(lvl).strip().lower()
        return _LEVEL_DECODE.get(lvl, lvl)

    def _user_level_encode(self, lvl) -> str:
        return _LEVEL_ENCODE.get(lvl, "")

    # -- loaders ----------------------------------------------------------------
    def _load_users(self, level=None, order_by="u.nickname", extra_where=None) -> list[dict]:
        where = []
        if level is not None:
            where.append(f"u.user_level = {int(level)}")
        if extra_where:
            where.append(extra_where)
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        rows = self.bot.db.select(
            f"SELECT u.char_id, u.nickname, u.last_seen, u.user_level FROM #___users u{where_sql} ORDER BY {order_by}",
            True,
        ) or []
        for row in rows:
            row["last_seen_date"] = _last_seen_date(row["last_seen"])
            row["last_seen_str"] = _last_seen_str(row["last_seen"])
        return rows

    def _load_never(self) -> list[dict]:
        rows = self.bot.db.select(
            "SELECT u.char_id, u.nickname, u.last_seen, u.user_level FROM #___users u "
            "WHERE user_level >= 0 AND last_seen = 0 ORDER BY u.nickname",
            True,
        ) or []
        for row in rows:
            row["last_seen_date"] = "N/A"
            row["last_seen_str"] = _last_seen_str(0)
        return rows

    def _load_alts(self) -> dict:
        rows = self.bot.db.select("SELECT alt, main FROM #___alts ORDER BY alt", True) or []
        return {row["alt"]: row["main"] for row in rows}

    def _load_whois(self) -> dict:
        rows = self.bot.db.select("SELECT ID, nickname FROM #___whois ORDER BY nickname", True) or []
        return {row["ID"]: row["nickname"] for row in rows}

    # -- overview ---------------------------------------------------------------
    def _show_overview(self, name, origin):
        member_count = guest_count = anonymous_count = banned_count = 0
        buddy_member = buddy_guest = buddy_anon = buddy_banned = 0
        whois_member = whois_guest = whois_anon = whois_banned = 0
        main_count = alt_count = 0

        buddies = self.bot.aoc.buddies
        whois = self._load_whois()
        alts = self._load_alts()
        users = self._load_users()
        never = self._load_never()

        for u in users:
            lvl = u["user_level"]
            if lvl == MEMBER:
                member_count += 1
                if u["char_id"] in buddies:
                    buddy_member += 1
                if u["char_id"] in whois:
                    whois_member += 1
                if u["nickname"] in alts:
                    alt_count += 1
                else:
                    main_count += 1
            elif lvl == GUEST:
                guest_count += 1
                if u["char_id"] in buddies:
                    buddy_guest += 1
                if u["char_id"] in whois:
                    whois_guest += 1
            elif lvl == ANONYMOUS:
                anonymous_count += 1
                if u["char_id"] in buddies:
                    buddy_anon += 1
                if u["char_id"] in whois:
                    whois_anon += 1
            elif lvl == BANNED:
                banned_count += 1
                if u["char_id"] in buddies:
                    buddy_banned += 1
                if u["char_id"] in whois:
                    whois_banned += 1
            else:
                self.bot.log(
                    "UserAdmin", "WARNING",
                    f"Invalid user_level for char_id: '{u['char_id']}', nickname: '{u['nickname']}'.",
                )

        output = self._blob_header("Overview")
        output += (
            "\nThis is a SUPERADMIN sensible tool. Remember to BACKUP your database before clearing any data.\n"
            "Buddies however are stored in the bot's friendlist & could be rebuilt by <pre>rosterupdate. "
            "Same goes for <pre>whois datas which are pulled on demand.\n"
            "ALL other datas might be ##red##unrecoverable##end## (except for AO Org Members possibly readded "
            "by <pre>rosterupdate). So please first read the "
            + self._cmd("help", "useradmin", "help") + " section for more details on each function.\n"
        )

        output += self._section_overview("Users", [
            {"title": "Total Users", "count": len(users), "links": [self._cmd("list", "userlist all")]},
            {"title": "Members", "count": member_count, "links": [self._cmd("list", "userlist member")]},
            {"title": "Guests", "count": guest_count, "links": [
                self._cmd("list", "userlist guest"), self._cmd("manage", "", "guest"), self._cmd("clear", "userlist clear guest"),
            ]},
            {"title": "Anonymous (deleted)", "count": anonymous_count, "links": [
                self._cmd("list", "userlist anonymous"), self._cmd("clear", "userlist clear anonymous"),
            ]},
            {"title": "Never seen", "count": len(never), "links": [
                self._cmd("list", "userlist never"), self._cmd("clear", "userlist clear never"),
            ]},
            {"title": "Banned", "count": banned_count, "links": [
                self._cmd("list", "userlist banned"), self._cmd("clear", "userlist clear banned"),
            ]},
        ])

        output += self._section_overview("Members", [
            {"title": "Total Members", "count": member_count, "links": [self._cmd("list", "memberlist")]},
            {"title": "##green##Count##end## Idle Members", "count": None, "links": [
                self._cmd(str(d), f"memberlist cidle {d}") for d in (30, 60, 90, 180, 270, 360)
            ]},
            {"title": "##orange##List##end## Idle Members", "count": None, "links": [
                self._cmd(str(d), f"memberlist idle {d}") for d in (30, 60, 90, 180, 270, 360)
            ]},
            {"title": "##red##Clear##end## Idle Members", "count": None, "links": [
                self._cmd(str(d), f"memberlist clear {d}") for d in (90, 180, 360, 720)
            ]},
            {"title": "Main chars", "count": main_count, "links": [self._cmd("list", "memberlist main")]},
            {"title": "Alt chars", "count": alt_count, "links": [self._cmd("list", "memberlist alt")]},
            {"title": "Obsolete entries in alts table", "count": len(alts) - alt_count, "links": [
                self._cmd("list", "altlist list obsolete"), self._cmd("clear", "altlist clear obsolete"),
            ]},
        ])

        output += self._section_overview("Buddies", [
            {"title": "Total Buddies", "count": len(buddies), "links": [
                self._cmd("list", "buddylist"), self._cmd("clear", "buddylist clear"),
                self._cmd("fix", "buddylist fix"), self._cmd("rosterupdate", "", "rosterupdate"),
            ]},
            {"title": "Members", "count": buddy_member, "links": []},
            {"title": "Missing members", "count": member_count - buddy_member, "links": [
                self._cmd("list", "buddylist missing"),
            ]},
            {"title": "Guests", "count": buddy_guest, "links": []},
            {"title": "Anonymous (deleted)", "count": buddy_anon, "links": []},
            {"title": "Banned", "count": buddy_banned, "links": []},
        ])

        output += self._section_overview("Whois", [
            {"title": "Total Whois Entries", "count": len(whois), "links": [self._cmd("clear", "whois clear all")]},
            {"title": "Members", "count": whois_member, "links": [self._cmd("clear", "whois clear member")]},
            {"title": "Guests", "count": whois_guest, "links": [self._cmd("clear", "whois clear guest")]},
            {"title": "Anonymous (deleted)", "count": whois_anon, "links": [self._cmd("clear", "whois clear anonymous")]},
            {"title": "Banned", "count": whois_banned, "links": [self._cmd("clear", "whois clear banned")]},
            {"title": "Obsolete entries in whois table", "count": len(whois) - (whois_member + whois_guest + whois_anon + whois_banned), "links": [
                self._cmd("clear", "whois clear obsolete"),
            ]},
        ])

        tools = self.bot.core("tools")
        self.bot.send_tell(
            name,
            self._prefix_output(
                "Members: ##seablue##{}/{}##end## :: Buddies: ##seablue##{}/{}##end## :: "
                "Whois: ##seablue##{}/{}##end## :: {}".format(
                    member_count, len(users), buddy_member, len(buddies), whois_member, len(whois),
                    tools.make_blob("Show", output),
                )
            ),
            1,
        )
        return False

    # -- buddylist ----------------------------------------------------------------
    def _list_buddies(self):
        buddies = self.bot.aoc.buddies
        if not buddies:
            return "No buddies in <botname>'s buddylist!"
        chat = self.bot.core("chat")
        buddylist = sorted(
            ((uid, chat.get_uname(uid)) for uid in buddies),
            key=lambda kv: kv[1] or "",
        )
        output = self._blob_header("Buddylist") + "<b></b>\n"
        for uid, uname in buddylist:
            output += f"{uname} :: [ {self._cmd('remove', f'buddy remove {uid}')} ]\n"
        return f"Found ##seablue##{len(buddylist)}##end## buddies :: " + self.bot.core("tools").make_blob("Show", output)

    def _list_missing_buddies(self):
        buddies = self.bot.aoc.buddies
        users = self._load_users(level=MEMBER)
        if not users:
            return "No members in <botname>'s memberlist!"
        output = self._blob_header("Members not in buddylist") + "<b></b>\n"
        count = 0
        for u in users:
            if u["char_id"] not in buddies:
                output += "{} :: {} :: {} :: [ {} | {} | {} | {} | {} ]\n".format(
                    u["nickname"], u["char_id"], u["last_seen_str"],
                    self._cmd("add", f"buddy add {u['char_id']}"),
                    self._cmd("not", u["nickname"], "notify on"),
                    self._cmd("alt", u["nickname"], "alts"),
                    self._cmd("who", u["nickname"], "whois"),
                    self._cmd("del", u["nickname"], "member del"),
                )
                count += 1
        if count > 0:
            return f"Found ##seablue##{count}##end## members not in buddylist :: " + self.bot.core("tools").make_blob("Show", output)
        return "All current members are in <botname>'s memberlist"

    def _clear_buddies(self):
        buddies = list(self.bot.aoc.buddies.keys())
        chat = self.bot.core("chat")
        for uid in buddies:
            chat.buddy_remove(uid)
        return f"Removed ##seablue##{len(buddies)}##end## buddies from <botname>'s buddylist"

    def _fix_buddies(self):
        buddies = self.bot.aoc.buddies
        chat = self.bot.core("chat")
        users = self._load_users()
        user_ids = {u["char_id"] for u in users}
        count = removed = missing = 0
        for u in users:
            if u["char_id"] not in buddies:
                chat.buddy_add(u["char_id"])
                count += 1
                missing += 1
        for uid in list(buddies.keys()):
            if uid not in user_ids:
                chat.buddy_remove(uid)
                count += 1
                removed += 1
        return f"Fixed ##seablue##{count}##end## buddies from <botname>'s buddylist ({removed} deleted ; {missing} added)"

    def _add_buddy(self, char_id):
        char_id = int(char_id)
        chat = self.bot.core("chat")
        char_name = chat.get_uname(char_id)
        if not chat.buddy_exists(char_id):
            chat.buddy_add(char_id)
            return f"Added ##seablue##{char_name}##end## to <botname>'s buddylist"
        return f"##seablue##{char_name}##end## is already on <botname>'s buddylist"

    def _remove_buddy(self, char_id):
        char_id = int(char_id)
        chat = self.bot.core("chat")
        char_name = chat.get_uname(char_id)
        if chat.buddy_exists(char_id):
            chat.buddy_remove(char_id)
            return f"Removed ##seablue##{char_name}##end## from <botname>'s buddylist"
        return f"##seablue##{char_name}##end## is not on <botname>'s buddylist"

    # -- memberlist / userlist ------------------------------------------------------
    def _list_members(self, filter_=None, limit=0):
        tools = self.bot.core("tools")
        if filter_:
            filter_ = filter_.strip().lower().capitalize()

        if filter_ in ("Idle", "Cidle"):
            extra_where = None
            if limit > 0:
                offset_time = int(time.time()) - limit * 24 * 60 * 60
                extra_where = f"u.last_seen > 0 AND u.last_seen < {offset_time}"
            users = self._load_users(level=MEMBER, order_by="u.last_seen DESC", extra_where=extra_where)
            if users:
                output = self._blob_header(f"{len(users)} idle members last {limit} days") + "<b></b>\n"
                if filter_ == "Idle":
                    for u in users:
                        output += "{} @ {} :: [ {} | {} | {} ".format(
                            u["nickname"], u["last_seen_date"],
                            self._cmd("alts", u["nickname"], "alts"),
                            self._cmd("whois", u["nickname"], "whois"),
                            self._cmd("delete", u["nickname"], "member del"),
                        )
                        output += tools.chatcmd(f"kick {u['nickname']}", "kick", "org")
                        output += "]\n"
                return (
                    f"Found ##seablue##{len(users)}##end## idle members the last {limit} day(s) :: "
                    + tools.make_blob("Show", output)
                )
            return f"No idlers above {limit} day(s) were found in <botname>'s memberlist."

        users = self._load_users(level=MEMBER)
        if not users:
            return "<botname>'s memberlist is empty."

        if filter_ in ("Main", "Alt"):
            alts = self._load_alts()
            count = 0
            output = self._blob_header(f"{filter_} characters") + "<b></b>\n"
            for u in users:
                is_alt = u["nickname"] in alts
                if (filter_ == "Main" and not is_alt) or (filter_ == "Alt" and is_alt):
                    count += 1
                    output += "{} @ {} :: [ {} | {} | {} ]\n".format(
                        u["nickname"], u["last_seen_date"],
                        self._cmd("alts", u["nickname"], "alts"),
                        self._cmd("whois", u["nickname"], "whois"),
                        self._cmd("delete", u["nickname"], "member del"),
                    )
            return f"Found ##seablue##{count}##end## {filter_} characters :: " + tools.make_blob("Show", output)

        output = self._blob_header("All members") + "<b></b>\n"
        for u in users:
            output += "{} @ {} :: [ {} | {} | {} ]\n".format(
                u["nickname"], u["last_seen_date"],
                self._cmd("alts", u["nickname"], "alts"),
                self._cmd("whois", u["nickname"], "whois"),
                self._cmd("delete", u["nickname"], "member del"),
            )
        return f"Found ##seablue##{len(users)}##end## members :: " + tools.make_blob("Show", output)

    def _list_users(self, level=None):
        tools = self.bot.core("tools")
        users: list[dict] = []
        output = ""
        if level in (None, "all"):
            users = self._load_users()
            output = self._blob_header("Userlist") + "<b></b>\n"
        elif level == "never":
            users = self._load_never()
            output = self._blob_header("Never seen list") + "<b></b>\n"
        elif level in ("member", "guest", "anonymous", "banned"):
            lvl = self._user_level_decode(level)
            users = self._load_users(level=lvl)
            # Faithful PHP quirk: the "<b></b>\n" is nested inside the blob
            # title argument here (unlike the other branches above).
            output = self._blob_header(f"Userlist :: {level}<b></b>\n")

        if users:
            for u in users:
                output += "{} ( {}-{} @ {} ) ".format(
                    u["nickname"],
                    self._user_level_encode(u["user_level"])[:1].upper(),
                    u["char_id"],
                    u["last_seen_date"],
                )
                if level == "never":
                    output += tools.chatcmd(f"kick {u['nickname']}", "kick", "org")
                output += "\n"
            return f"Found ##seablue##{len(users)}##end## users :: " + tools.make_blob("Show", output)
        return "##red##No matching users found in <botname>'s userlist.##end##"

    # -- clearing ---------------------------------------------------------------
    def _clear_users(self, level):
        db = self.bot.db
        if level in ("guest", "anonymous", "banned"):
            lvl = self._user_level_decode(level)
            if db.query(f"DELETE FROM #___users WHERE user_level = {int(lvl)}"):
                return f"Cleared {level} entries from <botname>'s users table."
            return f"##red##Error clearing {level} entries from <botname>'s users table.##end##"
        if level == "never":
            if db.query("DELETE FROM #___users WHERE user_level >= 0 AND last_seen = 0"):
                return "Cleared all never seen entries from <botname>'s users table."
            return "##red##Error clearing all never seen entries from <botname>'s users table.##end##"
        if str(level).isdigit() and int(level) >= 90:
            days = int(level)
            offset_time = int(time.time()) - days * 24 * 60 * 60
            if db.query(
                f"DELETE FROM #___users WHERE user_level = 2 AND last_seen > 0 AND last_seen < {offset_time}"
            ):
                return f"Cleared at least {days} days old entries from <botname>'s users table."
            return f"##red##Error clearing at least {days} days old idle entries from <botname>'s users table.##end##"
        return False

    def _clear_whois(self, level):
        db = self.bot.db
        if level == "all":
            if db.query("TRUNCATE #___whois"):
                return "Cleared all entries from <botname>'s whois database."
            return "##red##Error clearing all entries from <botname>'s whois database.##end##"
        if level == "obsolete":
            if db.query("DELETE FROM #___whois WHERE ID NOT IN (SELECT char_id FROM #___users)"):
                return "Cleared obsolete entries from <botname>'s whois database."
            return "##red##Error clearing obsolete entries from <botname>'s whois database.##end##"
        if level in ("member", "guest", "anonymous", "banned"):
            lvl = self._user_level_decode(level)
            if db.query(
                f"DELETE FROM #___whois WHERE ID IN (SELECT char_id FROM #___users WHERE user_level = {int(lvl)})"
            ):
                return f"Cleared {level} entries from <botname>'s whois database."
            return f"##red##Error clearing {level} entries from <botname>'s whois database.##end##"
        return False

    def _clear_alts(self, filter_):
        db = self.bot.db
        if filter_ == "obsolete":
            ok = db.query(
                f"DELETE FROM #___alts WHERE main NOT IN (SELECT nickname FROM #___users WHERE user_level = {MEMBER})"
            ) and db.query(
                f"DELETE FROM #___alts WHERE alt NOT IN (SELECT nickname FROM #___users WHERE user_level = {MEMBER})"
            )
            if ok:
                return "Cleared obsolete entries from <botname>'s alts table."
            return "##red##Error clearing obsolete entries from <botname>'s alts table.##end##"
        # Faithful PHP quirk: "all" is accepted by the dispatching regex but
        # has no case in the original `switch` either, so it falls through
        # to a silent `False` (no reply) just like here.
        return False

    def _list_obsolete_alts(self):
        rows = self.bot.db.select(
            f"SELECT alt, main FROM #___alts WHERE main NOT IN "
            f"(SELECT nickname FROM #___users WHERE user_level = {MEMBER}) ORDER BY alt",
            True,
        )
        if rows:
            output = self._blob_header("Obsolete entries in alts table") + "<b></b>\n"
            for row in rows:
                output += f"{row['alt']} ({row['main']})\n"
            return (
                f"Found ##seablue##{len(rows)}##end## obsolete entries in alts table :: "
                + self.bot.core("tools").make_blob("Show", output)
            )
        return "##red##No obsolete entries found in <botname>'s alts table.##end##"
