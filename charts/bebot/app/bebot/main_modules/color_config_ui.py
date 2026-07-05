"""Ported (reduced) from Modules/ColorConfigUi.php.

The PHP original is an in-game chat UI for editing the DB-backed
color/scheme system: it lets an admin browse `#___color_schemes` rows
(grouped by "module"/"name"), reassign each one to a different
`#___colors` row or a "theme" color (`color menu` / `color module
<mod>` / `color select <mod> <scheme>` / `color set <mod> <scheme>
<color>`), and it manages `Themes/*.colors.xml` / `*.scheme.xml` files
on disk (`theme`, `theme select`, `theme export`, `theme import`).

None of that backing store exists in this port. As documented in
colors.py's own docstring, the whole DB-backed multi-scheme/theme-file
system (`#___colors`, `#___color_schemes`, `Themes/*.colors.xml`, the
in-game theme editor) was intentionally not ported -- this bot uses a
single fixed built-in palette (`Colors.color_tags`) instead. Concretely,
`core("colors")` here has none of `get_theme()`, `check_theme()`,
`update_scheme()`, `create_color_cache()`, `create_scheme_file()`, or
`read_scheme_file()`, which every PHP subcommand except the very top of
`show_colors()` depends on. So this port drops entirely:
  * `color menu` / `color module <module>` / `color select <module>
    <scheme>` / `color set <module> <scheme> <color>` -- editing which
    color a named scheme uses; there are no named schemes anymore, just
    the fixed tags.
  * `theme` / `theme select <name>` -- switching the whole palette to a
    different `Themes/*.colors.xml` file; there is only the one built-in
    palette.
  * `theme export <filename>` / `theme import` / `theme import
    <filename>` -- writing/reading `Themes/*.scheme.xml` files; there is
    no scheme DB left to serialize.

What's kept is the one piece that's still meaningful against a fixed
palette: viewing the current tag -> color-code mapping (`color`), and
inspecting/previewing a single tag (`color <tag>`), replacing
`show_colors()`'s "list the defined schemes" behavior with "list the
defined tags", since that's the closest surviving analog.

Depends on `core("colors")` (`color_tags`, `colorize`) and `core("tools")`
(`make_blob`). `core("settings")` is not needed by anything kept.
"""
from __future__ import annotations

from ..commodities.base import BaseActiveModule


class ColorConfigUi(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("color_config_ui")
        self.register_command("all", "color", "SUPERADMIN")
        self.help["description"] = "Shows the colors used by the bot."
        self.help["command"] = {
            "color": "Shows the currently defined color tags.",
            "color <tag>": "Shows the color code and a preview for a single tag.",
        }
        self.help["notes"] = (
            "The DB-backed multi-scheme/theme-file editor from the original "
            "BeBot is not available in this port -- there is one fixed "
            "built-in palette. See this module's docstring for details."
        )

    # -- dispatch ---------------------------------------------------------------
    def command_handler(self, name, msg, origin):
        parts = msg.split(" ")
        v0 = parts[0].lower() if parts and parts[0] else ""
        if v0 != "color":
            return f"Broken plugin, received unhandled command: {v0}"
        v1 = parts[1] if len(parts) > 1 else ""
        if v1 == "":
            return self.show_colors()
        return self.show_color(v1)

    # -- commands -----------------------------------------------------------------
    def show_colors(self) -> str:
        tags = self.bot.core("colors").color_tags
        names = sorted(tag.strip("#") for tag in tags if tag != "##end##")
        if not names:
            return "No color tags defined at all!"
        blob = "##ao_infotext##The following color tags are defined.##end##\n"
        for tag_name in names:
            code = tags.get(f"##{tag_name}##", "")
            blob += f"\n##{tag_name}##{tag_name}##end## {code}"
        return self.bot.core("tools").make_blob("Defined colors", blob)

    def show_color(self, tag: str) -> str:
        tag_name = tag.strip("#").lower()
        colors = self.bot.core("colors")
        tags = colors.color_tags
        key = f"##{tag_name}##"
        if key not in tags or key == "##end##":
            return f"##error##Unknown color tag ##highlight##{tag_name}##end##!##end##"
        code = tags[key]
        preview = colors.colorize(tag_name, f"Sample text in {tag_name}")
        blob = (
            f"##ao_infotext##Tag:##end## ##{tag_name}##{tag_name}##end##\n"
            f"##ao_infotext##Font code:##end## {code}\n"
            f"##ao_infotext##Preview:##end## {preview}"
        )
        return self.bot.core("tools").make_blob(f"Color: {tag_name}", blob)
