"""Ported from Core/Alias.php.

Lets players register free-text "aliases" (nicknames they're commonly
known by) for their character, used elsewhere to look someone up by a
name other than their actual AO character name. This is a distinct
concept from the already-ported `command_alias.py` (Main/15_CommandAlias.php),
which aliases *chat commands*, not characters -- the two happen to share a
name in English but have nothing to do with each other.

Depends on the already-ported `core("alts")` (to normalize a character to
its "main" before storing/looking up aliases), `core("tools")`
(`sanitize_player`/`chatcmd`/`make_blob`), and `core("player")` (existence
check via `.id()`).

Scope notes:
  * The PHP source has no DB schema-version migration logic for this
    module (a single `CREATE TABLE IF NOT EXISTS` with its final schema),
    so there's nothing to drop here -- unlike settings.py/access_control.py/
    alts.py, which do drop such logic.
  * Nothing here touches Core/Ao/Whois.php, IRC/relay bridges, or the
    dynamic Core/Modules/ plugin loader, so there's no cut to note for
    those either.
  * `del_alias()`'s cache eviction (`unset($this->alias[$alias])` in the
    PHP) uses the alias argument's original case, while the cache is
    always keyed by the lower-cased alias (see `create_caches()`/
    `add_alias()`). This is a latent case-sensitivity quirk in the PHP
    original (a mixed-case `alias del FooBar` would fail to evict the
    `foobar` cache entry even though the DB row -- keyed the same way --
    would be deleted). It's preserved as-is here for faithful parity
    rather than silently fixed.
"""
from __future__ import annotations

from ..commodities.base import BaseActiveModule, BotError


class Alias(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_command("all", "alias", "GUEST", {"admin": "ADMIN"})
        self.register_module("alias")
        self.register_event("connect")
        self.help["description"] = (
            "Add Alias's like what you are commonly called to be used in other modules."
        )
        self.help["command"] = {
            "alias add <Alias>": "Add Alias.",
            "alias del <Alias>": "Delete Alias.",
            "alias rem <Alias>": "Delete Alias.",
            "alias admin add <nickname> <Alias>": "Add Alias to Nickname.",
            "alias admin del <Alias>": "Delete Alias.",
            "alias admin rem <Alias>": "Delete Alias.",
            "alias <name>": "Show Alias's associated with <name> and Alts.",
            "alias": "Show Alias's associated with you and your Alts.",
            "alias list": "Show all Alias's.",
        }
        db = bot.db
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('alias', False)} "
            "(alias VARCHAR(30) PRIMARY KEY, nickname VARCHAR(30), main INT(1) Default '0')"
        )
        self.alias: dict[str, str] = {}
        self.main: dict[str, str] = {}

    # -- lifecycle ---------------------------------------------------------------
    def connect(self) -> None:
        self.create_caches()

    def create_caches(self) -> None:
        self.alias = {}
        self.main = {}
        rows = self.bot.db.select("SELECT alias, nickname, main FROM #___alias") or []
        for alias, nickname, main in rows:
            self.alias[str(alias).lower()] = nickname
            if int(main or 0) == 1:
                self.main[self.bot.core("alts").main(nickname)] = alias

    # -- dispatch ---------------------------------------------------------------
    def command_handler(self, name, msg, origin):
        parts = msg.split(" ")

        def arg(i: int, default: str = "") -> str:
            return parts[i] if len(parts) > i else default

        v0 = arg(0).lower()
        v1 = arg(1).lower()
        if v0 != "alias":
            return f"Broken plugin, received unhandled command: {v0}"
        if v1 == "add":
            return self.add_alias(name, arg(2))
        if v1 in ("del", "rem"):
            return self.del_alias(name, arg(2))
        if v1 == "main":
            return self.set_main(name, arg(2))
        if v1 == "":
            return self.get_alias(name)
        if v1 == "admin":
            v2 = arg(2).lower()
            if v2 == "add":
                new_name = arg(3).capitalize()
                return self.add_alias(new_name, arg(4))
            if v2 in ("rem", "del"):
                return self.del_alias_admin(arg(3))
            return f"Unknown Subcommand of alias admin: {v1}"
        return self.get_alias(arg(1))

    # -- mutation ---------------------------------------------------------------
    def add_alias(self, name: str, alias: str) -> str | BotError:
        mainmsg = ""
        if isinstance(self.bot.core("player").id(name), BotError):
            return f"##error##Character ##highlight##{name}##end## does not exist.##end##"
        if len(alias) < 3:
            return f"##error##Alias ##highlight##{alias}##end## is too Short. (min 3)##end##"
        name = self.bot.core("alts").main(name)
        db = self.bot.db
        result = db.select(f"SELECT nickname FROM #___alias WHERE alias = '{alias}'")
        if not result:
            name = self.bot.core("tools").sanitize_player(name)
            if name not in self.main:
                mainmsg = " and set as Main Alias"
                self.main[name] = alias
                main = 1
            else:
                main = 0
            db.query(
                f"INSERT INTO #___alias (alias, nickname, main) VALUES ('{alias}', '{name}', {main})"
            )
            self.alias[alias.lower()] = name
            return f"##highlight##{alias}##end## Added as Alias of ##highlight##{name}##end##{mainmsg}"
        return f"##highlight##{alias}##end## is Already an Alias off ##highlight##{result[0][0]}##end##."

    def del_alias(self, name: str, alias: str) -> str:
        name = self.bot.core("alts").main(name)
        db = self.bot.db
        result = db.select(f"SELECT nickname, main FROM #___alias WHERE alias = '{alias}'")
        if result:
            nickname, main_flag = result[0][0], result[0][1]
            if nickname == name:
                db.query(f"DELETE FROM #___alias WHERE alias = '{alias}'")
                self.alias.pop(alias, None)
                if int(main_flag or 0) == 1:
                    self.main.pop(name, None)
                return f"Alias ##highlight##{alias}##end## Deleted."
            return (
                f"Alias ##highlight##{alias}##end## Belongs to ##highlight##{nickname}##end## "
                "and can not be Deleted by you."
            )
        return f"Alias ##highlight##{alias}##end## Not found."

    def del_alias_admin(self, alias: str) -> str:
        db = self.bot.db
        result = db.select(f"SELECT nickname, main FROM #___alias WHERE alias = '{alias}'")
        if result:
            nickname, main_flag = result[0][0], result[0][1]
            db.query(f"DELETE FROM #___alias WHERE alias = '{alias}'")
            self.alias.pop(alias, None)
            if int(main_flag or 0) == 1:
                self.main.pop(nickname, None)
            return f"Alias ##highlight##{alias}##end## Deleted."
        return f"Alias ##highlight##{alias}##end## Not found."

    def set_main(self, name: str, alias: str) -> str:
        alias = alias.lower()
        db = self.bot.db
        alts = self.bot.core("alts")
        main = alts.main(name)
        if main in self.main:
            if self.main[main].lower() == alias:
                return f"##highlight##{alias}##end## is Already you main alias"
            amain = alts.main(self.alias.get(alias, ""))
            if main != amain:
                return f"##highlight##{alias}##end## is not your Alias so cannot be set as main"
            db.query(f"UPDATE #___alias SET main = 0 WHERE nickname = '{main}'")
            db.query(f"UPDATE #___alias SET main = 1 WHERE alias = '{alias}'")
            self.create_caches()
            return "Alias Main set"
        if alias in self.alias:
            amain = alts.main(self.alias[alias])
            if main != amain:
                return f"##highlight##{alias}##end## is not your Alias so cannot be set as main"
            sql = f"UPDATE #___alias SET main = 0 WHERE nickname = '{main}'"
            for alt in alts.get_alts(main) or []:
                sql += f" OR nickname = '{alt}'"
            db.query(sql)
            db.query(f"UPDATE #___alias SET main = 1 WHERE alias = '{alias}'")
            self.create_caches()
            return "Alias Main set"
        return "Alias not Found"

    # -- lookups ------------------------------------------------------------------
    def get_alias(self, name: str) -> str:
        name = self.bot.core("tools").sanitize_player(name)
        inside = "<center>##ao_ccheader##:::: Alias List ::::##end##</center>\n"
        aliases = self.alias
        if aliases:
            if name == "List":
                for alias, nickname in aliases.items():
                    inside += f"\n##lightyellow##{alias}"
                    inside += "   " + self.bot.core("tools").chatcmd(f"whois {nickname}", nickname)
            else:
                main = self.bot.core("alts").main(name)
                for alias, nickname in aliases.items():
                    if main == nickname:
                        inside += f"\n##lightyellow##{alias}"
                        inside += "   " + self.bot.core("tools").chatcmd(f"whois {nickname}", nickname)
        else:
            inside = "<center>##ao_ccheader##:::: No Alias's Found ::::##end##</center>\n"
        if name == "List":
            forwho = "Alias List :: "
        else:
            forwho = f"Alias List :: {name} and Alts :: "
        return forwho + self.bot.core("tools").make_blob("click to view", inside)

    def get_main(self, name: str):
        main = self.bot.core("alts").main(name)
        return self.main.get(main, False)
