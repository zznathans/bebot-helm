"""Ported from Core/Alts.php.

Tracks main<->alt character relationships and renders the "alts list" blob
used by the `alts`/`whois`-adjacent commands elsewhere in the bot.

Scope cuts, matching established precedent elsewhere in this port:
  * Schema-version migration (`update_table()`'s v1 -> v2 `ALTER TABLE ...
    ADD confirmed` step) is dropped -- the same way settings.py/
    access_control.py/player_notes.py already do it -- and the #___alts
    table is created directly with the final (v2) schema below (including
    the `confirmed` column) since there's nothing to migrate for a fresh
    Python port.
  * `core("whois").lookup(name)` (fancy_output()/make_info_blob()) is
    ported as a faithful call site: Core/Ao/Whois.php isn't ported (see
    the docstring at the top of main_modules/player.py for the rationale --
    no synchronous blocking-socket equivalent in this asyncio port), so
    this resolves via Bot.core()'s DummyModule fallback and returns an
    error string rather than a whois dict. Where the PHP checked
    `$whois instanceof BotError`, this port checks "is it actually a
    dict?" instead (covering both a BotError and the dummy-module string),
    falling back to `{"nickname": name}` either way. Net effect: the
    "Detail" (level/profession) portion of the fancy alts blob is always
    empty until whois is ported -- there's simply no data source for it.
  * `core("security").cache_mgr(...)` calls (invalidating the
    "main"/"maincache" security lookup caches) are guarded with a
    `hasattr()` check rather than called unconditionally: Main/03_Security.php's
    own `cache_mgr()` isn't ported yet either (see main_modules/security.py's
    docstring), so calling it unguarded would raise AttributeError on the
    real Security module instead of harmlessly no-op'ing the way an
    unregistered module would via DummyModule.
  * `make_info_blob()`'s "Last seen at" line used `gmdate($FormatString,
    ...)` to render a timestamp. main_modules/time.py's docstring already
    notes nothing in this port consumes the `Time/FormatString` setting
    yet (no gmdate() implementation exists), so this renders the UTC
    timestamp with a fixed "%Y-%m-%d %H:%M:%S" format instead.

Cross-module interface with main_modules/online.py (the two are circularly
dependent in the PHP original, hence porting them together):
  * Alts calls `bot.core("online").get_online_state(alt) -> dict` and
    `bot.core("online").get_last_seen(alt) -> int | float | False` from
    make_info_blob().
  * Online calls `bot.core("alts").main(name) -> str` and
    `bot.core("alts").get_alts(main) -> list[str]` from get_last_seen()
    when `checkalts=True`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..commodities.base import BasePassiveModule, BotError


def _norm(name) -> str:
    """PHP's `ucfirst(strtolower($x))` -- Python's str.capitalize() matches exactly."""
    return str(name).capitalize()


class Alts(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        db = bot.db
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('alts', False)} "
            "(alt VARCHAR(255) NOT NULL PRIMARY KEY, main VARCHAR(255), confirmed INT DEFAULT '1')"
        )
        self.register_module("alts")
        self.register_event("cron", "1hour")
        self.mains: dict[str, str] = {}
        self.alts: dict[str, dict[str, str]] = {}
        self.create_caches()
        settings = self.bot.core("settings")
        settings.create("Alts", "Output", "Fancy", "How would you like your alts list", "Fancy;Old")
        settings.create("Alts", "Detail", True, "Show level and profession in the alts list")
        settings.create("Alts", "LastSeen", True, "Show the time we last saw an alt if they are offline")
        settings.create(
            "Alts", "Confirmation", False,
            "Does the Alt have to Confirm him Self as an Alt after being Added?",
        )
        settings.create(
            "Alts", "incAll", False,
            "Should the Alt that was used to call the info also be listed inside the blob?",
        )

    # -- internal helpers -----------------------------------------------------
    def _cache_mgr(self, action: str, cache: str, info) -> None:
        security = self.bot.core("security")
        method = getattr(security, "cache_mgr", None)
        if method is not None:
            method(action, cache, info)

    def _player_exists(self, name: str) -> bool:
        pid = self.bot.core("player").id(name)
        return bool(pid) and not isinstance(pid, BotError)

    # -- caches ----------------------------------------------------------------
    def create_caches(self) -> None:
        """Rebuild the main<->alt lookup dicts from the #___alts table."""
        self.mains = {}
        self.alts = {}
        rows = self.bot.db.select(
            "SELECT main, alt FROM #___alts WHERE confirmed = 1 ORDER BY main ASC, alt ASC"
        ) or []
        if not rows:
            return
        curmain = ""
        for main_raw, alt_raw in rows:
            main = _norm(main_raw)
            if curmain != main:
                curmain = main
                self.alts[curmain] = {}
            altname = _norm(alt_raw)
            self.mains[altname] = curmain
            self.alts[curmain][altname] = altname
        self._cache_mgr("del", "maincache", "")

    def cron(self, duration=None) -> None:
        self.create_caches()

    # -- mutation ----------------------------------------------------------------
    def add_alt(self, main: str, alt: str) -> None:
        main = _norm(main)
        alt = _norm(alt)
        self._cache_mgr("add", "main", main)
        self._cache_mgr("add", "main", alt)
        self.alts.setdefault(main, {})
        self.alts[main][alt] = alt
        self.alts[main] = dict(sorted(self.alts[main].items(), key=lambda kv: kv[1].lower()))
        self.mains[alt] = main

    def del_alt(self, main: str, alt: str) -> None:
        self._cache_mgr("del", "main", _norm(main))
        self.mains.pop(_norm(alt), None)
        self.alts.get(_norm(main), {}).pop(_norm(alt), None)

    # -- lookups ----------------------------------------------------------------
    def main(self, char: str) -> str:
        char = _norm(char)
        return self.mains.get(char, char)

    def get_alts(self, char) -> list[str]:
        if isinstance(char, int) or (isinstance(char, str) and char.isdigit()):
            char = self.bot.core("player").name(char)
        return list(self.alts.get(_norm(char), {}).values())

    # -- rendering ----------------------------------------------------------------
    def old_output(self, who: str, returntype: int = 0) -> dict:
        main = self.main(who)
        alts = self.get_alts(main)
        if not alts:
            return {"alts": False, "list": ""}
        return {"alts": True, "list": self.make_alt_blob(main, _norm(who), alts, returntype)}

    def make_alt_blob(self, main: str, who: str, alts: list[str], returntype: int) -> str:
        tools = self.bot.core("tools")
        result = f"##highlight##::: {main}'s Alts :::##end##\n\n"
        for alt in alts:
            result += tools.chatcmd(f"whois {alt}", alt) + "\n"
        title = "Alts" if main == who else f"{main}'s alts"
        if returntype == 1:
            return result
        return tools.make_blob(title, result)

    def fancy_output(self, name: str, returntype: int):
        if not self._player_exists(name):
            return f"##highlight##{name}##end## does not exist."
        name = _norm(name)
        whois = self.bot.core("whois").lookup(name)
        if not isinstance(whois, dict):
            whois = {"nickname": name}
        main = self.main(name)
        alts = self.get_alts(main)
        if name != main or (alts and self.bot.core("settings").get("Alts", "incAll")):
            alts = [main] + list(alts)
        return {
            "alts": bool(alts),
            "list": self.make_info_blob(whois, main, alts, returntype),
        }

    def make_info_blob(self, whois: dict, main: str, alts=None, returntype: int = 0) -> str:
        tools = self.bot.core("tools")
        settings = self.bot.core("settings")
        window = ""
        if alts:
            window = f"##normal##:::  {main}'s alts  :::##end##\n\n"
            for alt in alts:
                if alt != whois.get("nickname") or settings.get("Alts", "incAll"):
                    window += tools.chatcmd(f"whois {alt}", alt) + "</a>"
                    online = self.bot.core("online").get_online_state(alt)
                    window += " " + online["content"]

                    if settings.get("Alts", "Detail"):
                        whoisalt = self.bot.core("whois").lookup(alt)
                        if not isinstance(whoisalt, dict):
                            whoisalt = {"nickname": alt}
                        if whoisalt.get("level"):
                            window += f"\n##normal## - (##highlight##{whoisalt['level']}##end##"
                            if str(self.bot.game).lower() == "ao":
                                window += f"/##lime##{whoisalt.get('at_id')}##end##"
                            window += f" {whoisalt.get('profession')})##end##"

                    if online["status"] <= 0:
                        if settings.get("Alts", "LastSeen"):
                            last_seen = self.bot.core("online").get_last_seen(alt)
                            if last_seen:
                                time_str = datetime.fromtimestamp(
                                    last_seen, tz=timezone.utc
                                ).strftime("%Y-%m-%d %H:%M:%S")
                                window += (
                                    f"\n##normal## - Last seen at:##highlight## {time_str} UTC##end####end##"
                                )
                    window += "\n\n"
        if str(whois.get("nickname", "")).lower() == main.lower():
            title = "Alts"
        else:
            title = f"{main}'s alts"
        if returntype == 1:
            return window
        return tools.make_blob(title, window)

    def show_alt(self, who: str, returntype: int = 0):
        """The entry point other modules should use to render an alts list."""
        output = self.bot.core("settings").get("Alts", "Output")
        if output == "Old":
            return self.old_output(_norm(who), returntype)
        if output == "Fancy":
            return self.fancy_output(_norm(who), returntype)
        return "Settings module required for this module to work properly!"
