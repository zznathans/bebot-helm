"""Fixed load order for the ported subset of Main/*.php.

Replaces Main.php's `$bot->load_files('Main', 'Main')` directory scan --
there is no dynamic Core/Modules/Custom plugin loading in this port yet,
just this hardcoded list of modules, instantiated in dependency order
(each module registers itself onto `bot` via `register_module()` in its
constructor, so order only matters where a constructor calls
`bot.core(...)` on another module).
"""
from __future__ import annotations

from .access_control import AccessControl
from .access_control_ui import AccessControlUi
from .alias import Alias
from .alts import Alts
from .aochat_wrapper import ChatWrapper
from .bot_help import BotHelp
from .bot_statistics import BotStatistics
from .buddy_list import BuddyList
from .buddy_queue import BuddyQueue
from .chat_queue import ChatQueue
from .color_config_ui import ColorConfigUi
from .colors import Colors
from .command_alias import CommandAlias
from .command_alias_ui import CommandAliasUi
from .flexible_security import FlexibleSecurity
from .fun_filters import FunFilters
from .logon_notifies import LogonNotifies
from .notify import Notify
from .online import Online
from .player import Player
from .player_notes import PlayerNotes
from .preferences import Preferences
from .professions import Professions
from .queue import Queue
from .security import Security
from .settings import Settings
from .settings_ui import SettingsUi
from .shortcuts import Shortcuts
from .shortcuts_ui import ShortcutsUi
from .statistics import Statistics
from .string_filter import StringFilter
from .string_filter_ui import StringFilterUi
from .time import TimeCore
from .timer_core import TimerCore
from .tools import Tools
from .user import User


def load_all(bot) -> None:
    Player(bot)
    Tools(bot)
    Colors(bot)
    Security(bot)
    Settings(bot)
    AccessControl(bot)
    CommandAlias(bot)
    Queue(bot)
    ChatQueue(bot)
    TimerCore(bot)
    ChatWrapper(bot)
    BotHelp(bot)
    Professions(bot)
    Shortcuts(bot)
    TimeCore(bot)
    PlayerNotes(bot)
    Preferences(bot)
    Statistics(bot)
    BotStatistics(bot)
    LogonNotifies(bot)
    FunFilters(bot)
    StringFilter(bot)
    FlexibleSecurity(bot)
    Alts(bot)
    Online(bot)
    User(bot)
    Notify(bot)
    Alias(bot)
    BuddyList(bot)
    BuddyQueue(bot)
    SettingsUi(bot)
    AccessControlUi(bot)
    ColorConfigUi(bot)
    CommandAliasUi(bot)
    ShortcutsUi(bot)
    StringFilterUi(bot)
