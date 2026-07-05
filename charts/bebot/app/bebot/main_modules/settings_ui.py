"""Ported from Modules/SettingsUi.php (class `SetConf`).

Chat-command UI layer over the already-ported `core("settings")`
(`bebot/main_modules/settings.py`). Lets SUPERADMINs browse the settings
groups stored in `#___settings`, view the settings for one group, and
change a single setting's value.

Scope notes / intentional deviations from the PHP:
  * The ported `Settings.save()` has no `change_user` tracking (no
    `set_change_user()`/`$change_user` in `settings.py` at all -- the whole
    concept was dropped when that module was ported), so unlike the PHP's
    `change_setting()` this doesn't bracket the save with
    `set_change_user($user)` / `set_change_user("")`. The `user` argument is
    kept on `change_setting()` for signature parity with the PHP but is
    otherwise unused, same as upstream effectively left it once you note
    `change_user` never influenced anything user-visible there either.
  * `get_data_type()`/`set_data_type()`/`remove_space()` are private
    module-level helpers on `settings.py` (leading underscore, not part of
    its public surface) rather than being called through `core("settings")`
    -- per this codebase's convention of never reaching into another
    main_module's internals, they're reimplemented locally here
    (`_data_type()`/`_coerce()`) operating on the already-typed Python value
    `Settings.get()` returns, instead of on a raw DB string.
  * `command_handler()`'s 3-token branch (`"settings <module> <setting>"`,
    no value) faithfully preserves an argument-order bug in the original:
    `change_setting($msg[1], $msg[2], "")` drops `$name` and shifts every
    argument over one slot, so `setting` always ends up `""` and the call
    always reports "does not exist". This is harmless (the `user` argument
    was never used for anything observable, see above) and preserved as-is
    for parity rather than silently "fixed", matching this repo's existing
    precedent for latent-but-inert PHP quirks (see `alias.py`'s docstring).
  * Modifying array-typed settings is refused, same as upstream ("Modifying
    array values is not supported in this interface").
  * Nothing here touches Core/Ao/Whois.php, IRC/relay bridges, or the
    dynamic Core/Modules/ plugin loader.
"""
from __future__ import annotations

import re

from ..commodities.base import BaseActiveModule, BotError


def _data_type(value) -> str:
    if isinstance(value, bool):
        return "bool"
    if value is None:
        return "null"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, list):
        return "array"
    return "string"


def _coerce(value: str, datatype: str):
    """Loosely mirrors PHP's intval()/floatval() (garbage -> 0/0.0) rather
    than raising, since a chat user can type anything as <value>."""
    if datatype == "int":
        try:
            return int(value)
        except ValueError:
            try:
                return int(float(value))
            except ValueError:
                return 0
    if datatype == "float":
        try:
            return float(value)
        except ValueError:
            return 0.0
    return str(value)


class SettingsUi(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.help["description"] = "Setting management interface."
        self.help["command"] = {
            "settings": "Shows the settings interface",
            "set <module> <setting> <value>": "Sets the setting <setting> for module <module> to <value>.",
        }
        self.register_command("all", "settings", "SUPERADMIN")
        self.register_module("settings_ui")
        self.register_alias("settings", "set")

    # -- dispatch ---------------------------------------------------------------
    def command_handler(self, name, msg, origin):
        parts = msg.split(" ", 3)
        if len(parts) == 4:
            return self.change_setting(name, parts[1], parts[2], parts[3])
        if len(parts) == 3:
            # Preserved PHP argument-shift bug -- see module docstring.
            return self.change_setting(parts[1], parts[2], "")
        if len(parts) == 2:
            return self.show_module(parts[1])
        return self.show_all_modules()

    # -- views --------------------------------------------------------------------
    def show_all_modules(self) -> str:
        db = self.bot.db
        rows = db.select("SELECT DISTINCT module FROM #___settings WHERE hidden = FALSE ORDER BY module") or []
        if not rows:
            return "No settings defined."
        tools = self.bot.core("tools")
        output = "##ao_infoheader##Setting groups for <botname>:##end##\n\n"
        for row in rows:
            module = row[0]
            if module:
                output += tools.chatcmd(f"settings {module}", module) + "\n"
        return tools.make_blob("Settings groups for <botname>", output)

    def show_module(self, module: str) -> str:
        module = module.replace(" ", "_")
        db = self.bot.db
        m = db.real_escape_string(module)
        rows = db.select(
            "SELECT setting, value, datatype, longdesc, defaultoptions FROM #___settings "
            f"WHERE module = '{m}' AND hidden = FALSE ORDER BY disporder, setting"
        ) or []
        if not rows:
            return f"No settings for module {module}"
        tools = self.bot.core("tools")
        inside = f"##ao_infoheader##Settings for {module}##end##\n\n"
        for setting, value, datatype, longdesc, defaultoptions in rows:
            if not longdesc:
                if datatype in ("int", "float"):
                    longdesc = "Numeric"
                elif datatype == "bool":
                    longdesc = "On/Off"
                elif datatype == "string":
                    longdesc = "Text String"
                else:
                    longdesc = "Not configured."
            options = (defaultoptions or "").split(";")
            optionlinks = "  ##ao_infotextbold##Change to: ["
            for option in options:
                optionlinks += " " + tools.chatcmd(f"set {module} {setting} {option}", option) + " |"
            optionlinks = optionlinks.rstrip("|") + "]##end##"
            display_value = value
            if str(value).upper() == "TRUE":
                display_value = "On"
            elif str(value).upper() == "FALSE":
                display_value = "Off"
            if str(setting).lower() == "password":
                inside += f"##ao_infoheadline##{setting}:##end##  ##ao_infotextbold##************##end##\n"
            elif re.match(r"^#[0-9a-f]{6}$", str(display_value), re.I):
                inside += f"##ao_infoheadline##{setting}:##end##  <font color={display_value}>{display_value}</font>\n"
            else:
                inside += f"##ao_infoheadline##{setting}:##end##  ##ao_infotextbold##{display_value}##end##\n"
            inside += f"  ##ao_infotextbold##Description:##end## ##ao_infotext##{longdesc}##end##\n"
            if len(options) > 1:
                inside += optionlinks + "\n\n"
            else:
                inside += f"/tell <botname> <pre>set {module} {setting} &lt;new value&gt;\n\n"
        return tools.make_blob(f"Settings for {module}", inside)

    # -- mutation ---------------------------------------------------------------
    def change_setting(self, user: str, module: str, setting: str, value: str = ""):
        settings = self.bot.core("settings")
        module = module.replace(" ", "_")
        setting = setting.replace(" ", "_")
        if not settings.exists(module, setting):
            return f"Setting {setting} for module {module} does not exist."
        current = settings.get(module, setting)
        datatype = _data_type(current)
        if datatype == "bool":
            lowered = value.lower()
            if lowered == "on":
                value = True
            elif lowered == "off":
                value = False
            else:
                return f"Unrecognized value for setting {setting} for module {module}. No change made."
        elif datatype == "null":
            value = None if value.lower() == "null" else value
        elif datatype == "array":
            return f"Modifying array values is not supported in this interface. See the help for {module}"
        else:
            value = _coerce(value, datatype)
        result = settings.save(module, setting, value)
        if isinstance(result, BotError):
            return result
        display = "On" if value is True else "Off" if value is False else value
        return f"Changed setting {setting} for module {module} to {display} [{self.show_module(module)}]"
