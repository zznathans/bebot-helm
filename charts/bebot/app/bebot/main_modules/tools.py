"""Ported (reduced) from Main/14_Tools.php.

The proxy/curl/socket HTTP helpers (get_site/multi_site/post_site, used
for web lookups and the AO self-defreeze workaround) are not ported --
network scraping helpers for optional features, not needed to run.
"""
from __future__ import annotations

import random

from ..commodities.base import BasePassiveModule


class Tools(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("tools")

    def chatcmd(self, link: str, title: str, origin=False, strip: bool = False) -> str:
        origin = str(origin).lower() if origin else origin
        if origin in ("gc", "o", "gu", "3"):
            cmd = "o <pre>"
        elif origin in ("pgmsg", "pg", "2"):
            cmd = f"group {self.bot.botname} <pre>"
        elif origin == "start":
            cmd = "start "
        elif origin in ("tell", "0", "1", False, None):
            cmd = f"tell {self.bot.botname} <pre>"
        elif origin == "/":
            cmd = ""
        else:
            cmd = f"{origin} "
        style = "style=text-decoration:none " if strip else ""
        return f"<a {style}href='chatcmd:///{cmd}{link}'>{title}</a>"

    def make_blob(self, title: str, content: str, header: bool = True) -> str:
        inside = ""
        if header:
            inside += (
                "##blob_title##:::::::::::##end## ##blob_text##BeBot Client Terminal##end## "
                "##blob_title##::::::::::::##end##\n"
            )
            inside += self.chatcmd("about", " ##blob_text##About##end## ", False, True) + "     "
            if title != "MassMsg":
                inside += self.chatcmd("help", " ##blob_text##Help##end## ", False, True) + "     "
            inside += self.chatcmd("close InfoView", " ##blob_text##Close Terminal##end## ", "/", True)
            inside += "\n____________________________________\n"
        content = content.replace('="', "='").replace('">', "'>").replace('"', "&quot;")
        inside += content
        return f'<a href="text://{inside}">{title}</a>'

    def make_item(self, lowid, highid, ql, name: str, alt: bool = False, strip: bool = False) -> str:
        style = "style=text-decoration:none " if strip else ""
        quote = "'" if alt else '"'
        name = name.replace("'", "&#039;")
        return f"<a {style}href={quote}itemref://{lowid}/{highid}/{ql}{quote}>{name}</a>"

    def sanitize_player(self, name: str) -> str:
        import re
        return re.sub(r"[^a-z0-9\-]", "", name or "", flags=re.I).strip().capitalize()

    def my_rand(self, min_val=None, max_val=None) -> int:
        if min_val is None:
            return random.randint(0, 2**31 - 1)
        return random.randint(min_val, max_val)

    def compare(self, a, b) -> bool:
        return a == b

    def best_match(self, find: str, candidates, threshold: int = 0):
        import difflib
        best = (0, None)
        for candidate in candidates:
            ratio = difflib.SequenceMatcher(None, find, candidate).ratio() * 100
            if ratio >= threshold and ratio > best[0]:
                best = (ratio, candidate)
        return best
