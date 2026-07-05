"""Ported (reduced) from Main/15_AoChatWrapper.php.

Registers as "chat". The whois-cache fallback wrapping in the original
(get_uid/get_uname falling back to the Whois module's DB cache) is
dropped since Core/Ao/Whois.php isn't ported -- these just forward to
Player and AOChat directly.
"""
from __future__ import annotations

from ..commodities.base import BasePassiveModule


class ChatWrapper(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("chat")

    def get_uid(self, user):
        return self.bot.core("player").id(user)

    def get_uname(self, uid):
        return self.bot.core("player").name(uid)

    def lookup_group(self, arg, type_hint: int = 0):
        return self.bot.aoc.lookup_group(arg, bool(type_hint))

    def get_gname(self, group):
        return self.bot.aoc.get_gname(group)

    def pgroup_join(self, group):
        import asyncio
        return asyncio.ensure_future(self.bot.aoc.privategroup_join(group))

    def pgroup_leave(self, group):
        import asyncio
        return asyncio.ensure_future(self.bot.aoc.privategroup_leave(group))

    def pgroup_invite(self, user):
        import asyncio
        return asyncio.ensure_future(self.bot.aoc.privategroup_invite(user))

    def pgroup_kick(self, user):
        import asyncio
        return asyncio.ensure_future(self.bot.aoc.privategroup_kick(user))

    def pgroup_status(self, group):
        return self.bot.aoc.group_status(group) if hasattr(self.bot.aoc, "group_status") else False

    def buddy_add(self, user, que: bool = True):
        import asyncio
        return asyncio.ensure_future(self.bot.aoc.buddy_add(user))

    def buddy_remove(self, user):
        import asyncio
        return asyncio.ensure_future(self.bot.aoc.buddy_remove(user))

    def buddy_exists(self, who):
        return self.bot.aoc.buddy_exists(who)

    def buddy_online(self, who):
        return self.bot.aoc.buddy_online(who)
