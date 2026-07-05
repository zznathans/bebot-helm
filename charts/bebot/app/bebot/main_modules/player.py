"""Ported (reduced) from Core/PlayerList.php.

Despite living in Core/ in the original (a directory nominally reserved
for optional/toggleable features), this module is load-bearing: Bot.send_tell/
send_pgroup/inc_tell/etc. all resolve names<->ids through `bot.core("player")`.

Two behavioural changes from the PHP version:
  * No sfEvent dispatcher -- AOChat.get_packet() calls `.add()` on this
    module directly when a CLIENT_NAME/CLIENT_LOOKUP packet arrives
    (the "direct call" pattern the PHP code already used everywhere else).
  * `id()`/`name()` only consult the in-memory cache and return BotError
    immediately on a cache miss, instead of PHP's synchronous "ask the
    chat server and block until it answers" lookup -- that blocking-socket
    trick doesn't have an asyncio equivalent without a lot more plumbing.
    Use `await bot.aoc.lookup_user(name)` first (see AOChat.lookup_user)
    to populate the cache for a name the bot hasn't seen yet, e.g. from an
    async admin-command handler. The whois-table DB fallback is also
    dropped since Core/Ao/Whois.php isn't ported.
"""
from __future__ import annotations

import time

from ..commodities.base import BasePassiveModule, BotError

CACHE_TTL = 21600


class Player(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("player")
        self._name_cache: dict[str, dict] = {}
        self._uid_cache: dict[int, dict] = {}

    def add(self, uid: int, name: str) -> bool:
        if uid in (0, -1) or uid is None:
            return False
        name = self.bot.core("tools").sanitize_player(name)
        expire = time.time() + CACHE_TTL
        self._name_cache[name] = {"id": uid, "expire": expire}
        self._uid_cache[uid] = {"name": name, "expire": expire}
        return True

    def id(self, uname):
        if isinstance(uname, BotError):
            return uname
        if not uname:
            self.error.set("Tried to get user id for an empty user name.")
            return self.error
        uname = self.bot.core("tools").sanitize_player(uname)
        if str(uname).isdigit():
            return int(uname)
        cached = self._name_cache.get(uname)
        if cached:
            return cached["id"]
        self.error.set(f"Unable to find player '{uname}' in cache. Look it up first via aoc.lookup_user().")
        return self.error

    def name(self, uid):
        if not isinstance(uid, int) and not str(uid).isdigit():
            return uid
        if uid in ("", None):
            self.error.set("name() called with empty string")
            return self.error
        uid = int(uid)
        cached = self._uid_cache.get(uid)
        if cached:
            return cached["name"]
        self.error.set(f"name() unable to find player with userid: {uid}")
        return self.error

    def exists(self, user) -> bool:
        if not user:
            return False
        if isinstance(user, int) or str(user).isdigit():
            return int(user) in self._uid_cache
        return user in self._name_cache

    def get_namecache(self) -> dict:
        return self._name_cache

    def get_uidcache(self) -> dict:
        return self._uid_cache
