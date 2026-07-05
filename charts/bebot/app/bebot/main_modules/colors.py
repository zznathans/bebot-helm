"""Ported (reduced) from Main/15_Colors.php.

The DB-backed color/scheme/theme-file system (#___colors, #___color_schemes,
Themes/*.colors.xml, the in-game theme editor) is not ported -- this uses a
single fixed built-in palette instead. The tag-parsing algorithm
(`parse()`) that every send_tell/send_gc/send_pgroup call depends on is
ported faithfully.
"""
from __future__ import annotations

import re

from ..commodities.base import BasePassiveModule

DEFAULT_TAGS = {
    "##normal##": "<font color=#C3C3C3>",
    "##highlight##": "<font color=#FFFFFF>",
    "##error##": "<font color=#FF0000>",
    "##warning##": "<font color=#FFFF00>",
    "##blob_title##": "<font color=#FFFFFF>",
    "##blob_text##": "<font color=#C3C3C3>",
    "##orange##": "<font color=#FCA712>",
    "##yellow##": "<font color=#FFFF00>",
    "##white##": "<font color=#FFFFFF>",
    "##end##": "</font>",
}


class Colors(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("colors")
        self.color_tags = dict(DEFAULT_TAGS)

    def get(self, color: str) -> str:
        return self.color_tags.get(f"##{color}##", "<font color=#000000>")

    def colorize(self, color: str, text: str) -> str:
        tag = self.color_tags.get(f"##{color}##")
        if tag:
            return f"{tag}{text}</font>"
        return text

    def parse(self, text: str) -> str:
        if "##" not in text:
            return text
        stop = "##end##"
        trig = r"(?:(?!#{2}).)+"
        for _ in range(3):
            for tag, font in self.color_tags.items():
                if tag == stop:
                    continue
                pattern = re.compile(f"({re.escape(tag)}{trig}{re.escape(stop)})", re.I)
                while True:
                    match = pattern.search(text)
                    if not match:
                        break
                    replacement = re.sub(re.escape(tag), font, match.group(1), count=1, flags=re.I)
                    replacement = re.sub(re.escape(stop), "</font>", replacement, count=1, flags=re.I)
                    text = text[: match.start()] + replacement + text[match.end():]
        text = re.sub(r"##[^#]+##", "", text, flags=re.I)
        return text
