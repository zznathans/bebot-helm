"""Ported from Modules/Notify.php (class `Notify`).

IMPORTANT NAME COLLISION NOTE: this file is deliberately named
`notify_ui.py` and registers as `"notify_ui"`, *not* `"notify"` --
`main_modules/notify.py` (ported from Main/15_Notify.php, a different
file: the in-memory notify-list cache/DB layer) already owns the
`"notify"` module name and is this module's `core("notify")` dependency
for the actual add/delete/check/cache logic. Mirrors the PHP: `Notify.php`
(this file, a chat-command UI) called `$this->bot->core("notify")->...`
throughout, which was Main/15_Notify.php's `Notify` class -- two
same-named PHP classes only worked there because one lived in `Main/` and
was loaded first while the other overwrote nothing at the chat-command
level. That can't carry over 1:1 to Python module names, hence the
rename.

Scope notes / intentional deviations from the PHP:
  * `notify del($user)` -> `core("notify").delete(user)`. The ported
    `main_modules/notify.py` method is named `delete()` (`del` is a
    Python keyword and can't be a method name), so `del_notify()` below
    calls that instead of a same-named `del()`.
  * `over_notify()` (the AOC-only multi-bot-slave notify/friendlist
    overflow relay, gated on `strtolower($this->bot->game)=="aoc"` and
    `$this->bot->slave`) is not ported: this codebase's `Bot.game` is
    always `"Ao"` (see bot.py) and there is no `bot.slave` /
    multi-instance relay concept anywhere in this port, so the `over`
    subcommand falls through to the same "Unknown Sub Command" response
    as any other unrecognized subcommand instead of being a no-op stub.
  * `parse_com()` (no Python equivalent ported) is replaced with plain
    string splitting on whitespace, same approach used by every other
    ported *Ui module in this codebase.
"""
from __future__ import annotations

from ..commodities.base import BaseActiveModule


class NotifyUi(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("notify_ui")
        self.register_command("all", "notify", "ADMIN")
        self.help["description"] = "Handling of notify list."
        self.help["command"] = {}
        self.help["command"]["notify"] = "Shows the full notify list (can spam if many buddies ...)."
        self.help["command"]["notify count"] = "Shows the notify list count (no spam if many buddies)."
        self.help["command"]["notify on <player>"] = "Adds <player> to the notify list."
        self.help["command"]["notify off <player>"] = "Removes <player> of the notify list."
        self.help["command"]["notify cache"] = "Lists all players on the notify list."
        self.help["command"]["notify cache clear"] = "Removes all players on the notify list."
        self.help["command"]["notify cache update"] = "Updates the notify cache with the latest players on the notify list."

    def command_handler(self, name, msg, origin):
        parts = msg.split(" ", 2)
        sub_raw = parts[1] if len(parts) > 1 else ""
        sub = sub_raw.lower()
        arg = parts[2] if len(parts) > 2 else ""

        if sub == "on":
            return self.add_notify(name, arg)
        if sub == "off":
            return self.del_notify(arg)
        if sub == "check":
            if self.bot.core("notify").check(arg):
                return f"{arg} is in notify list."
            return f"{arg} is not in notify list."
        if sub == "cache":
            arg_l = arg.lower()
            if arg_l == "clear":
                return self.bot.core("notify").clear_cache()
            if arg_l == "update":
                self.bot.core("notify").update_cache()
                return "Updating notify cache."
            return self.bot.core("notify").list_cache()
        if sub == "count":
            return self.show_notify_count()
        if sub in ("list", ""):
            return self.show_notify_list()
        if arg.lower() in ("on", "off"):
            # assume they want to turn notify on or off but did wrong order
            return self.command_handler(name, f"notify {arg} {sub_raw}", origin)
        return f"##error##Error: Unknown Sub Command ##highlight##{sub}##end####end##"

    def show_notify_count(self) -> str:
        result = self.bot.db.select("SELECT COUNT(*) FROM #___users WHERE notify = 1")
        count = result[0][0] if result else 0
        return f"{count} player(s) currently in notify list."

    def show_notify_list(self) -> str:
        notlist = self.bot.db.select(
            "SELECT nickname, user_level FROM #___users WHERE notify = 1 ORDER BY nickname"
        ) or []
        if not notlist:
            return "Nobody on notify!"
        guestcount = 0
        membercount = 0
        othercount = 0
        total = 0
        tools = self.bot.core("tools")
        colors = self.bot.core("colors")
        guest = f"##blob_title## ::: All guests on notify for {self.bot.botname} :::##end##\n"
        member = f"##blob_title## ::: All members on notify for {self.bot.botname} :::##end##\n"
        other = f"##blob_title## ::: All others on notify for {self.bot.botname} ::: ##end##\n"
        for nickname, user_level in notlist:
            blob = "\n• " + nickname + " " + tools.chatcmd(f"notify off {nickname}", "[x]")
            blob = colors.colorize("blob_text", blob)
            if user_level >= 2:
                member += blob
                membercount += 1
            elif user_level == 1:
                guest += blob
                guestcount += 1
            else:
                other += blob
                othercount += 1
            total += 1
        return (
            f"{total} Characters on notify: "
            + tools.make_blob(f"{membercount} Member", member) + ", "
            + tools.make_blob(f"{guestcount} Guests", guest) + ", "
            + tools.make_blob(f"{othercount} Others", other)
        )

    def add_notify(self, source, user):
        return self.bot.core("notify").add(source, user)

    def del_notify(self, user):
        return self.bot.core("notify").delete(user)
