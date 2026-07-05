"""Ported from Modules/Afk.php.

Lets a player mark themselves AFK (with an optional reason) via the `afk`
command; any chat line in guild chat or the bot's private group that
mentions an AFK character's name (or the name of one of their alts/
aliases) is answered with how long they've been AFK plus any messages left
for them while away. Also detects when an AFK player speaks again (marking
them back) and, via the buddy-logon event, auto-sets/clears AFK status on
zone-in/logoff for members (AO only, matching the PHP's own
`strtolower($this->bot->game) == 'ao'` guard).

Depends on the already-ported `core("alts")` (`main()`/`get_alts()`, for
folding a player's alts into the AFK-alias watch list), `core("alias")`
(the character-alias module at main_modules/alias.py -- its `.alias` dict
mapping alias -> owning nickname, used the same way here, not to be
confused with `core("command_alias")`), `core("command_alias")` (via
`register_alias("afk", "brb")`, registering "brb" as a chat-command alias
for "afk" -- the PHP's `$this->bot->core("command_alias")->register("afk",
"brb")`), `core("security")` (`get_access_level()` in `buddy()`),
`core("settings")` (the three `Afk/*` settings below), and `core("tools")`
(`make_blob()` for the AFK-messages blob in `msgs()`).

Scope cuts vs. the PHP original:
  * `msgs()`'s AFK-message timestamps were rendered with
    `gmdate($this->bot->core("settings")->get("Time", "FormatString"),
    ...)`. Nothing in this port consumes that setting yet (see
    main_modules/time.py's docstring: no gmdate() equivalent exists), so --
    matching the same cut already made in main_modules/alts.py's
    `make_info_blob()` -- this renders a fixed UTC
    "%Y-%m-%d %H:%M:%S" timestamp instead.
  * `msg_check()`'s per-name/per-alias regex match (`preg_match("/$key\\b/i",
    $msg)`) is ported with the key/alias re.escape()'d before building the
    pattern. Player names and aliases are alphanumeric in practice (no
    regex metacharacters), so this is behaviorally identical for every
    realistic input -- it just avoids a latent crash/mismatch if a
    metacharacter-containing name ever slipped through, which the PHP
    itself has no protection against either.
  * The PHP module's `$afkmsgid` counter (used only as a never-reset dict
    key for alias-triggered message log entries, incremented but never
    read back) is dropped: this port just appends to a plain list for both
    the direct-name and alias-triggered cases in `msg_check()`, which
    `msgs()` iterates over identically either way.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone

from ..commodities.base import BaseActiveModule


class Afk(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_command("all", "afk", "MEMBER")
        self.register_module("afk")
        self.register_event("privgroup")
        self.register_event("gmsg", "org")
        self.register_event("buddy")

        self.help["description"] = "Shows other players that you are afk."
        self.help["command"] = {"afk <message>": "Sets you afk with <message>"}
        self.help["notes"] = (
            "This command does not affect nor is it affected by the in-game command /afk."
        )

        settings = self.bot.core("settings")
        settings.create("Afk", "Alias", True, "Should Alias's be used with AFK?")
        settings.create("Afk", "noprefix", False, "Can no prefix with AFK be used to go AFK?")
        settings.create("Afk", "brb_noprefix", False, "Can no prefix with BRB be used to go AFK?")
        self.register_alias("afk", "brb")

        self.afk: dict[str, dict[str, object]] = {}
        self.afkalias: dict[str, str] = {}
        self.afkmsgs: dict[str, list[tuple[float, str, str]]] = {}

    # -- command -------------------------------------------------------------
    def command_handler(self, name, msg, origin):
        self.error.reset()
        _, _, args = msg.partition(" ")
        self.gone(name, args)
        return f"##highlight##{name}##end## is now AFK."

    # -- passive chat listeners (PHP: privgroup()/gmsg()) ---------------------
    def privgroup(self, name, msg) -> None:
        if self.acheck(name):
            timegone = self.afk_time(name)
            self.back(name)
            msgs = self.msgs(name) or ""
            self.bot.send_output(name, f"{name} is back. AFK for ({timegone})  {msgs}", "both")

        settings = self.bot.core("settings")
        if settings.get("Afk", "noprefix"):
            match = re.match(r"^afk (.*)", msg, re.I)
            if match:
                self.gone(name, match.group(1))
                self.bot.send_output(name, f"{name} is now AFK.", "both")
            elif re.match(r"^afk", msg, re.I):
                self.gone(name)
                self.bot.send_output(name, f"{name} is now AFK.", "both")
        elif settings.get("Afk", "brb_noprefix"):
            match = re.match(r"^brb (.*)", msg, re.I)
            if match:
                self.gone(name, match.group(1))
                self.bot.send_output(name, f"{name} is now AFK.", "both")
            elif re.match(r"^brb", msg, re.I):
                self.gone(name, "")
                self.bot.send_output(name, f"{name} is now AFK.", "both")

        msgcheck = None
        if self.afk:
            msgcheck = self.msg_check(name, "", msg)
        if msgcheck:
            self.bot.send_pgroup(msgcheck)

    def gmsg(self, name, group, msg) -> None:
        if self.acheck(name):
            timegone = self.afk_time(name)
            self.back(name)
            msgs = self.msgs(name) or ""
            self.bot.send_output(name, f"{name} is back. AFK for ({timegone}) {msgs}", "both")

        settings = self.bot.core("settings")
        if settings.get("Afk", "noprefix"):
            match = re.match(r"^afk (.*)", msg, re.I)
            if match:
                self.gone(name, match.group(1))
                self.bot.send_output(name, f"##highlight##{name}##end## is now AFK.", "both")
                return
            if re.match(r"^afk", msg, re.I):
                self.gone(name)
                self.bot.send_output(name, f"##highlight##{name}##end## is now AFK.", "both")
                return
        elif settings.get("Afk", "brb_noprefix"):
            match = re.match(r"^brb (.*)", msg, re.I)
            if match:
                self.gone(name, match.group(1))
                self.bot.send_output(name, f"##highlight##{name}##end## is now AFK.", "both")
            elif re.match(r"^brb", msg, re.I):
                self.gone(name, "")
                self.bot.send_output(name, f"##highlight##{name}##end## is now AFK.", "both")

        msgcheck = None
        if self.afk:
            msgcheck = self.msg_check(name, group, msg)
        if msgcheck:
            self.bot.send_gc(msgcheck)

    # -- matching/lookup -------------------------------------------------------
    def msg_check(self, name, group, msg):
        for key, value in self.afk.items():
            if re.search(rf"{re.escape(key)}\b", msg, re.I):
                self.afkmsgs.setdefault(key, []).append((time.time(), name, msg))
                return f"{key} has been AFK for {self.afk_time(key)} ({value['msg']})."
        if self.bot.core("settings").get("Afk", "Alias"):
            for key2, value in self.afkalias.items():
                if re.search(rf"{re.escape(key2)}\b", msg, re.I):
                    self.afkmsgs.setdefault(value, []).append((time.time(), name, msg))
                    return f"{value} has been AFK for {self.afk_time(value)} ({self.afk[value]['msg']})."
        return False

    def afk_time(self, name) -> str:
        dif = time.time() - self.afk[name]["time"]
        if dif < 60:
            return f"{int(dif)} Seconds"
        if dif < 3600:
            mins = int(dif // 60)
            return f"{mins} Minutes"
        mins = int(dif // 60)
        hours = mins // 60
        minsrem = mins - hours * 60
        return f"{hours} Hours and {minsrem} Minutes"

    # -- state mutation ---------------------------------------------------------
    def gone(self, name, msg=False) -> None:
        if not msg:
            msg = "Away from keyboard"
        self.afk[name] = {"time": time.time(), "msg": msg}

        alts = self.bot.core("alts")
        main = alts.main(name)
        for alt in alts.get_alts(main) or []:
            self.afkalias[alt] = name

        if self.bot.core("settings").get("Afk", "Alias"):
            aliases = getattr(self.bot.core("alias"), "alias", None) or {}
            for alias, nickname in aliases.items():
                if main == nickname:
                    self.afkalias[alias] = name

    def back(self, name) -> None:
        if name in self.afk:
            del self.afk[name]
            for key in [k for k, v in self.afkalias.items() if v == name]:
                del self.afkalias[key]

    def acheck(self, name) -> bool:
        return bool(name) and name in self.afk

    # -- buddy (logon/logoff) event (PHP: buddy($name, $msg)) -------------------
    def buddy(self, name, msg) -> None:
        access = self.bot.core("security").get_access_level(name)
        if msg == 5 and access > 1:
            if self.acheck(name):
                self.back(name)
                msgs = self.msgs(name) or ""
                if str(self.bot.game).lower() == "ao":
                    self.bot.send_tell(name, f"you have been set as back. {msgs}")
        elif msg == 3 and access > 1:
            if not self.acheck(name):
                self.gone(name)
                msgs = self.msgs(name) or ""
                if str(self.bot.game).lower() == "ao":
                    self.bot.send_tell(name, f"you have been set as AFK. {msgs}")
        elif msg == 0:
            if self.acheck(name):
                self.back(name)
                msgs = self.msgs(name) or ""
                self.bot.send_tell(name, f"you have been set as back. (Logoff) {msgs}")

    def msgs(self, name):
        entries = self.afkmsgs.get(name)
        if entries:
            inside = "##blob_title##..:: AFK Messages ::..##end##\n\n"
            count = 0
            for timestamp, sender, msg in entries:
                time_str = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                inside += (
                    f"##green##{time_str}##end##  ##orange##{sender}##end##\n"
                    f"        ##blob_text##{msg}##end##\n\n"
                )
                count += 1
            result = f"##highlight##{count}##end## Messages :: " + self.bot.core("tools").make_blob(
                "click to view", inside
            )
            self.afkmsgs.pop(name, None)
            return result
        self.afkmsgs.pop(name, None)
        return False
