"""Ported from Modules/Quotes.php (class `Quotes`).

Lets players add/browse/search a shared quote board (`quotes`, `quotes
add`, `quotes search`, `quotes by`, `quotes rem/remove/del/delete`),
persisted in `#___quotes`. Depends on the already-ported `core("tools")`
(`my_rand()` for the random-quote pick, `make_blob()` for the search/by
result blobs).

Scope notes / intentional deviations from the PHP:
  * `add_quote()`'s `mb_detect_encoding()`/`mb_convert_encoding()` dance
    (re-encoding the quote text to UTF-8 if it wasn't already) has no
    equivalent here -- Python `str` is already Unicode, so there is
    nothing to convert.
  * `command_handler()` in the PHP manually calls `$this->bot->send_output()`
    (and, for `origin == 'gc'`, `$this->bot->send_irc()`) in every branch
    instead of just `return`ing the message for the base class's own
    reply mechanism to send. This is preserved here (`command_handler()`
    calls `self.bot.send_output()` itself and returns `None`) since the
    IRC bridge is a documented no-op (`Bot.send_irc()`) anyway -- there is
    no behavioral difference either way, but this keeps the port
    line-for-line faithful to the original dispatch shape.
  * The `del`/`remove`/`rem`/`delete` branch's `origin == 'gc'` case called
    `del_quote()` a *second* time (discarding the message, only to feed it
    to the no-op `send_irc()`). Since `send_irc()` does nothing in this
    port, the second (redundant, and potentially double-deleting) call is
    dropped -- the already-computed message is reused instead.
  * `send_quote(-1)`'s random-pick loop is preserved as-is, including its
    latent quirk: it rolls `my_rand(0, highest_id)` and uses that number as
    a *positional* index into the full, unfiltered result set (not a
    lookup by id), retrying until it lands on a populated slot. If quotes
    have been deleted (leaving gaps in the id sequence), this biases
    toward lower-id quotes and can require several retries -- this is
    exactly how Modules/Quotes.php behaves, not a Python-side bug.
"""
from __future__ import annotations

import re

from ..commodities.base import BaseActiveModule


class Quotes(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_command("all", "quotes", "MEMBER")
        self.register_module("quotes")
        self.register_alias("quotes", "quote")

        db = bot.db
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('quotes', False)} "
            "(id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, quote BLOB, contributor VARCHAR(15))"
        )

        self.help["description"] = "Immortalize your friends and enemies."
        self.help["command"] = {
            "quotes": "Display a random quote from the database.",
            "quotes #": "Display quote number # from the database.",
            "quotes search text": "Search the databases for quotes with text.",
            "quotes by name": "Search the databases for quotes by name.",
            "quotes add text": "Add text to the quotes databases.",
            "quotes rem #": "Remove quote number # from the database.",
            "quotes remove #": "Remove quote number # from the database.",
            "quotes del #": "Remove quote number # from the database.",
            "quotes delete #": "Remove quote number # from the database.",
        }

    # -- dispatch ---------------------------------------------------------------
    def command_handler(self, name, msg, origin):
        match = re.match(r"^quotes ([0-9]+)$", msg, re.I)
        if match:
            reply = self.send_quote(int(match.group(1)))
        else:
            match = re.match(r"^quotes add (.+)$", msg, re.I)
            if match:
                reply = self.add_quote(match.group(1), name)
            else:
                match = re.match(r"^quotes (remove|del|rem|delete) ([0-9]+)$", msg, re.I)
                if match:
                    reply = self.del_quote(int(match.group(2)))
                else:
                    match = re.match(r"^quotes search (.+)$", msg, re.I)
                    if match:
                        reply = self.search_quote(match.group(1))
                    else:
                        match = re.match(r"^quotes by (.+)$", msg, re.I)
                        if match:
                            reply = self.by_quote(match.group(1))
                        else:
                            reply = self.send_quote(-1)

        self.bot.send_output(name, reply, origin)
        if origin == "gc":
            self.bot.send_irc("", "", reply)
        return None

    # -- mutation -----------------------------------------------------------------
    def add_quote(self, strquote: str, name: str) -> str:
        db = self.bot.db
        db.query(
            f"INSERT INTO #___quotes (quote, contributor) VALUES "
            f"('{db.real_escape_string(strquote)}', '{db.real_escape_string(name)}')"
        )
        num = db.select("SELECT id FROM #___quotes ORDER BY id DESC")
        return f"Thank you, your quote has been added as id #{num[0][0]}"

    def del_quote(self, qnum: int) -> str:
        db = self.bot.db
        result = db.select(f"SELECT * FROM #___quotes WHERE id={qnum}")
        if result:
            db.query(f"DELETE FROM #___quotes WHERE id={qnum}")
            return "Quote removed."
        num = db.select("SELECT id FROM #___quotes ORDER BY id DESC")
        highest = num[0][0] if num else 0
        return f"Quote with id of {qnum} not found. (Highest quote ID is {highest}.)"

    # -- views ----------------------------------------------------------------------
    def send_quote(self, qnum: int) -> str:
        db = self.bot.db
        if qnum == -1:
            num = db.select("SELECT id FROM #___quotes ORDER BY id DESC")
            result = db.select("SELECT * FROM #___quotes")
            if not result:
                return "No quotes exist. Add some!"
            highest = num[0][0]
            tools = self.bot.core("tools")
            found = False
            strquote = ""
            while not found:
                row = tools.my_rand(0, highest)
                if row < len(result) and result[row][0]:
                    strquote = f"#{result[row][0]} - {result[row][1]} [By: {result[row][2]}]"
                    found = True
            return strquote

        result = db.select(f"SELECT * FROM #___quotes WHERE id={qnum}")
        if result:
            return f"#{result[0][0]} - {result[0][1]} [By: {result[0][2]}]"
        num = db.select("SELECT id FROM #___quotes ORDER BY id DESC")
        highest = num[0][0] if num else 0
        return f"Quote with id of {qnum} not found. (Highest quote ID is {highest}.)"

    def search_quote(self, qtext: str) -> str:
        db = self.bot.db
        searchs = db.select(f"SELECT * FROM #___quotes WHERE quote LIKE '%{qtext}%'") or []
        if not searchs:
            return "No quotes found with such keyword!"
        result = "".join(f"#{s[0]} - {s[1]} [By: {s[2]}]\n" for s in searchs)
        blob = self.bot.core("tools").make_blob("click to view", result)
        return f"{len(searchs)} quote(s) with keyword {blob}"

    def by_quote(self, qname: str) -> str:
        db = self.bot.db
        capname = qname[:1].upper() + qname[1:] if qname else qname
        bys = db.select(f"SELECT * FROM #___quotes WHERE contributor = '{capname}'") or []
        if not bys:
            return "No quotes found by such username!"
        result = "".join(f"#{b[0]} - {b[1]} [By: {b[2]}]\n" for b in bys)
        blob = self.bot.core("tools").make_blob("click to view", result)
        return f"{len(bys)} quote(s) by username : {blob}"
