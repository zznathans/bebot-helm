"""Ported from Modules/AdminsUi.php (class `admins`).

Chat-command UI that renders the bot's admin roster ("owner"/"superadmin"/
"admin"/"leader" groups) as a clickable blob, built entirely on top of
already-ported Core modules: `core("alts")` (main/alt resolution + roster
grouping by main), `core("online")` (online-state rendering),
`core("player")` (existence checks for `adminsfix`), `core("security")`
(the bot owner name), `core("tools")` (chatcmd/make_blob), `core("user")`
(re-adding a stale member during `adminsfix`), and `core("chat")`
(buddy-list checks/adds during `adminsfix`).

Scope notes / intentional deviations from the PHP:
  * The PHP reads `$this->bot->core("security")->cache['groups'][$gid]
    ['members']` -- an in-memory group-membership cache Main/03_Security.php
    builds and keeps in sync as groups/memberships change. The ported
    main_modules/security.py deliberately has no such cache (see its
    docstring: it computes access levels live from the `#___users`/
    `#___security_*` tables on every check instead), so there is nothing to
    read there. This port queries `#___security_members` directly for a
    group's `name` column instead, which is the same data the PHP cache was
    ultimately populated from. This mirrors the precedent already set in
    access_control_ui.py (writing straight to `#___access_control` when the
    ported Core module has no method for it) and settings_ui.py (reaching
    for `#___settings` directly for read-only listing queries).
  * `$members` (the commented-out MEMBER/GUEST/ANONYMOUS group sections) was
    already dead code in the PHP original (commented out) -- not ported.
  * Nothing here touches Core/Ao/Whois.php, IRC/relay bridges, or the
    dynamic Core/Modules/ plugin loader.
"""
from __future__ import annotations

import re

from ..commodities.base import BaseActiveModule, BotError
from .security import ADMIN, LEADER, MEMBER, SUPERADMIN

_SECTIONS = (
    (SUPERADMIN, "SA", "Superadmin(s) (SA)"),
    (ADMIN, "A", "Admin(s) (A)"),
    (LEADER, "L", "Leader(s) (L)"),
)


class AdminsUi(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("admins_ui")
        self.register_command("all", "admins", "GUEST")
        self.register_alias("admins", "leaders")
        self.register_command("all", "adminsfix", "OWNER")

        self.help["description"] = "Shows bots Admin list."
        self.help["command"] = {
            "admins": "Shows a short list of admins.",
            "admins all": "Shows a full list of admins.",
            "adminsfix": "Refreshes admins notify & memberships.",
        }

    # -- dispatch ---------------------------------------------------------------
    def command_handler(self, name, msg, channel):
        return self.admins_blob(msg)

    # -- adminsfix repair helper --------------------------------------------------
    def all_fixer(self, name: str) -> None:
        uid = self.bot.core("player").id(name)
        if isinstance(uid, BotError):
            return
        db = self.bot.db
        result = db.select(f"SELECT user_level FROM #___users WHERE nickname = '{name}'")
        if result:
            if result[0][0] != 2:
                self.bot.core("user").add(self.bot.botname, name, 0, MEMBER, 1)
        else:
            self.bot.core("user").add(self.bot.botname, name, 0, MEMBER, 1)
        chat = self.bot.core("chat")
        if not chat.buddy_exists(name):
            chat.buddy_add(name)

    # -- roster rendering ---------------------------------------------------------
    def _group_members(self, gid) -> list[str]:
        rows = self.bot.db.select(f"SELECT name FROM #___security_members WHERE gid = '{gid}'") or []
        return [row[0] for row in rows]

    def _render_main_and_alts(self, main: str, all_: bool, fix: bool) -> tuple[str, bool]:
        """Renders one "- Main is <state>\n   - Alt is <state>" section.

        Returns (text, saw_anyone_online).
        """
        online_mod = self.bot.core("online")
        alts_mod = self.bot.core("alts")
        if fix:
            self.all_fixer(main)
        online = online_mod.get_online_state(main)
        temp = f"\n- ##highlight##{main}##end## is " + online["content"]
        online2 = online["status"] == 1
        for alt in alts_mod.get_alts(main) or []:
            if fix:
                self.all_fixer(alt)
            alt_online = online_mod.get_online_state(alt)
            if alt_online["status"] == 1 or all_:
                temp += f"\n   - {alt} is " + alt_online["content"]
            if alt_online["status"] == 1:
                online2 = True
        temp += "\n"
        return temp, online2

    def admins_blob(self, msg: str) -> str:
        all_ = bool(re.match(r"^admins all$", msg, re.I))
        fix = bool(re.match(r"^adminsfix$", msg, re.I))
        if fix:
            all_ = True

        security = self.bot.core("security")
        alts_mod = self.bot.core("alts")
        db = self.bot.db

        groups = db.select(
            "SELECT gid, name, description, access_level FROM #___security_groups "
            "ORDER BY access_level DESC, gid ASC, name",
            True,
        ) or []

        owner_section = "##highlight##Owner (O)##end##\n"
        section_bodies = {SUPERADMIN: "", ADMIN: "", LEADER: ""}
        section_counts = {SUPERADMIN: 0, ADMIN: 0, LEADER: 0}

        # -- owner + owner's alts -----------------------------------------------
        owner_name = alts_mod.main(security.owner)
        temp, online2 = self._render_main_and_alts(owner_name, all_, fix)
        if online2 or all_:
            owner_section += temp

        # -- superadmin/admin/leader groups --------------------------------------
        for group in groups:
            access_level = group["access_level"]
            if access_level not in section_counts:
                continue
            users = self._group_members(group["gid"])
            section_counts[access_level] += len(users)
            if not users:
                continue
            mains = sorted({alts_mod.main(user) for user in users}, key=str.lower)
            for main in mains:
                temp, online2 = self._render_main_and_alts(main, all_, fix)
                if online2 or all_:
                    section_bodies[access_level] += temp

        tools = self.bot.core("tools")
        inside = "##ao_ccheader##:::: <botname> Admins ::::##end##\n\n##seablue##"
        inside += owner_section + "\n"
        inside += f"{section_counts[SUPERADMIN]} ##highlight##Superadmin(s) (SA)##end##\n{section_bodies[SUPERADMIN]}\n"
        inside += f"{section_counts[ADMIN]} ##highlight##Admin(s) (A)##end##\n{section_bodies[ADMIN]}\n"
        inside += f"{section_counts[LEADER]} ##highlight##Leader(s) (L)##end##\n{section_bodies[LEADER]}\n"
        if not all_:
            inside += "\n" + tools.chatcmd("admins all", "View all bot admins")
        inside += "##end##"
        return "Admins list " + tools.make_blob("click to view", inside)
