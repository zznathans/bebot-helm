"""Ported (reduced) from Modules/About.php.

Only the static `about` command (the credits/links blob) is ported.
Cut vs. the PHP original:
  * The periodic version-check (`register_event("cron", "6hour")`,
    `version_check()`, `set_update_time()`) and the SUPERADMIN "new version
    available" buddy notice (`buddy()`, `register_event("buddy")`) depended
    on `core("tools")->get_site()`/`->xmlparse()`, which main_modules/tools.py
    deliberately does not port (see its docstring: "proxy/curl/socket HTTP
    helpers ... not ported -- network scraping helpers for optional
    features, not needed to run"). With no way to fetch/parse the remote
    bebot.link version XML, there is nothing left for these to do, so the
    whole update-check subsystem (and the "Version"/`CheckURL`/`CheckUpdate`/
    `LastCheck` settings it registered) is dropped rather than ported as a
    permanent no-op.
  * `BOT_VERSION_NAME`/`BOT_VERSION` (PHP constants baked in at build time)
    have no equivalent anywhere else in this Python port (see
    main_modules/bot_statistics_ui.py's docstring, which hit the same gap
    for `environ`), so the "Bot Client:" line reports a generic
    "BeBot (Python port)" label instead of inventing version constants that
    don't exist elsewhere in the codebase.
"""
from __future__ import annotations

from ..commodities.base import BaseActiveModule

_BOT_CLIENT_LABEL = "BeBot (Python port)"


class About(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("about")
        self.register_command("all", "about", "GUEST")
        self.register_alias("about", "version")
        self.help["description"] = "Shows information about the bot."
        self.help["command"] = {"about": "See description"}

    # -- dispatch -----------------------------------------------------------------
    def command_handler(self, name, msg, origin):
        command = (msg or "").split(" ")[0].lower()
        if command == "about":
            return self.about_blob()
        return f"Broken plugin, received unhandled command: {command}"

    # -- rendering ------------------------------------------------------------------
    def about_blob(self) -> str:
        inside = "##blob_text##Bot Client:##end##\n"
        inside += f"{_BOT_CLIENT_LABEL}\n\n"
        inside += "##blob_text##Developers:##end##\n"
        inside += "Alreadythere (RK2)\n"
        inside += "Blondengy (RK1)\n"
        inside += "Blueeagl3 (RK1)\n"
        inside += "Glarawyn (RK1)\n"
        inside += "Khalem (RK1)\n"
        inside += "Naturalistic (RK1)\n"
        inside += "Temar (RK1 / Doomsayer)\n\n"
        inside += "##blob_text##Special thanks to:##end##\n"
        inside += "Akarah (RK1)\n"
        inside += "Bigburtha (RK2) aka Craized\n"
        inside += "Derroylo (RK2)\n"
        inside += "Foxferal (RK1)\n"
        inside += "Jackjonez (RK1)\n"
        inside += "Sabkor (RK1)\n"
        inside += "Vhab (RK1)\n"
        inside += "Wolfbiter (RK1)\n"
        inside += "Xenixa (RK1)\n"
        inside += "Zacix (RK2)\n"
        inside += "Zarkingu (RK2)\n"
        inside += "Bitnykk (RK5)\n"
        inside += "Auno for various tools as PHP AOChat library & DB extractor/parser\n"
        inside += "Tyrence for writing/updating many modules that inspired recent patches\n"
        inside += "And last but not least, the greatest MMORPG community in existence.\n\n"
        inside += "##blob_text##Links:##end##\n"
        tools = self.bot.core("tools")
        if str(self.bot.game).lower() == "ao":
            inside += tools.chatcmd("http://bebot.link", "BeBot website and support forums", "start") + "\n"
        else:
            inside += "BeBot website and support forums: http://bebot.link \n"
        return f"{_BOT_CLIENT_LABEL} ::: " + tools.make_blob("More details", inside)
