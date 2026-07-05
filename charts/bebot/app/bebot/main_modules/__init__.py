"""Fixed load order for the ported subset of Main/*.php.

Replaces Main.php's `$bot->load_files('Main', 'Main')` directory scan --
there is no dynamic Core/Modules/Custom plugin loading in this port yet,
just this hardcoded list of modules, instantiated in dependency order
(each module registers itself onto `bot` via `register_module()` in its
constructor, so order only matters where a constructor calls
`bot.core(...)` on another module).
"""
from __future__ import annotations

from .about import About
from .access_control import AccessControl
from .access_control_ui import AccessControlUi
from .admins_ui import AdminsUi
from .afk import Afk
from .alias import Alias
from .alts import Alts
from .aochat_wrapper import ChatWrapper
from .auto_user_add import AutoUserAdd
from .bans_manager_ui import BansManagerUi
from .bot_help import BotHelp
from .bot_statistics import BotStatistics
from .bot_statistics_ui import BotStatisticsUi
from .buddy_list import BuddyList
from .buddy_queue import BuddyQueue
from .calc import Calc
from .chat_queue import ChatQueue
from .color_config_ui import ColorConfigUi
from .colors import Colors
from .command_alias import CommandAlias
from .command_alias_ui import CommandAliasUi
from .countdown import Countdown
from .flexible_security import FlexibleSecurity
from .fun_filters import FunFilters
from .is_module import IsModule
from .logon_notifies import LogonNotifies
from .mail import Mail
from .news import News
from .notify import Notify
from .notify_ui import NotifyUi
from .nroll import Nroll
from .online import Online
from .online_count import OnlineCounting
from .ping import Ping
from .player import Player
from .player_notes import PlayerNotes
from .player_notes_ui import PlayerNotesUi
from .preferences import Preferences
from .preferences_ui import PreferencesUi
from .professions import Professions
from .queue import Queue
from .quotes import Quotes
from .rally import Rally
from .roll import Roll
from .rules import Rules
from .say import Say
from .scripts import Scripts
from .security import Security
from .set_debug import SetDebug
from .settings import Settings
from .settings_ui import SettingsUi
from .shortcuts import Shortcuts
from .shortcuts_ui import ShortcutsUi
from .shutdown import Shutdown
from .statistics import Statistics
from .string_filter import StringFilter
from .string_filter_ui import StringFilterUi
from .time import TimeCore
from .timer_core import TimerCore
from .timer_relay import TimerRelay
from .timer_ui import TimerUi
from .tools import Tools
from .user import User
from .user_admin import UserAdmin


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
    PlayerNotesUi(bot)
    PreferencesUi(bot)
    BotStatisticsUi(bot)
    AutoUserAdd(bot)
    BansManagerUi(bot)
    AdminsUi(bot)
    Afk(bot)
    NotifyUi(bot)
    About(bot)
    Calc(bot)
    Countdown(bot)
    IsModule(bot)
    Mail(bot)
    News(bot)
    OnlineCounting(bot)
    Ping(bot)
    Quotes(bot)
    Rally(bot)
    Roll(bot)
    Nroll(bot)
    Rules(bot)
    Say(bot)
    Scripts(bot)
    SetDebug(bot)
    Shutdown(bot)
    TimerRelay(bot)
    TimerUi(bot)
    UserAdmin(bot)
