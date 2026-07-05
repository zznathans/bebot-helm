"""Ported from Core/LogonNotifies.php.

Global storage for delaying "logon" notifications to registered modules.
This module offers the storing backend as well as the buddy-list logon
tracking: other modules register themselves via `bot.register_event(
"logon_notify", None, self)` (dispatched by Bot.register_event/
unregister_event straight to `register()`/`unregister()` below) and must
expose a `notify(nickname, startup)` method. `nickname` is the character
that logged on; `startup` is True while the bot is still within its
configurable startup grace period (so modules can suppress spam right
after a bot restart).

Scope cut vs. the PHP original: no DB schema/schema-version migration
logic exists in the original for this module (it's pure in-memory state),
so nothing was dropped there.

`core("notify")` (Main/15_Notify.php) is NOT ported yet -- it's part of a
separate, more complex notify<->user cluster planned for a later batch.
The `buddy()` method below still calls `self.bot.core("notify").check(name)`
faithfully as the PHP does; until notify.py exists, `core("notify")`
resolves to Bot's dummy-module fallback, so this call is inert scaffolding
(it logs a CORE/ERROR line the first time and returns a value) rather than
a real notify-eligibility check. This will start behaving correctly once
Main/15_Notify.php is ported.
"""
from __future__ import annotations

import time

from ..commodities.base import BasePassiveModule


class LogonNotifies(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("logon_notifies")
        self.register_event("buddy")
        self.register_event("connect")
        self.register_event("cron", "2sec")

        self.modules: dict[str, object] = {}
        self.cron_running = False
        self.notifies: dict[str, float] = {}
        self.waiting = False

        self.bot.core("settings").create(
            "Logon_Notifies",
            "Notify_Delay",
            5,
            "How many seconds should be waited after logon of a buddy till any notifies are sent to him?",
            "0;1;2;3;4;5;10;15;30",
        )
        self.bot.core("settings").create(
            "Logon_Notifies",
            "Startup_Delay",
            120,
            "How many seconds should be waited after startup before bot starts firing its notifcations?",
            "15;30;60;120;240;480;960",
        )
        self.bot.core("settings").create(
            "Logon_Notifies", "Enabled", True, "Are notifies on logon enabled or disabled?"
        )
        # Init startup high enough that it cannot be reached before connection is done successfully:
        self.startup = time.time() + 3600

    # -- module (un)registration, called by Bot.register_event/unregister_event ---
    def register(self, module) -> None:
        self.modules[type(module).__name__] = module

    def unregister(self, module) -> None:
        self.modules.pop(type(module).__name__, None)

    # -- event handlers -------------------------------------------------------
    def buddy(self, name, msg) -> None:
        if (
            msg == 1
            and self.bot.core("settings").get("Logon_Notifies", "Enabled")
            and self.bot.core("security").check_access(name, "GUEST")
            and self.bot.core("notify").check(name)
        ):
            self.notifies[name] = time.time() + self.bot.core("settings").get(
                "Logon_Notifies", "Notify_Delay"
            )
            self.waiting = True

    def connect(self) -> None:
        self.startup = (
            time.time()
            + self.bot.core("settings").get("Logon_Notifies", "Startup_Delay")
            + self.bot.core("settings").get("Logon_Notifies", "Notify_Delay")
        )

    def cron(self, duration=None) -> None:
        if not self.waiting or not self.modules:
            return
        if not self.notifies:
            self.waiting = False
            self.cron_running = False
            return
        if not self.cron_running:
            self.cron_running = True
        else:
            return

        now = time.time()
        starting = now < self.startup
        for user, due in list(self.notifies.items()):
            if due <= now:
                for module in list(self.modules.values()):
                    if module is not None:
                        module.notify(user, starting)
                self.notifies.pop(user, None)
        self.cron_running = False
