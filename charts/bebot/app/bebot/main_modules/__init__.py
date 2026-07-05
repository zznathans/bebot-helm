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
from .aochat_wrapper import ChatWrapper
from .bot_help import BotHelp
from .chat_queue import ChatQueue
from .colors import Colors
from .command_alias import CommandAlias
from .player import Player
from .player_notes import PlayerNotes
from .preferences import Preferences
from .professions import Professions
from .queue import Queue
from .security import Security
from .settings import Settings
from .shortcuts import Shortcuts
from .time import TimeCore
from .timer_core import TimerCore
from .tools import Tools


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
