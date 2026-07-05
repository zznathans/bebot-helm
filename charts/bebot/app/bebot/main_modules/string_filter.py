"""Ported (reduced) from Core/StringFilter.php.

Performs simple text filtering (usable as a word censor, disabled by
default via the "Filter"/"Enabled" setting -- note the setting is created
but, matching the PHP original, is never actually consulted by
output_filter()/input_filter() themselves) plus an optional "fun mode"
output garbler (rot13/chef/eleet/fudd/pirate/nofont) delegated to
`bot.core("funfilters")`.

Schema-version migration is dropped, matching the precedent already
established in main_modules/settings.py and player_notes.py: the
string_filter table is created directly with its (only ever) schema
instead of migrating an older layout forward.
"""
from __future__ import annotations

import re

from ..commodities.base import BasePassiveModule, BotError


class StringFilter(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        db = bot.db
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('string_filter', True)} "
            "(search varchar(255) NOT NULL, "
            "new VARCHAR(255) NOT NULL DEFAULT '**bleep**', "
            "PRIMARY KEY (search))"
        )
        self.register_module("stringfilter")
        self.register_event("connect")
        self.stringlist: dict[str, str] = {}
        self.bot.core("settings").create(
            "Filter", "Enabled", False, "Enable bot output text filter.", "On;Off", False, 1
        )
        self.bot.core("settings").create(
            "Filter",
            "Funmode",
            "off",
            "Select a fun bot output filter. (See documentation)",
            "off;chef;eleet;fudd;pirate;nofont;",
            False,
            10,
        )

    def connect(self) -> None:
        self.get_strings(True)

    def output_filter(self, text: str) -> str:
        for search, new in self.stringlist.items():
            text = re.sub(search, new, text, flags=re.IGNORECASE)
        if self.bot.core("settings").get("Filter", "Funmode") != "off":
            text = self.funmode(text, self.bot.core("settings").get("Filter", "Funmode"))
        return text

    def input_filter(self, text: str) -> str:
        # This function can be used to filter input against the string list.
        for search, new in self.stringlist.items():
            text = re.sub(search, new, text, flags=re.IGNORECASE)
        return text

    def get_strings(self, update: bool = False) -> dict[str, str] | bool:
        if update:
            rows = self.bot.db.select("SELECT search, new FROM #___string_filter")
            if not rows:
                return False
            for search, new in rows:
                self.stringlist[search] = new
        return self.stringlist

    def add_string(self, search: str, new: str | None = None) -> str | BotError:
        db = self.bot.db
        search = db.real_escape_string(search.lower())
        if search in self.stringlist:
            self.error.set(f"The string '{search}' is already on the filtered word list.")
            return self.error
        if new is not None:
            new = db.real_escape_string(new.lower())
            sql = f"INSERT INTO #___string_filter (search, new) VALUES ('{search}', '{new}')"
        else:
            sql = f"INSERT INTO #___string_filter (search) VALUES ('{search}')"
            new = "**bleep**"
        db.query(sql)
        self.stringlist[search] = new
        return f"Added '{search}' to the filterd string list. It will be replaced with '{new}'"

    def rem_string(self, search: str) -> str | BotError:
        db = self.bot.db
        search = db.real_escape_string(search.lower())
        if search in self.stringlist:
            del self.stringlist[search]
            db.query(f"DELETE FROM #___string_filter WHERE search = '{search}'")
            return f"Removed {search} from the filtered string list."
        self.error.set(f"{search} is not on the filtered string list.")
        return self.error

    def funmode(self, text: str, filter_: str) -> str:
        filter_ = filter_.lower()
        funfilters = self.bot.core("funfilters")
        if filter_ == "rot13":
            return funfilters.rot13(text)
        if filter_ == "chef":
            return funfilters.chef(text)
        if filter_ == "eleet":
            return funfilters.eleet(text)
        if filter_ == "fudd":
            return funfilters.fudd(text)
        if filter_ == "pirate":
            return funfilters.pirate(text)
        if filter_ == "nofont":
            return funfilters.nofont(text)
        self.bot.log("FILTER", "ERROR", f"{filter_} is not a valid fun mode.")
        return text
