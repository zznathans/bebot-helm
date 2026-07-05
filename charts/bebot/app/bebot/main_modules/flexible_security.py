"""Ported from Main/11_FlexibleSecurity.php.

Extended security module allowing flexible security groups like "all omni
210+ are GUESTs" -- an extension on top of the existing security groups
defined by security.py, keyed by shared `gid`.

Schema-migration code (update_table's version-1/2 ALTERs, plus the
SchemaVersion-setting migration shim) is dropped -- we always create the
current schema directly, matching the access_control.py / settings.py
precedent.

Two cuts, both following established precedent elsewhere in this port:
  * The `core("whois")->lookup(player)` call (done to make sure the player
    is in the whois cache before querying it) is kept as a faithful call
    site, but Core/Ao/Whois.php itself isn't ported -- there's no
    synchronous blocking-socket equivalent in this asyncio port (see the
    docstring at the top of main_modules/player.py for the same cut).
    Since "whois" is never registered as a core module, `bot.core("whois")`
    resolves to the bot's DummyModule fallback and `.lookup(...)` safely
    no-ops (logs an error and returns an error string that is ignored
    here).
  * The PHP module also calls `core("security")->cache_mgr("del",
    "maincache", 0)` after a flexible-group definition changes, to
    invalidate an in-memory per-player access-level cache inside the
    Security module. That cache was never ported into security.py --
    get_access_level() there always queries the DB directly -- so there is
    nothing to invalidate. Unlike the whois case, "security" *is* a
    registered real module here, so blindly calling a nonexistent
    `cache_mgr` on it would raise AttributeError rather than harmlessly
    no-op; the call site is therefore dropped instead of ported.
"""
from __future__ import annotations

from ..commodities.base import BasePassiveModule

# Maps a security_flexible.field value to the whois-cache column it is compared against.
QUERY_NAMES = {
    "level": "level",
    "profession": "profession",
    "faction": "faction",
    "rank_id": "org_rank_id",
    "org_id": "org_id",
    "at_id": "defender_rank_id",
}


class FlexibleSecurity(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        db = bot.db
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('security_flexible', True)} ("
            "id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, "
            "gid INT(10) unsigned NOT NULL, "
            "field ENUM('join', 'level', 'profession', 'faction', 'rank_id', 'org_id', 'at_id'), "
            "op ENUM('=', '<', '<=', '>', '>=', '!=', '&&', '||'), "
            "compareto VARCHAR(100) NOT NULL DEFAULT '')"
        )
        self.register_module("flexible_security")
        self.register_event("cron", "6hour")
        # Highest access level defined by all flexible groups, per player.
        self.cache: dict[str, int] = {}
        self.enabled = False
        self.check_enable()

    def cron(self, duration=None) -> None:
        # Clean cache periodically to react to changes in the whois cache.
        self.clear_cache()

    def clear_cache(self) -> None:
        """Clears the cache and re-checks whether flexible security is enabled.

        Should be called whenever a flexible group is modified in any way
        (this includes changes to access levels via the Security module).
        """
        self.cache = {}
        self.check_enable()

    def check_enable(self) -> None:
        result = self.bot.db.select("SELECT * FROM #___security_flexible WHERE field = 'join'")
        self.enabled = bool(result)

    def flexible_group_access(self, player: str, highest: int) -> int:
        """Returns the highest access level `player` has due to flexible security
        groups if higher than `highest`. Returns `highest` otherwise."""
        # If we have no rules active, save time, memory and resources.
        if not self.enabled:
            return highest
        # Make sure player is always ucfirst-strtolower:
        player = self.bot.core("tools").sanitize_player(player)
        # Check if cached, then compare highest with cached access level.
        if player in self.cache:
            return max(highest, self.cache[player])
        # Not in cache: get all flexible security groups with a higher access
        # level than `highest` (no sense checking for lower ones).
        groups = self.bot.db.select(
            "SELECT t1.gid, t1.access_level, t2.op FROM #___security_groups AS t1, "
            f"#___security_flexible AS t2 WHERE t1.access_level > {highest} AND t1.gid = t2.gid "
            "AND t2.field = 'join' ORDER BY access_level DESC"
        )
        # No groups with a higher access level? Just return highest again.
        if not groups:
            return highest
        # Do a whois lookup on the character to be certain it is in the cache.
        self.bot.core("whois").lookup(player)
        # Go through the groups in descending order of access level.
        for gid, acl, op in groups:
            groupkind = "OR" if op == "||" else "AND"
            rules = self.bot.db.select(
                f"SELECT field, op, compareto FROM #___security_flexible WHERE gid = {gid} AND field != 'join'"
            )
            if not rules:
                continue
            wherestring = ""
            rulecount = len(rules)
            for count, (field, rule_op, compareto) in enumerate(rules, start=1):
                # Handle "faction = all" / "faction != all" cases.
                if field.lower() == "faction" and compareto.lower() == "all":
                    combine = "OR" if rule_op == "=" else "AND"
                    wherestring += f" (faction {rule_op} 'omni' {combine} faction "
                    wherestring += f"{rule_op} 'clan' {combine} faction {rule_op}"
                    wherestring += " 'neutral') "
                else:
                    wherestring += f" {QUERY_NAMES[field]} {rule_op}"
                    wherestring += f" '{compareto}'"
                if count < rulecount:
                    wherestring += f" {groupkind}"
            # Query the whois cache with the rules.
            ret = self.bot.db.select(
                f"SELECT nickname FROM #___whois WHERE nickname = '{player}' AND ({wherestring})"
            )
            # Got a result? Player is a member of this group -- cache and return it.
            if ret:
                self.cache[player] = acl
                return acl
        # Nothing higher found -- cache this as the result and return highest.
        self.cache[player] = highest
        return highest
