"""Ported from Main/06_Preferences.php.

Registers itself as "prefs" (not "preferences") -- the PHP original does the
same (`$this->bot->register_module($this, "prefs")`), so `bot.core("prefs")`
is the correct lookup for other modules that want to read/change settings.

Two cuts, matching established precedent elsewhere in this codebase:
  * The `update_table()` schema-migration path (the version-1 -> version-2
    ALTER TABLE steps that drop the old `access` column from
    preferences_def and widen `preferences.owner` to a NOT NULL BIGINT) is
    dropped -- as with main_modules/access_control.py, the tables are
    always created directly with the final (v2) schema instead.
  * The PHP source occasionally calls back into its own registered
    instance via `$this->bot->core("prefs")` instead of `$this` (e.g. in
    show_modules()/show_prefs()). Per the porting convention used
    throughout this codebase, those call sites just use `self.method(...)`
    directly here.

Everything else -- default-value caching on `connect`, per-user override
caching on `buddy` login/logout, create()/get()/change()/change_default()/
exists()/show_modules()/show_prefs() -- is ported faithfully, including a
couple of PHP quirks worth flagging for anyone reading closely:
  * get(name) with no module/setting only returns the *set of module
    names* with any meaningful values (it's a shallow array_merge of the
    defaults dict with the user's override dict, so a module with any
    per-user override loses its non-overridden default entries in the
    merged result) -- this matches the PHP exactly, and is fine because
    the only caller (show_modules()) only reads the dict's keys.
  * create() only touches the DB; it does not update the in-memory
    `def` cache, so a preference created after `connect()` has already
    run won't be visible via get()/change() until the bot reconnects (or
    connect() is re-invoked). This is the same behaviour as the PHP.
"""
from __future__ import annotations

from typing import Any

from ..commodities.base import BasePassiveModule, BotError


class Preferences(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        db = bot.db
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('preferences_def', True)} "
            "(ID INT NOT NULL AUTO_INCREMENT PRIMARY KEY, module VARCHAR(30), name VARCHAR(30), "
            "description VARCHAR(255), default_value VARCHAR(25), possible_values VARCHAR(255))"
        )
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('preferences', True)} "
            "(ID INT NOT NULL AUTO_INCREMENT PRIMARY KEY, pref_id INT NOT NULL, "
            "owner BIGINT NOT NULL, value VARCHAR(25))"
        )
        self.register_event("connect")  # Cache all defaults on connect.
        self.register_event("buddy")  # Cache / throw out cache on logon/logoff.
        self.register_module("prefs")
        self.cache: dict[Any, dict[str, dict[str, str]]] = {}

    # -- caching --------------------------------------------------------------
    def connect(self) -> None:
        """Grab all defaults and put them in cache."""
        query = "SELECT module, name, default_value AS value FROM #___preferences_def"
        pref_defs = self.bot.db.select(query, True) or []
        self.cache["def"] = {}
        for preference in pref_defs:
            module = preference["module"].lower()
            name = preference["name"].lower()
            self.cache["def"].setdefault(module, {})[name] = preference["value"]

    def buddy(self, name, msg) -> None:
        uid = self.bot.core("player").id(name)
        if msg == 0:
            if uid in self.cache:
                # Buddy logging off. Throw out the cached data.
                del self.cache[uid]
        elif msg == 1:
            # Cache customized preferences.
            query = (
                "SELECT value, module, name FROM #___preferences AS t1 "
                "JOIN #___preferences_def AS t2 ON t1.pref_ID = t2.ID "
                f"WHERE owner={uid}"
            )
            result = self.bot.db.select(query, True) or []
            for preference in result:
                module = preference["module"].lower()
                pref_name = preference["name"].lower()
                self.cache.setdefault(uid, {}).setdefault(module, {})[pref_name] = preference["value"]

    # -- definitions ------------------------------------------------------------
    def create(self, module: str, name: str, description: str, default: str, possible_values: str) -> None:
        db = self.bot.db
        module = module.lower().capitalize()
        default = default.lower().capitalize()
        description_escaped = db.real_escape_string(description)
        query = (
            "SELECT ID, description, possible_values, default_value FROM #___preferences_def "
            f"WHERE module = '{module}' AND name = '{name}' LIMIT 1"
        )
        prefs = db.select(query)
        if not prefs:
            db.query(
                "INSERT INTO #___preferences_def VALUES "
                f"(NULL, '{module}', '{name}', '{description_escaped}', '{default}', '{possible_values}')"
            )
            self.bot.log(
                "PREFS", "CREATE",
                f"Created preference '{name}' for module '{module}' with default value '{default}'",
            )
            return
        row = prefs[0]
        if row[1] != description or row[2] != possible_values:
            db.query(
                f"UPDATE #___preferences_def SET description = '{description_escaped}', "
                f"possible_values = '{possible_values}' WHERE module = '{module}' AND name = '{name}'"
            )
            self.bot.log("PREFS", "UPDATED", f"Updated values for {name} for module {module}")
            if row[2] != possible_values:
                pv = {temp.strip().lower(): True for temp in possible_values.split(";")}
                if row[3].lower() not in pv:  # current default invalid, reset
                    db.query(
                        f"UPDATE #___preferences_def SET default_value = '{default}' "
                        f"WHERE module = '{module}' AND name = '{name}'"
                    )
                    self.bot.log(
                        "PREFS", "UPDATED",
                        f"Reset default value as it was invalid for {name} for module {module}",
                    )
                uprefs = db.select(f"SELECT ID, value FROM #___preferences WHERE pref_id = {row[0]}") or []
                count = 0
                for pref_id, value in uprefs:
                    if value.strip().lower() not in pv:
                        db.query(f"DELETE FROM #___preferences WHERE ID = '{pref_id}'")
                        count += 1
                if count > 0:
                    self.bot.log(
                        "PREFS", "UPDATED",
                        f"Reset {count} user prefs as they were invalid for {name} for module {module}",
                    )

    def exists(self, module: str, setting: str) -> bool:
        return setting.lower() in self.cache.get("def", {}).get(module.lower(), {})

    # -- reading ------------------------------------------------------------
    def _resolve_uid(self, name):
        if isinstance(name, int):
            return name
        if isinstance(name, str) and name.isdigit():
            return int(name)
        return self.bot.core("player").id(name)

    def get(self, name, module: str | bool = False, setting: str | bool = False):
        uid = self._resolve_uid(name)
        if isinstance(uid, BotError):
            return False

        if module is False and setting is False:
            # We're fetching a list of all preferences for a user.
            if uid in self.cache:
                prefs = dict(self.cache.get("def", {}))
                prefs.update(self.cache.get(uid, {}))
            else:
                # If no user preferences yet, list the known modules.
                prefs = {}
                mods = self.bot.db.select("SELECT DISTINCT(module) FROM #___preferences_def") or []
                for (mod_name,) in mods:
                    prefs[mod_name.lower()] = {}
            return prefs

        if module is not False and setting is False:
            # We're fetching a list of all preferences for a given module.
            module_l = module.lower()
            prefs = {}
            if uid in self.cache and module_l in self.cache.get(uid, {}):
                prefs = dict(self.cache.get("def", {}).get(module_l, {}))
                prefs.update(self.cache[uid][module_l])
            else:
                # If no user preferences yet, use the raw defaults.
                sets = self.bot.db.select(
                    f"SELECT DISTINCT(name), default_value FROM #___preferences_def WHERE module='{module}'"
                ) or []
                for set_name, default_value in sets:
                    prefs[set_name.lower()] = default_value
            return prefs

        module_l = module.lower()
        setting_l = setting.lower()
        if uid in self.cache and setting_l in self.cache[uid].get(module_l, {}):
            return self.cache[uid][module_l][setting_l]
        return self.cache.get("def", {}).get(module_l, {}).get(setting_l)

    # -- writing ------------------------------------------------------------
    def change(self, name, module: str, setting: str, value: str):
        uid = self.bot.core("player").id(name)
        module = module.lower()
        setting = setting.lower()
        default = self.cache.get("def", {}).get(module, {}).get(setting)
        old_value = self.get(uid, module, setting)
        if isinstance(old_value, BotError):
            self.error = old_value
            return self.error
        if old_value == value:
            return f"Preference for {name}, {module}->{setting} was already set to '{value}'. Nothing changed."
        if value == default:
            # Changing to the default value. Remove from preference table and user cache.
            self.bot.db.query(
                f"DELETE FROM #___preferences WHERE owner = {uid} AND pref_id = "
                f"(SELECT ID FROM #___preferences_def WHERE module = '{module}' AND name = '{setting}' LIMIT 1) LIMIT 1"
            )
            self.cache.get(uid, {}).get(module, {}).pop(setting, None)
            return f"Preferences for {name}, {module}->{setting} reset to default value '{value}'"
        if old_value == default:
            # The value was previously set to default. An entry needs to be made in the table.
            self.bot.db.query(
                "INSERT INTO #___preferences (pref_id, owner, value) VALUES ("
                f"(SELECT ID FROM #___preferences_def WHERE module='{module}' AND name='{setting}' LIMIT 1), {uid}, '{value}')"
            )
            self.cache.setdefault(uid, {}).setdefault(module, {})[setting] = value
            return f"Preference was created for {name}, {module}->{setting} = {value}"
        # Neither old nor new value are defaults. An update needs to be made to the table.
        self.bot.db.query(
            f"UPDATE #___preferences SET value='{value}' WHERE owner={uid} AND pref_id="
            f"(SELECT ID FROM #___preferences_def WHERE module='{module}' AND name='{setting}' LIMIT 1) LIMIT 1"
        )
        self.cache.setdefault(uid, {}).setdefault(module, {})[setting] = value
        return f"Preferences for {name}, {module}->{setting} changed to '{value}'"

    def change_default(self, name, module: str, setting: str, value: str) -> str:
        module = module.lower()
        setting = setting.lower()
        self.bot.db.query(
            f"UPDATE #___preferences_def SET default_value = '{value}' "
            f"WHERE module='{module}' AND name='{setting}' LIMIT 1"
        )
        self.bot.db.query(
            "DELETE FROM #___preferences WHERE pref_id="
            f"(SELECT ID FROM #___preferences_def WHERE module='{module}' AND name='{setting}' LIMIT 1)"
        )
        self.cache.setdefault("def", {}).setdefault(module, {})[setting] = value
        # Remove any customisation that matches the new default from cached users.
        for user in list(self.cache.keys()):
            if user == "def":
                continue
            content = self.cache[user]
            if module in content and content[module].get(setting) == value:
                del content[module][setting]
            if module in content and len(content[module]) == 0:
                del content[module]
            if len(content) == 0:
                del self.cache[user]
        self.bot.log(
            "PREFS", "CHANGE",
            f"{name} changed the default value for setting {module} -> {setting} to {value}",
        )
        return f"The default value for {module}->{setting} has been set to '{value}'."

    # -- display --------------------------------------------------------------
    def show_modules(self, name) -> str:
        window = ""
        modules = self.get(name) or {}
        for module in modules.keys():
            window += (
                "Preferences for "
                + self.bot.core("tools").chatcmd(f"preferences show {module}", module)
                + "<br>"
            )
        return self.bot.core("tools").make_blob("Preferences", window)

    def show_prefs(self, name, module: str, defaults: bool = True) -> str:
        query = (
            "SELECT name, description, default_value, possible_values FROM #___preferences_def "
            f"WHERE module='{module}'"
        )
        pref_defs = self.bot.db.select(query, True) or []
        prefs = self.get(name, module) or {}
        window = f"<center>##blob_title##::: Preferences for {module} :::##end##</center>\n"
        for preference in pref_defs:
            current_value = ""
            index = preference["name"].lower()
            if index in prefs:
                current_value = prefs[index]
            value_list = preference["possible_values"].split(";")
            window += (
                f"##highlight##{preference['name']}: ##end####blob_text##{preference['description']}##end##\n"
            )
            buttonlist = "##highlight##[ ##end##"
            for option in value_list:
                if option == current_value:
                    buttonlist += option
                else:
                    buttonlist += self.bot.core("tools").chatcmd(
                        f"preferences set {module} {preference['name']} {option}", option
                    )
                if defaults and self.bot.core("access_control").check_rights(
                    name, "preferences", "preferences default", "tell"
                ):
                    if option == preference["default_value"]:
                        buttonlist += "##green##[##end##D##green##]##end##"
                    else:
                        buttonlist += "##red##[##end##"
                        buttonlist += self.bot.core("tools").chatcmd(
                            f"preferences default {module} {preference['name']} {option}", "D"
                        )
                        buttonlist += "##red##]##end##"
                buttonlist += " | "
            buttonlist = buttonlist[:-3]
            buttonlist += "##highlight## ]##end##<br><br>"
            window += buttonlist
        return "Preferences for " + self.bot.core("tools").make_blob(module, window)
