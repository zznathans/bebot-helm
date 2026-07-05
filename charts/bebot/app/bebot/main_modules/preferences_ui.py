"""Ported from Modules/PreferencesUi.php (class `Preferences_GUI`).

Thin chat-command UI over the already-ported `core("prefs")`
(main_modules/preferences.py -- note the registration name is "prefs", not
"preferences", matching the PHP's `register_module($this, "prefs")`):
lets a GUEST browse the known preference modules and a given module's
settings, and lets a user change their own preference ("set") or -- gated
by the "default" subcommand access level (SUPERADMIN by default, same as
the PHP's `array('default' => 'SUPERADMIN')`) -- change a setting's
default for everyone ("default").

Scope notes / intentional deviations from the PHP:
  * `preferences reset <module>` is dispatched in the PHP to
    `$this->bot->core('prefs')->reset($name, $com['module'])`, but neither
    the PHP `Preferences` core class (Main/06_Preferences.php) nor its
    Python port (preferences.py) actually defines a `reset()` method --
    this is dead/broken code in the original (it would throw a fatal PHP
    error if ever reached). Rather than silently inventing a `reset()`
    behaviour that doesn't exist upstream, this is preserved as an inert,
    caught case here: it falls through to the same "Unknown command"
    error as any other unrecognised subcommand instead of raising
    `AttributeError`.
  * The PHP's special-cased "add to notify list" side effect on `set` (for
    the three specific autoinv/mail/massmsg preferences that imply the
    user wants to be notified while offline) is preserved faithfully in
    `_maybe_add_notify()`, using `core("notify")`'s already-ported
    `check()`/`add()`.
  * See preferences.py's own docstring for two faithfully-preserved PHP
    quirks in the underlying core module (`get()`'s shallow-merge and
    `create()` not updating the in-memory default cache) -- neither is
    touched here since this module only calls the already-public
    `show_modules()`/`show_prefs()`/`change()`/`change_default()` surface.
  * Nothing here touches Core/Ao/Whois.php, IRC/relay bridges, or the
    dynamic Core/Modules/ plugin loader.
"""
from __future__ import annotations

from ..commodities.base import BaseActiveModule


class PreferencesUi(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("preferences_ui")
        self.register_command("all", "preferences", "GUEST", {"default": "SUPERADMIN"})
        self.register_alias("preferences", "prefs")
        self.help["description"] = "Player Preferences"
        self.help["command"] = {
            "preferences": "Shows the preferences interface.",
        }
        self.help["notes"] = (
            "When a default is changed all users who have not customised "
            "that setting will also have their preferences changed.<br>"
            "When a default is changed from option A to option B and back again "
            "users who had customised their preference to option B will be reset "
            "and have option A as default again."
        )

    # -- dispatch ---------------------------------------------------------------
    def command_handler(self, name, msg, origin):
        parts = msg.split(" ", 4)
        sub = parts[1].lower() if len(parts) > 1 else ""
        module = parts[2] if len(parts) > 2 else ""
        preference = parts[3] if len(parts) > 3 else ""
        value = parts[4] if len(parts) > 4 else ""

        prefs = self.bot.core("prefs")
        if sub == "":
            # No arguments.
            return prefs.show_modules(name)
        if sub == "show":
            if module == "":
                # Show all modules.
                return prefs.show_modules(name)
            # Show module-specific preferences.
            return prefs.show_prefs(name, module)
        if sub == "set":
            self._maybe_add_notify(name, module, preference, value)
            return prefs.change(name, module, preference, value)
        if sub == "default":
            return prefs.change_default(name, module, preference, value)
        # "reset" falls through to here too -- see module docstring: the PHP
        # dispatches it to a core method that has never existed.
        self.error.set(f"Unknown command ##highlight##'{sub}'##end##")
        return self.error

    # -- side effects -------------------------------------------------------------
    def _maybe_add_notify(self, name: str, module: str, preference: str, value: str) -> None:
        """Auto-add the user to the notify list for the specific preference
        combinations the PHP special-cases (offline mail/mass-message/auto-invite
        notifications all imply the user wants to be reachable while offline)."""
        module_l = module.lower()
        preference_l = preference.lower()
        value_l = value.lower()
        trigger = (
            (module_l == "autoinv" and preference_l == "receive_auto_invite" and value_l == "on")
            or (module_l == "mail" and preference_l == "logon_notification" and value_l == "yes")
            or (module_l == "massmsg" and value_l == "yes")
        )
        if trigger:
            notify = self.bot.core("notify")
            if not notify.check(name):
                notify.add(name, name)
