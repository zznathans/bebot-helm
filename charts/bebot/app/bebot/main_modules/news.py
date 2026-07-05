"""Ported from Modules/News.php (class `News`).

Chat-command UI + storage for headlines/news/raid announcements, built on
the already-ported `core("settings")` (who may delete headlines/news),
`core("prefs")` (per-user "what to spam on logon/pgjoin" preference),
`core("security")` (delete-permission checks), and `core("tools")`
(chatcmd/make_blob). Registers for the `logon_notify` and `pgjoin` events
(dispatched by `Bot.register_event` straight to `notify(name, startup)` /
`pgjoin(name)`, matching main_modules/logon_notifies.py's and
main_modules/auto_user_add.py's established contract for those two events).

Scope notes / intentional deviations from the PHP:
  * The schema-version bump (`get_version("news") < 2` -> `ALTER TABLE ...
    MODIFY COLUMN Name VARCHAR(255)`) is dropped, matching the precedent set
    throughout this port (settings.py, preferences.py, player_notes.py): the
    table is always created directly with the final schema (`name
    VARCHAR(255)`) instead of migrating an older layout forward.
  * `mb_detect_encoding()`/`mb_convert_encoding()` (UTF-8 <-> ISO-8859-1
    juggling for PHP's non-unicode string internals) and the matching
    `stripslashes()` on read (undoing `addslashes()` from `set_news()`) are
    both dropped. Python 3 strings are unicode natively, and this port uses
    `db.real_escape_string()` for SQL-safety on insert (see
    preferences.py/player_notes.py) rather than `addslashes()`, so there are
    no slashes to strip back out on read.
  * `get_news()` faithfully reproduces a genuine bug in the PHP: the
    "News last updated <date>" header's `$newsdate` is only ever set inside
    `if (!empty($result))`, but at that point in the function `$result` has
    never been assigned (the headline query result is stored in
    `$result_headline`, not `$result`) -- so `$newsdate` is always the empty
    string and the header always renders as "News last updated :: ...".
    This is harmless (cosmetic only, the news blob itself is unaffected) so
    it's preserved as-is rather than silently "fixed", matching this
    codebase's precedent for inert-but-faithful PHP quirks (see
    settings_ui.py, player_notes_ui.py). `get_raids()`'s equivalent
    `$newsdate`, which *is* assigned from its own query's result in the
    original, is ported working correctly.
  * `del_news()` only ever checks the `News/News_del` setting, never
    `News/Headline_del`, even when deleting via "headline del <id>" --
    this matches the PHP exactly (`sub_handler()`'s `del`/`rem` branch calls
    `del_news($name, $com['args'])` without forwarding `$type` at all), so
    it's preserved rather than "fixed" to check the type-appropriate
    setting.
  * `gmdate($FormatString, ...)` timestamp rendering uses a fixed
    `"%Y-%m-%d %H:%M:%S"` UTC format instead, matching the precedent already
    established in player_notes_ui.py (nothing in this port consumes the
    `Time/FormatString` setting yet).
  * Command-string parsing (`parse_com()` in the PHP base class, which also
    does item-link substitution via `core("items")`) is replaced with plain
    `str.split()`, matching the convention used throughout this port
    (player_notes_ui.py, etc.) -- no `items` module exists in this codebase.
"""
from __future__ import annotations

import time

from ..commodities.base import BaseActiveModule


def _fmt_time(ts) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts))


class News(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        db = bot.db
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('news', True)} "
            "(id INT NOT NULL auto_increment PRIMARY KEY, type INT default '1', "
            "time INT NOT NULL default '0', name VARCHAR(255) default NULL, news TEXT)"
        )
        self.register_module("news")

        self.register_command("all", "news", "GUEST", {"add": "MEMBER"})
        self.register_command("all", "headline", "GUEST", {"add": "ADMIN"})
        self.register_command("all", "raids", "MEMBER", {"add": "LEADER", "del": "LEADER"})
        self.register_event("logon_notify")
        self.register_event("pgjoin")

        # These are required in order to let authors delete their own messages but not everyones.
        self.bot.core("settings").create(
            "News", "Headline_Del", "ADMIN", "Who should be able to delete headlines",
            "ADMIN;LEADER;MEMBER;GUEST;ANONYMOUS",
        )
        self.bot.core("settings").create(
            "News", "News_Del", "ADMIN", "Who should be able to delete news",
            "ADMIN;LEADER;MEMBER;GUEST;ANONYMOUS",
        )
        self.bot.core("prefs").create(
            "News", "Logonspam", "What should news spam when logging on?", "Last_headline",
            "Last_headline;Link;Nothing",
        )
        self.bot.core("prefs").create(
            "News", "PGjoinspam", "What should news spam when joining private group?", "Nothing",
            "Last_headline;Link;Nothing",
        )

        self.help["description"] = "Sets and shows headlines, news and raid events."
        self.help["command"] = {
            "news": "Shows current headlines and news",
            "raids": "Shows current raid events",
            "headline add <newsitem>": "Adds <newsitem> to current news. ",
            "news add <newsitem>": "Adds <newsitem> to current news. ",
            "raids add <newsitem>": "Adds <newsitem> to current raids. ",
        }
        self.help["notes"] = "The deletion of headlines, news and raids are managed by the GUI."

    # -- logon_notify / pgjoin event handlers ------------------------------------

    def notify(self, name, startup: bool = False) -> None:
        if startup:
            return
        setting = self.bot.core("prefs").get(name, "News", "Logonspam")
        spam = ""
        if setting == "Last_headline":
            spam += self.get_last_headline() or ""
            spam += self.get_news(name)
        elif setting == "Link":
            spam += self.get_news(name)
        else:
            return
        if spam != "No news.":
            self.bot.send_output(name, spam, "tell")

    def pgjoin(self, name) -> None:
        setting = self.bot.core("prefs").get(name, "News", "PGjoinspam")
        spam = ""
        if setting == "Last_headline":
            spam += self.get_last_headline() or ""
            spam += self.get_news(name)
        elif setting == "Link":
            spam += self.get_news(name)
        else:
            return
        if spam != "No news.":
            self.bot.send_output(name, spam, "tell")

    # -- dispatch ---------------------------------------------------------------

    def command_handler(self, name, msg, origin):
        parts = msg.split(" ", 2)
        com = parts[0]
        sub = parts[1] if len(parts) > 1 else ""
        args = parts[2] if len(parts) > 2 else ""
        if com == "news":
            return self.sub_handler(name, sub, args, 1)
        if com == "headline":
            return self.sub_handler(name, sub, args, 2)
        if com == "raids":
            return self.sub_handler(name, sub, args, 3)
        self.error.set(f"News received unknown command '{com}'.")
        return self.error

    def sub_handler(self, name, sub, args, news_type):
        if sub in ("", "read"):
            if news_type in (1, 2):
                return self.get_news(name)
            return self.get_raids(name)
        if sub == "add":
            return self.set_news(name, args, news_type)
        if sub in ("del", "rem"):
            return self.del_news(name, args)
        # No keyword recognized. Assume the person is attempting to add news
        # and forgot the "add" keyword.
        news = f"{sub} {args}"
        return self.set_news(name, news, news_type)

    # -- reads --------------------------------------------------------------------

    def get_news(self, name) -> str:
        db = self.bot.db
        settings = self.bot.core("settings")
        security = self.bot.core("security")
        tools = self.bot.core("tools")
        newsdate = ""
        inside = ""

        result_headline = db.select(
            "SELECT id, time, name, news FROM #___news WHERE type = '2' ORDER BY time DESC LIMIT 0, 3"
        ) or []
        if result_headline:
            inside = "<center>##ao_infoheadline##:::: Headline ::::##end##</center>\n"
            for hid, htime, hname, htext in result_headline:
                inside += (
                    f"##ao_infoheader##On {_fmt_time(htime)} GMT ##ao_cctext##{hname}##end## Reported:\n"
                )
                inside += f"##ao_infotext##{htext}"
                if security.check_access(name, settings.get("News", "Headline_del")) or name == hname:
                    inside += " [" + tools.chatcmd(f"headline del {hid}", "Delete") + "]"
                inside += "\n\n"

        result = db.select(
            "SELECT id, time, name, news FROM #___news WHERE type = '1' ORDER BY time DESC LIMIT 0, 10"
        ) or []
        if result:
            inside += "<center>##ao_infoheadline##:::: News ::::##end##</center>\n"
            for nid, ntime, nname, ntext in result:
                inside += (
                    f"##ao_infoheader##On {_fmt_time(ntime)} GMT ##ao_cctext##{nname}##end## Reported:\n"
                )
                inside += f"##ao_infotext##{ntext}"
                if security.check_access(name, settings.get("News", "News_del")) or name == nname:
                    inside += " [" + tools.chatcmd(f"news del {nid}", "Delete") + "]"
                inside += "\n\n"

        if inside:
            return f"News last updated {newsdate}:: " + tools.make_blob("click to view", inside)
        return "No news."

    def get_last_headline(self):
        rows = self.bot.db.select(
            "SELECT name, news FROM #___news WHERE type = '2' ORDER BY time DESC LIMIT 1"
        ) or []
        if not rows:
            return False
        hname, htext = rows[0][0], rows[0][1]
        return f"{hname}:##highlight## {htext}##end##\n"

    def get_raids(self, name) -> str:
        db = self.bot.db
        settings = self.bot.core("settings")
        security = self.bot.core("security")
        tools = self.bot.core("tools")
        newsdate = ""
        inside = "<center>##ao_infoheadline##:::: Planned Raids ::::##end##</center>\n"

        result = db.select(
            "SELECT id, time FROM #___news WHERE type = '3' ORDER BY id DESC LIMIT 0, 1"
        ) or []
        if result:
            newsdate = _fmt_time(result[0][1])

        result_raids = db.select(
            "SELECT id, time, name, news FROM #___news WHERE type = '3' ORDER BY time DESC LIMIT 0, 10"
        ) or []
        for rid, rtime, rname, rtext in result_raids:
            inside += f"##ao_infoheader##{_fmt_time(rtime)} GMT ##ao_cctext##{rname}##end## wrote:\n"
            inside += f" ##ao_infotext##{rtext}"
            if security.check_access(name, settings.get("News", "News_del")) or name == rname:
                inside += " [" + tools.chatcmd(f"raids del {rid}", "Delete") + "]"
            inside += "\n\n"

        return f"Planned Raids last updated {newsdate}:: " + tools.make_blob("click to view", inside)

    # -- writes -------------------------------------------------------------------

    def set_news(self, name, msg, news_type) -> str:
        db = self.bot.db
        m, n = db.real_escape_string(msg), db.real_escape_string(name)
        db.query(
            f"INSERT INTO #___news (type, time, name, news) VALUES "
            f"('{news_type}', {int(time.time())}, '{n}', '{m}')"
        )
        return "Your entry has been submitted."

    def del_news(self, name, msg):
        db = self.bot.db
        entry_id = db.real_escape_string(str(msg).strip())
        result = db.select(f"SELECT name FROM #___news WHERE id = '{entry_id}'") or []
        if not result:
            self.error.set(f"No entry with id '{msg}' found.")
            return self.error
        res_name = result[0][0]
        del_level = self.bot.core("settings").get("News", "News_del")
        if self.bot.core("security").check_access(name, del_level) or name == res_name:
            db.query(f"DELETE FROM #___news WHERE id = '{entry_id}'")
            return "Entry has been removed."
        self.error.set(f"You must be {del_level} or higher or own the entry to delete news")
        return self.error
