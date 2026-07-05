"""Tests for main_modules/admins_ui.py (ported from Modules/AdminsUi.php).

Central to what's being tested here: the real, already-ported Alts,
Online, Security, Settings, AccessControl, CommandAlias and Tools modules
-- AdminsUi is a thin rendering/dispatch layer on top of their real
behaviour (main/alt grouping, online-state colouring, access levels), so
faking those out would just mean re-implementing them in the test file.
Peripheral dependencies (Player existence checks and Chat buddy-list
state used only by `adminsfix`, and User.add()) get small local fakes to
keep control over exactly what `adminsfix` does.
"""
from __future__ import annotations

from bebot.commodities.base import BotError
from bebot.main_modules.access_control import AccessControl
from bebot.main_modules.admins_ui import AdminsUi
from bebot.main_modules.alts import Alts
from bebot.main_modules.command_alias import CommandAlias
from bebot.main_modules.online import Online
from bebot.main_modules.security import ADMIN, LEADER, MEMBER, SUPERADMIN
from bebot.main_modules.security import Security
from bebot.main_modules.settings import Settings
from bebot.main_modules.tools import Tools
from fakes import FakePlayer


class FakeChat:
    """Peripheral: buddy-list state, used both by Online.get_online_state()
    and directly by AdminsUi.all_fixer() during `adminsfix`."""

    def __init__(self, online_buddies=None, known_buddies=None):
        self.online_buddies = set(online_buddies or [])
        self.known_buddies = set(known_buddies or []) | self.online_buddies
        self.added: list[str] = []

    def buddy_exists(self, who):
        return who in self.known_buddies

    def buddy_online(self, who):
        return who in self.online_buddies

    def buddy_add(self, who, que: bool = True):
        self.added.append(who)
        self.known_buddies.add(who)


class FakeNotify:
    def check(self, name):
        return True


class FakeUser:
    """Peripheral: records add() calls made by `adminsfix`'s all_fixer()."""

    def __init__(self):
        self.added: list[tuple] = []

    def add(self, source, name, id=False, user_level=0, silent=0):
        self.added.append((source, name, id, user_level, silent))
        return f"Player {name} added"


class FakeDb:
    """Answers the read-only queries admins_ui/its Core dependencies issue,
    based on small in-memory tables the test sets up; every other query
    (setup CREATE TABLEs, settings/access_control housekeeping) behaves
    like the default fixture fake (empty result / accepted no-op)."""

    def __init__(self, alt_rows=None, group_rows=None, member_rows=None, user_rows=None):
        self.alt_rows = alt_rows or []
        self.group_rows = group_rows or []
        self.member_rows = member_rows or {}
        self.user_rows = user_rows or {}
        self.queries: list[str] = []

    def query(self, sql: str) -> bool:
        self.queries.append(sql)
        return True

    def select(self, sql: str, as_dict: bool = False):
        if "#___alts" in sql:
            return list(self.alt_rows)
        if "#___security_groups" in sql:
            return [dict(row) for row in self.group_rows] if as_dict else [
                (r["gid"], r["name"], r["description"], r["access_level"]) for r in self.group_rows
            ]
        if "#___security_members" in sql:
            for gid, members in self.member_rows.items():
                if f"gid = '{gid}'" in sql:
                    return [(m,) for m in members]
            return []
        if "#___users" in sql:
            for name, level in self.user_rows.items():
                if f"nickname = '{name}'" in sql:
                    return [(level,)]
            return []
        return []

    def real_escape_string(self, value) -> str:
        return str(value).replace("'", "\\'")

    def define_tablename(self, table: str, use_prefix) -> str:
        return table


def make_ui(bot, monkeypatch, alt_rows=None, group_rows=None, member_rows=None, user_rows=None,
            online_buddies=None, known_buddies=None, player=None, chat=None, user=None):
    fake_db = FakeDb(alt_rows=alt_rows, group_rows=group_rows, member_rows=member_rows, user_rows=user_rows)
    monkeypatch.setattr(bot, "db", fake_db)

    Tools(bot)
    Settings(bot)
    AccessControl(bot)
    CommandAlias(bot)
    Security(bot)
    bot.register_module(player or FakePlayer(), "player")
    bot.register_module(chat or FakeChat(online_buddies=online_buddies, known_buddies=known_buddies), "chat")
    bot.register_module(FakeNotify(), "notify")
    Alts(bot)
    Online(bot)
    bot.register_module(user or FakeUser(), "user")
    return AdminsUi(bot)


DEFAULT_GROUPS = [
    {"gid": 1, "name": "Superadmins", "description": "", "access_level": SUPERADMIN},
    {"gid": 2, "name": "Admins", "description": "", "access_level": ADMIN},
    {"gid": 3, "name": "Leaders", "description": "", "access_level": LEADER},
    {"gid": 4, "name": "Members", "description": "", "access_level": MEMBER},
]


# -- construction / registration --------------------------------------------------

def test_registers_as_admins_ui_module(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    assert bot.core("admins_ui") is module


def test_registers_admins_and_adminsfix_on_all_channels(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    for channel in ("tell", "gc", "pgmsg"):
        assert bot.commands[channel]["admins"] is module
        assert bot.commands[channel]["adminsfix"] is module


def test_registers_leaders_alias(bot, monkeypatch):
    make_ui(bot, monkeypatch)
    assert bot.core("command_alias").exists("leaders")
    assert bot.core("command_alias").replace("leaders all") == "admins all"


def test_help_describes_commands(bot, monkeypatch):
    module = make_ui(bot, monkeypatch)
    assert "admins" in module.help["command"]
    assert "admins all" in module.help["command"]
    assert "adminsfix" in module.help["command"]


# -- admins_blob: basic shape -------------------------------------------------------

def test_admins_short_list_includes_view_all_link(bot, monkeypatch):
    module = make_ui(bot, monkeypatch, group_rows=DEFAULT_GROUPS)
    result = module.admins_blob("admins")
    assert "Admins list" in result
    assert "admins all" in result
    assert "View all bot admins" in result


def test_admins_all_omits_view_all_link(bot, monkeypatch):
    module = make_ui(bot, monkeypatch, group_rows=DEFAULT_GROUPS)
    result = module.admins_blob("admins all")
    assert "View all bot admins" not in result


def test_admins_short_list_shows_counts_even_with_nobody_online(bot, monkeypatch):
    module = make_ui(
        bot, monkeypatch,
        group_rows=DEFAULT_GROUPS,
        member_rows={1: ["Suzy"], 2: ["Bob"], 3: []},
    )
    result = module.admins_blob("admins")
    assert "1 ##highlight##Superadmin(s) (SA)##end##" in result
    assert "1 ##highlight##Admin(s) (A)##end##" in result
    assert "0 ##highlight##Leader(s) (L)##end##" in result
    # Nobody is online and this isn't "admins all" -- names are suppressed.
    assert "Suzy" not in result
    assert "Bob" not in result


def test_admins_short_list_shows_online_admin_even_without_all(bot, monkeypatch):
    module = make_ui(
        bot, monkeypatch,
        group_rows=DEFAULT_GROUPS,
        member_rows={1: ["Suzy"], 2: [], 3: []},
        online_buddies=["Suzy"],
    )
    result = module.admins_blob("admins")
    assert "Suzy" in result
    assert "##green##Online##end##" in result


def test_admins_all_shows_offline_admins_too(bot, monkeypatch):
    module = make_ui(
        bot, monkeypatch,
        group_rows=DEFAULT_GROUPS,
        member_rows={1: ["Suzy"], 2: [], 3: []},
        known_buddies=["Suzy"],
    )
    result = module.admins_blob("admins all")
    assert "Suzy" in result
    assert "##red##Offline##end##" in result


def test_admins_ignores_member_level_group(bot, monkeypatch):
    module = make_ui(
        bot, monkeypatch,
        group_rows=DEFAULT_GROUPS,
        member_rows={1: [], 2: [], 3: [], 4: ["Regularjoe"]},
    )
    result = module.admins_blob("admins all")
    assert "Regularjoe" not in result


def test_admins_owner_section_shown_when_all(bot, monkeypatch):
    module = make_ui(bot, monkeypatch, group_rows=DEFAULT_GROUPS)
    result = module.admins_blob("admins all")
    assert "##highlight##Owner (O)##end##" in result
    assert "Owner" in result


def test_admins_owner_alts_listed(bot, monkeypatch):
    module = make_ui(
        bot, monkeypatch,
        alt_rows=[("Owner", "Owneralt")],
        group_rows=DEFAULT_GROUPS,
    )
    result = module.admins_blob("admins all")
    assert "Owneralt" in result


def test_admins_groups_multiple_alts_under_one_main(bot, monkeypatch):
    module = make_ui(
        bot, monkeypatch,
        alt_rows=[("Suzy", "Suzyalt")],
        group_rows=DEFAULT_GROUPS,
        member_rows={1: ["Suzy"], 2: [], 3: []},
    )
    result = module.admins_blob("admins all")
    assert "Suzy" in result
    assert "Suzyalt" in result


def test_admins_members_sorted_by_main_name(bot, monkeypatch):
    module = make_ui(
        bot, monkeypatch,
        group_rows=DEFAULT_GROUPS,
        member_rows={1: ["Zed", "Amy"], 2: [], 3: []},
    )
    result = module.admins_blob("admins all")
    assert result.index("Amy") < result.index("Zed")


def test_admins_dedupes_alts_mapping_to_same_main(bot, monkeypatch):
    # Two "members" that are actually alts of the same main should only
    # produce one entry (mirrors PHP's $mains['SA'][$main] = true dedupe).
    module = make_ui(
        bot, monkeypatch,
        alt_rows=[("Suzy", "Suzyalt")],
        group_rows=DEFAULT_GROUPS,
        member_rows={1: ["Suzy", "Suzyalt"], 2: [], 3: []},
    )
    result = module.admins_blob("admins all")
    assert result.count("- ##highlight##Suzy##end##") == 1


# -- command_handler dispatch -------------------------------------------------------

def test_command_handler_dispatches_to_admins_blob(bot, monkeypatch):
    module = make_ui(bot, monkeypatch, group_rows=DEFAULT_GROUPS)
    result = module.command_handler("Someadmin", "admins", "tell")
    assert "Admins list" in result


# -- adminsfix / all_fixer -----------------------------------------------------------

def test_adminsfix_forces_all_true(bot, monkeypatch):
    module = make_ui(
        bot, monkeypatch,
        group_rows=DEFAULT_GROUPS,
        member_rows={1: ["Suzy"], 2: [], 3: []},
    )
    result = module.admins_blob("adminsfix")
    assert "Suzy" in result
    assert "View all bot admins" not in result


def test_all_fixer_adds_missing_user_as_member(bot, monkeypatch):
    fake_user = FakeUser()
    module = make_ui(
        bot, monkeypatch,
        group_rows=DEFAULT_GROUPS,
        member_rows={1: ["Suzy"], 2: [], 3: []},
        user=fake_user,
    )
    module.admins_blob("adminsfix")
    assert (module.bot.botname, "Suzy", 0, MEMBER, 1) in fake_user.added


def test_all_fixer_skips_add_when_already_a_member(bot, monkeypatch):
    fake_user = FakeUser()
    module = make_ui(
        bot, monkeypatch,
        group_rows=DEFAULT_GROUPS,
        member_rows={1: ["Suzy"], 2: [], 3: []},
        # Owner is also run through all_fixer() by adminsfix -- give it a
        # row too so this test only asserts on Suzy's (the thing under
        # test) add() calls.
        user_rows={"Suzy": 2, "Owner": 2},
        user=fake_user,
    )
    module.admins_blob("adminsfix")
    assert fake_user.added == []


def test_all_fixer_re_adds_when_user_level_not_member(bot, monkeypatch):
    fake_user = FakeUser()
    module = make_ui(
        bot, monkeypatch,
        group_rows=DEFAULT_GROUPS,
        member_rows={1: ["Suzy"], 2: [], 3: []},
        user_rows={"Suzy": 0},
        user=fake_user,
    )
    module.admins_blob("adminsfix")
    assert (module.bot.botname, "Suzy", 0, MEMBER, 1) in fake_user.added


def test_all_fixer_adds_buddy_if_missing(bot, monkeypatch):
    fake_chat = FakeChat()
    module = make_ui(
        bot, monkeypatch,
        group_rows=DEFAULT_GROUPS,
        member_rows={1: ["Suzy"], 2: [], 3: []},
        chat=fake_chat,
    )
    module.admins_blob("adminsfix")
    assert "Suzy" in fake_chat.added


def test_all_fixer_skips_add_buddy_if_already_present(bot, monkeypatch):
    fake_chat = FakeChat(known_buddies=["Suzy"])
    module = make_ui(
        bot, monkeypatch,
        group_rows=DEFAULT_GROUPS,
        member_rows={1: ["Suzy"], 2: [], 3: []},
        chat=fake_chat,
    )
    module.admins_blob("adminsfix")
    assert "Suzy" not in fake_chat.added


class _AlwaysBotErrorPlayer:
    """id() always reports the player doesn't exist, e.g. a deleted char."""

    def __init__(self, bot):
        self._bot = bot

    def id(self, name):
        err = BotError(self._bot, "player")
        err.set("no such player", log=False)
        return err


def test_all_fixer_skips_nonexistent_player(bot, monkeypatch):
    fake_user = FakeUser()
    fake_chat = FakeChat()
    module = make_ui(
        bot, monkeypatch,
        group_rows=DEFAULT_GROUPS,
        member_rows={1: ["Ghost"], 2: [], 3: []},
        player=_AlwaysBotErrorPlayer(bot),
        chat=fake_chat,
        user=fake_user,
    )
    module.admins_blob("adminsfix")
    assert fake_user.added == []
    assert fake_chat.added == []


def test_admins_all_fixer_runs_for_owner_and_alts_too(bot, monkeypatch):
    fake_chat = FakeChat()
    module = make_ui(
        bot, monkeypatch,
        alt_rows=[("Owner", "Owneralt")],
        group_rows=DEFAULT_GROUPS,
        chat=fake_chat,
    )
    module.admins_blob("adminsfix")
    assert "Owner" in fake_chat.added
    assert "Owneralt" in fake_chat.added
