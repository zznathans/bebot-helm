from fakes import FakePlayer, RecordingModule

from bebot.main_modules.buddy_list import BuddyList


class FakeNotify:
    def __init__(self, members: set[str] | None = None):
        self.members = set(members or ())

    def check(self, name: str) -> bool:
        return name in self.members


class FakeSecurityLevels:
    def __init__(self, levels: dict[str, int] | None = None):
        self.levels = dict(levels or {})

    def get_access_level(self, player: str) -> int:
        return self.levels.get(player, 1)

    def get_access_name(self, level: int) -> str:
        return {1: "GUEST", 2: "MEMBER"}.get(level, "ANONYMOUS")


class FakeChat:
    def __init__(self):
        self.removed: list[str] = []

    def buddy_remove(self, user) -> None:
        self.removed.append(user)


def make_buddy_list(bot, names=None, members=None, levels=None):
    bot.register_module(FakePlayer(names=names or {}), "player")
    bot.register_module(FakeNotify(members=members), "notify")
    bot.register_module(FakeSecurityLevels(levels=levels), "security")
    bot.register_module(FakeChat(), "chat")
    return BuddyList(bot)


# -- construction -------------------------------------------------------------

def test_registers_as_buddy_module(bot):
    module = make_buddy_list(bot)
    assert bot.core("buddy") is module


# -- on_buddy_onoff(): non-members ---------------------------------------------

def test_non_member_logon_is_removed_from_buddy_list(bot):
    module = make_buddy_list(bot, names={42: "Rando"}, members=set())
    module.on_buddy_onoff(42, 1)
    chat = bot.core("chat")
    assert chat.removed == ["Rando"]
    # Not a notify member -- must not be tracked in the online cache.
    assert "Rando" not in module.online


def test_empty_user_name_is_a_noop(bot):
    module = make_buddy_list(bot, names={}, members=set())
    # FakePlayer.name() falls back to str(uid) for unknown ids, so force an
    # empty-string resolution to exercise the guard clause directly.
    module.bot.core("player").name = lambda uid: ""
    module.on_buddy_onoff(99, 1)
    assert module.online == {}
    assert bot.core("chat").removed == []


# -- on_buddy_onoff(): members, online-tracking dedup guards -------------------

def test_member_logon_marks_user_online(bot):
    module = make_buddy_list(bot, names={1: "Memberguy"}, members={"Memberguy"})
    module.on_buddy_onoff(1, 1)
    assert module.online["Memberguy"] == "Memberguy"


def test_member_duplicate_logon_is_ignored(bot):
    module = make_buddy_list(bot, names={1: "Memberguy"}, members={"Memberguy"})
    module.on_buddy_onoff(1, 1)
    module.on_buddy_onoff(1, 1)  # already online -- must not raise or double count
    assert module.online == {"Memberguy": "Memberguy"}


def test_member_logoff_clears_online(bot):
    module = make_buddy_list(bot, names={1: "Memberguy"}, members={"Memberguy"})
    module.on_buddy_onoff(1, 1)
    module.on_buddy_onoff(1, 0)
    assert "Memberguy" not in module.online


def test_member_logoff_without_prior_logon_is_ignored(bot):
    module = make_buddy_list(bot, names={1: "Memberguy"}, members={"Memberguy"})
    module.on_buddy_onoff(1, 0)  # never logged on -- must not raise
    assert module.online == {}


def test_member_is_never_removed_via_chat_buddy_remove(bot):
    module = make_buddy_list(bot, names={1: "Memberguy"}, members={"Memberguy"})
    module.on_buddy_onoff(1, 1)
    assert bot.core("chat").removed == []


# -- dispatch to modules registered for the "buddy" event ----------------------

def test_dispatches_to_registered_buddy_event_modules(bot):
    module = make_buddy_list(bot, names={1: "Memberguy"}, members={"Memberguy"})
    subscriber = RecordingModule("subscriber")
    bot.register_event("buddy", None, subscriber)

    module.on_buddy_onoff(1, 1)

    assert subscriber.calls == [("buddy", ("Memberguy", 1), {})]


def test_dispatches_logoff_with_online_flag_zero(bot):
    module = make_buddy_list(bot, names={1: "Memberguy"}, members={"Memberguy"})
    subscriber = RecordingModule("subscriber")
    bot.register_event("buddy", None, subscriber)

    module.on_buddy_onoff(1, 1)
    subscriber.calls.clear()
    module.on_buddy_onoff(1, 0)

    assert subscriber.calls == [("buddy", ("Memberguy", 0), {})]


def test_dispatches_to_multiple_registered_modules(bot):
    # Bot.register_event() keys subscribers by type(module).__name__, so two
    # distinct fake *classes* are needed here to prove both get dispatched to
    # (two instances of the same class would collide on that key).
    class SubA(RecordingModule):
        pass

    class SubB(RecordingModule):
        pass

    module = make_buddy_list(bot, names={1: "Memberguy"}, members={"Memberguy"})
    sub1 = SubA("sub1")
    sub2 = SubB("sub2")
    bot.register_event("buddy", None, sub1)
    bot.register_event("buddy", None, sub2)

    module.on_buddy_onoff(1, 1)

    assert sub1.calls == [("buddy", ("Memberguy", 1), {})]
    assert sub2.calls == [("buddy", ("Memberguy", 1), {})]


def test_no_registered_modules_does_not_raise(bot):
    module = make_buddy_list(bot, names={1: "Memberguy"}, members={"Memberguy"})
    module.on_buddy_onoff(1, 1)  # nothing registered for "buddy" -- must not raise
