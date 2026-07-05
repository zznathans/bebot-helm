"""Ported (reduced) from Main/06_Settings.php.

Schema-version migration and the "Maintenance" first-run diff-reporting
hook are dropped -- we always create the current schema directly, and the
Maintenance module itself isn't ported (in-game "what changed" report,
not needed to run).
"""
from __future__ import annotations

from ..commodities.base import BasePassiveModule, BotError


def _get_data_type(value):
    if isinstance(value, bool):
        return "bool"
    if value is None:
        return "null"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "unknown"


def _set_data_type(value, datatype: str):
    datatype = (datatype or "").lower()
    if datatype == "bool":
        return str(value).upper() == "TRUE"
    if datatype == "null":
        return None
    if datatype == "float":
        return float(value)
    if datatype == "int":
        return int(value)
    if datatype == "array":
        return value.split(";") if value else []
    return str(value)


class Settings(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        db = bot.db
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('settings', True)} "
            "(module varchar(25) NOT NULL, setting varchar(50) NOT NULL, value varchar(255) NOT NULL, "
            "datatype varchar(25) DEFAULT NULL, longdesc varchar(255) DEFAULT NULL, "
            "defaultoptions varchar(255) DEFAULT NULL, hidden BOOLEAN DEFAULT 0, "
            "disporder INT UNSIGNED NOT NULL DEFAULT 1, PRIMARY KEY (module, setting))"
        )
        self.register_module("settings")
        self.register_event("connect")
        self.register_event("cron", "1hour")
        self._cache: dict[str, dict[str, object]] = {}
        self._callbacks: dict[tuple[str, str], dict[str, object]] = {}
        self.create("Settings", "Log", True, "Log settings changes/loads?")
        self.load_all()

    def cron(self, duration=None) -> None:
        self.load_all()

    def connect(self) -> None:
        self.load_all()

    def exists(self, module: str, setting: str) -> bool:
        return setting.lower() in self._cache.get(module.lower(), {})

    def get(self, module: str, setting: str):
        bucket = self._cache.get(module.lower(), {})
        if setting.lower() in bucket:
            return bucket[setting.lower()]
        self.error.set(f"The setting named {setting} for setting group {module} does not exist.")
        return self.error

    def get_all(self, module: str):
        return self._cache.get(module.lower(), {})

    def load_all(self) -> None:
        rows = self.bot.db.select("SELECT module, setting, value, datatype FROM #___settings") or []
        self._cache = {}
        for module, setting, value, datatype in rows:
            typed = value.split(";") if datatype == "array" else _set_data_type(value, datatype)
            self._cache.setdefault(module.lower(), {})[setting.lower()] = typed

    def save(self, module: str, setting: str, value, noupdate: bool = False):
        module = module.replace(" ", "_")
        setting = setting.strip().replace(" ", "_")
        if setting.lower() not in self._cache.get(module.lower(), {}):
            self.error.set(f"Setting {setting} for module {module} could not be saved. It does not exist.")
            return self.error
        datatype = _get_data_type(value)
        if datatype == "array":
            value = ";".join(value)
        elif datatype == "bool":
            value = "TRUE" if value else "FALSE"
        db = self.bot.db
        m, s, v = db.real_escape_string(module), db.real_escape_string(setting), db.real_escape_string(str(value))
        if noupdate:
            sql = f"INSERT IGNORE INTO #___settings (module, setting, value, datatype) VALUES ('{m}','{s}','{v}','{datatype}')"
        else:
            sql = f"UPDATE #___settings SET value = '{v}', datatype = '{datatype}' WHERE module = '{m}' AND setting = '{s}'"
        if db.query(sql):
            old_value = self._cache[module.lower()][setting.lower()]
            new_value = _set_data_type(value, datatype)
            self._cache[module.lower()][setting.lower()] = new_value
            for callback in self._callbacks.get((module.lower(), setting.lower()), {}).values():
                if callback is not None:
                    callback.settings("", module.lower(), setting.lower(), new_value, old_value)
            return True
        self.error.set(f"Could not save setting {setting} for module {module} to database.")
        return self.error

    def create(self, module: str, setting: str, value, longdesc: str, defaultoptions: str = "",
               hidden: bool = False, disporder: int = 1):
        module = module.replace(" ", "_")
        setting = setting.replace(" ", "_")
        datatype = _get_data_type(value)
        if datatype == "bool":
            defaultoptions = "On;Off"
            value = "TRUE" if value else "FALSE"
        elif datatype == "null":
            value = "null"
        elif isinstance(value, list):
            value = ";".join(value)
            hidden = True
        else:
            value = str(value)
        db = self.bot.db
        m, s = db.real_escape_string(module), db.real_escape_string(setting)
        v, ld, do = db.real_escape_string(value), db.real_escape_string(longdesc), db.real_escape_string(defaultoptions)
        existing = db.select(
            f"SELECT longdesc, defaultoptions, hidden, disporder FROM #___settings WHERE module = '{m}' AND setting = '{s}'"
        )
        if existing:
            row = existing[0]
            if [row[0], row[1], row[2], row[3]] != [longdesc, defaultoptions, int(hidden), disporder]:
                db.query(
                    f"UPDATE #___settings SET longdesc = '{ld}', defaultoptions = '{do}', hidden = {int(hidden)}, "
                    f"disporder = {disporder} WHERE module = '{m}' AND setting = '{s}'"
                )
        else:
            result = db.query(
                "INSERT INTO #___settings (module, setting, value, datatype, longdesc, defaultoptions, hidden, disporder) "
                f"VALUES ('{m}', '{s}', '{v}', '{datatype}', '{ld}', '{do}', {int(hidden)}, {disporder}) "
                "ON DUPLICATE KEY UPDATE longdesc=VALUES(longdesc), defaultoptions=VALUES(defaultoptions), "
                "hidden=VALUES(hidden), disporder=VALUES(disporder)"
            )
            if result:
                self._cache.setdefault(module.lower(), {})[setting.lower()] = _set_data_type(value, datatype)
        return True

    def del_setting(self, module: str, setting: str | None = None):
        module = module.replace(" ", "_")
        db = self.bot.db
        if setting is None:
            db.query(f"DELETE FROM #___settings WHERE module = '{db.real_escape_string(module)}'")
            self._cache.pop(module.lower(), None)
            return f"Deleted settings for {module}."
        setting = setting.replace(" ", "_")
        if setting.lower() not in self._cache.get(module.lower(), {}):
            self.error.set(f"Setting {setting} for module {module} does not exist.")
            return self.error
        self._cache[module.lower()].pop(setting.lower(), None)
        db.query(
            f"DELETE FROM #___settings WHERE module = '{db.real_escape_string(module)}' "
            f"AND setting = '{db.real_escape_string(setting)}'"
        )
        return f"Deleted setting '{setting}' from '{module}'."

    def register_callback(self, module: str, setting: str, reg_module) -> str | bool:
        key = (module.lower(), setting.lower())
        name = type(reg_module).__name__
        if name in self._callbacks.get(key, {}):
            return f"{name} has the setting {setting} of the module {module} already registered!"
        self._callbacks.setdefault(key, {})[name] = reg_module
        return False

    def unregister_callback(self, module: str, setting: str, reg_module) -> str | bool:
        key = (module.lower(), setting.lower())
        name = type(reg_module).__name__
        if name not in self._callbacks.get(key, {}):
            return f"{name} does not have setting {setting} of module {module} registered!"
        del self._callbacks[key][name]
        return False
