"""Tests for main_modules/user_admin.py (ported from Modules/UserAdmin.php).

UserAdmin only depends on core("chat") and core("tools") (verified against
the PHP source) plus direct bot.db/bot.aoc.buddies access, so those two are
faked locally and Tools is the one real dependency instantiated (its
chatcmd()/make_blob() output is asserted on directly, mirroring the
precedent in test_module_settings_ui.py of using the real Tools module
rather than re-implementing its blob/link formatting in a fake).
"""
from __future__ import annotations

import re

from bebot.main_modules.security import ANONYMOUS, BANNED, GUEST, MEMBER
from bebot.main_modules.tools import Tools
from bebot.main_modules.user_admin import UserAdmin


class FakeChat:
    def __init__(self, names: dict[int, str] | None = None, known_buddies=None):
        self.names = dict(names or {})
        self.known_buddies = set(known_buddies or [])
        self.added: list[int] = []
        self.removed: list[int] = []

    def get_uname(self, uid):
        return self.names.get(uid, str(uid))

    def buddy_exists(self, uid):
        return uid in self.known_buddies

    def buddy_add(self, uid, que: bool = True):
        self.added.append(uid)
        self.known_buddies.add(uid)

    def buddy_remove(self, uid):
        self.removed.append(uid)
        self.known_buddies.discard(uid)


class FakeAoc:
    def __init__(self, buddies=None):
        self.buddies = dict(buddies or {})


class FakeDb:
    """Answers the raw SQL user_admin.py issues against small in-memory
    tables the test sets up."""

    def __init__(self, users=None, alts=None, whois=None):
        # users: list of dicts with char_id, nickname, last_seen, user_level
        self.users = list(users or [])
        self.alts = list(alts or [])  # list of (alt, main)
        self.whois = list(whois or [])  # list of (ID, nickname)
        self.queries: list[str] = []

    def query(self, sql: str) -> bool:
        self.queries.append(sql)
        return True

    def select(self, sql: str, as_dict: bool = False):
        if "#___alts" in sql:
            if "NOT IN" in sql:
                member_names = {r["nickname"] for r in self.users if r["user_level"] == MEMBER}
                rows = [row for row in self.alts if row[0] not in member_names]
            else:
                rows = list(self.alts)
            rows = sorted(rows, key=lambda r: r[0])
            return [{"alt": a, "main": m} for a, m in rows]
        if "#___whois" in sql:
            rows = sorted(self.whois, key=lambda r: r[1])
            return [{"ID": i, "nickname": n} for i, n in rows]
        if "FROM #___users u" in sql and "user_level >= 0" not in sql:
            rows = list(self.users)
            if "user_level = " in sql:
                m = re.search(r"user_level = (-?\d+)", sql)
                if m:
                    lvl = int(m.group(1))
                    rows = [r for r in rows if r["user_level"] == lvl]
                m2 = re.search(r"last_seen > 0 AND last_seen < (\d+)", sql)
                if m2:
                    cutoff = int(m2.group(1))
                    rows = [r for r in rows if r["last_seen"] and r["last_seen"] < cutoff]
            if "ORDER BY u.last_seen DESC" in sql:
                rows = sorted(rows, key=lambda r: r["last_seen"], reverse=True)
            else:
                rows = sorted(rows, key=lambda r: r["nickname"])
            return [dict(r) for r in rows]
        if "user_level >= 0 AND last_seen = 0" in sql:
            rows = [r for r in self.users if r["user_level"] >= 0 and r["last_seen"] == 0]
            rows = sorted(rows, key=lambda r: r["nickname"])
            return [dict(r) for r in rows]
        return []

    def real_escape_string(self, value) -> str:
        return str(value).replace("'", "\\'")

    def define_tablename(self, table: str, use_prefix) -> str:
        return table


def make_module(bot, monkeypatch, users=None, alts=None, whois=None, buddies=None,
                 names=None, known_buddies=None, chat=None, db=None):
    fake_db = db or FakeDb(users=users, alts=alts, whois=whois)
    monkeypatch.setattr(bot, "db", fake_db)
    monkeypatch.setattr(bot.aoc, "buddies", dict(buddies or {}))
    bot.register_module(chat or FakeChat(names=names, known_buddies=known_buddies), "chat")
    Tools(bot)
    return UserAdmin(bot), fake_db


def _user(char_id, nickname, level=MEMBER, last_seen=1000):
    return {"char_id": char_id, "nickname": nickname, "last_seen": last_seen, "user_level": level}


# -- construction / registration --------------------------------------------------

def test_registers_as_useradmin_module(bot, monkeypatch):
    module, _ = make_module(bot, monkeypatch)
    assert bot.core("useradmin") is module


def test_registers_useradmin_command_on_all_channels(bot, monkeypatch):
    module, _ = make_module(bot, monkeypatch)
    for channel in ("tell", "gc", "pgmsg"):
        assert bot.commands[channel]["useradmin"] is module


def test_help_describes_commands(bot, monkeypatch):
    module, _ = make_module(bot, monkeypatch)
    assert "useradmin" in module.help["command"]
    assert "useradmin userlist" in module.help["command"]
    assert "useradmin buddylist fix" in module.help["command"]
    assert "notes" in module.help


# -- prefix_output ------------------------------------------------------------------

def test_prefix_output_wraps_truthy_result(bot, monkeypatch):
    module, _ = make_module(bot, monkeypatch)
    assert module._prefix_output("hi") == "##white####bluegray##[-UserAdmin-]##end## :: hi##end##"


def test_prefix_output_passes_through_false(bot, monkeypatch):
    module, _ = make_module(bot, monkeypatch)
    assert module._prefix_output(False) is False
    assert module._prefix_output("") is False


# -- userlist -----------------------------------------------------------------------

def test_userlist_empty(bot, monkeypatch):
    module, _ = make_module(bot, monkeypatch)
    result = module.command_handler("Boss", "useradmin userlist", "tell")
    assert "No matching users found" in result


def test_userlist_all_lists_users(bot, monkeypatch):
    users = [_user(1, "Suzy"), _user(2, "Bob", level=GUEST)]
    module, _ = make_module(bot, monkeypatch, users=users)
    result = module.command_handler("Boss", "useradmin userlist", "tell")
    assert "Found ##seablue##2##end## users" in result
    assert "Suzy" in result
    assert "Bob" in result


def test_userlist_filtered_by_level(bot, monkeypatch):
    users = [_user(1, "Suzy"), _user(2, "Bob", level=GUEST)]
    module, _ = make_module(bot, monkeypatch, users=users)
    result = module.command_handler("Boss", "useradmin userlist member", "tell")
    assert "Suzy" in result
    assert "Bob" not in result


def test_userlist_never_shows_kick_link(bot, monkeypatch):
    users = [_user(1, "Ghost", level=MEMBER, last_seen=0)]
    module, _ = make_module(bot, monkeypatch, users=users)
    result = module.command_handler("Boss", "useradmin userlist never", "tell")
    assert "Ghost" in result
    assert "kick Ghost" in result


def test_userlist_clear_guest(bot, monkeypatch):
    module, fake_db = make_module(bot, monkeypatch)
    result = module.command_handler("Boss", "useradmin userlist clear guest", "tell")
    assert "Cleared guest entries" in result
    assert any("user_level = 1" in q for q in fake_db.queries)


def test_userlist_clear_never(bot, monkeypatch):
    module, fake_db = make_module(bot, monkeypatch)
    result = module.command_handler("Boss", "useradmin userlist clear never", "tell")
    assert "Cleared all never seen entries" in result


# -- memberlist ---------------------------------------------------------------------

def test_memberlist_empty(bot, monkeypatch):
    module, _ = make_module(bot, monkeypatch)
    result = module.command_handler("Boss", "useradmin memberlist", "tell")
    assert "memberlist is empty" in result


def test_memberlist_all(bot, monkeypatch):
    users = [_user(1, "Suzy"), _user(2, "Bob", level=GUEST)]
    module, _ = make_module(bot, monkeypatch, users=users)
    result = module.command_handler("Boss", "useradmin memberlist", "tell")
    assert "Suzy" in result
    assert "Bob" not in result


def test_memberlist_main_and_alt(bot, monkeypatch):
    users = [_user(1, "Suzy"), _user(2, "Suzyalt")]
    module, _ = make_module(bot, monkeypatch, users=users, alts=[("Suzyalt", "Suzy")])
    main_result = module.command_handler("Boss", "useradmin memberlist main", "tell")
    alt_result = module.command_handler("Boss", "useradmin memberlist alt", "tell")
    assert "Suzy" in main_result and "Suzyalt" not in main_result
    assert "Suzyalt" in alt_result


def test_memberlist_idle_lists_with_kick_link(bot, monkeypatch):
    import time
    now = int(time.time())
    users = [_user(1, "Stale", last_seen=now - 200 * 86400)]
    module, _ = make_module(bot, monkeypatch, users=users)
    result = module.command_handler("Boss", "useradmin memberlist idle 90", "tell")
    assert "Stale" in result
    assert "kick Stale" in result


def test_memberlist_cidle_no_listing(bot, monkeypatch):
    import time
    now = int(time.time())
    users = [_user(1, "Stale", last_seen=now - 200 * 86400)]
    module, _ = make_module(bot, monkeypatch, users=users)
    result = module.command_handler("Boss", "useradmin memberlist cidle 90", "tell")
    assert "Found ##seablue##1##end## idle members" in result
    assert "Stale" not in result


def test_memberlist_clear_dispatches_to_clear_users(bot, monkeypatch):
    module, fake_db = make_module(bot, monkeypatch)
    result = module.command_handler("Boss", "useradmin memberlist clear 90", "tell")
    assert "Cleared at least 90 days old entries" in result


# -- altlist ------------------------------------------------------------------------

def test_altlist_list_obsolete(bot, monkeypatch):
    users = [_user(1, "Suzy")]
    module, _ = make_module(bot, monkeypatch, users=users, alts=[("Oldalt", "Retired")])
    result = module.command_handler("Boss", "useradmin altlist list obsolete", "tell")
    assert "Oldalt (Retired)" in result


def test_altlist_list_obsolete_none_found(bot, monkeypatch):
    module, _ = make_module(bot, monkeypatch)
    result = module.command_handler("Boss", "useradmin altlist list obsolete", "tell")
    assert "No obsolete entries found" in result


def test_altlist_clear_obsolete(bot, monkeypatch):
    module, fake_db = make_module(bot, monkeypatch)
    result = module.command_handler("Boss", "useradmin altlist clear obsolete", "tell")
    assert "Cleared obsolete entries from" in result
    assert any("#___alts" in q for q in fake_db.queries)


def test_altlist_clear_all_is_a_noop(bot, monkeypatch):
    # Faithful PHP quirk: the regex accepts "all" but clear_alts() has no
    # case for it, so it silently returns False (no reply).
    module, _ = make_module(bot, monkeypatch)
    result = module.command_handler("Boss", "useradmin altlist clear all", "tell")
    assert result is False


# -- buddylist ----------------------------------------------------------------------

def test_buddylist_empty(bot, monkeypatch):
    module, _ = make_module(bot, monkeypatch)
    result = module.command_handler("Boss", "useradmin buddylist", "tell")
    assert "No buddies in <botname>'s buddylist!" in result


def test_buddylist_lists_buddies(bot, monkeypatch):
    module, _ = make_module(bot, monkeypatch, buddies={5: 1}, names={5: "Suzy"})
    result = module.command_handler("Boss", "useradmin buddylist", "tell")
    assert "Found ##seablue##1##end## buddies" in result
    assert "Suzy" in result


def test_buddylist_missing(bot, monkeypatch):
    users = [_user(5, "Suzy"), _user(6, "Bob")]
    module, _ = make_module(bot, monkeypatch, users=users, buddies={5: 1})
    result = module.command_handler("Boss", "useradmin buddylist missing", "tell")
    assert "Bob" in result
    assert "Suzy" not in result
    assert "Found ##seablue##1##end## members not in buddylist" in result


def test_buddylist_missing_none_left(bot, monkeypatch):
    users = [_user(5, "Suzy")]
    module, _ = make_module(bot, monkeypatch, users=users, buddies={5: 1})
    result = module.command_handler("Boss", "useradmin buddylist missing", "tell")
    assert "All current members are in <botname>'s memberlist" in result


def test_buddylist_missing_no_members(bot, monkeypatch):
    module, _ = make_module(bot, monkeypatch)
    result = module.command_handler("Boss", "useradmin buddylist missing", "tell")
    assert "No members in <botname>'s memberlist!" in result


def test_buddylist_clear(bot, monkeypatch):
    fake_chat = FakeChat()
    module, _ = make_module(bot, monkeypatch, buddies={5: 1, 6: 1}, chat=fake_chat)
    result = module.command_handler("Boss", "useradmin buddylist clear", "tell")
    assert "Removed ##seablue##2##end## buddies" in result
    assert sorted(fake_chat.removed) == [5, 6]


def test_buddylist_fix_adds_missing_and_removes_extra(bot, monkeypatch):
    fake_chat = FakeChat()
    users = [_user(5, "Suzy")]
    module, _ = make_module(bot, monkeypatch, users=users, buddies={9: 1}, chat=fake_chat)
    result = module.command_handler("Boss", "useradmin buddylist fix", "tell")
    assert "Fixed ##seablue##2##end##" in result
    assert "1 deleted" in result
    assert "1 added" in result
    assert fake_chat.added == [5]
    assert fake_chat.removed == [9]


def test_buddy_add_new(bot, monkeypatch):
    fake_chat = FakeChat(names={5: "Suzy"})
    module, _ = make_module(bot, monkeypatch, chat=fake_chat)
    result = module.command_handler("Boss", "useradmin buddy add 5", "tell")
    assert "Added ##seablue##Suzy##end##" in result
    assert fake_chat.added == [5]


def test_buddy_add_already_present(bot, monkeypatch):
    fake_chat = FakeChat(names={5: "Suzy"}, known_buddies=[5])
    module, _ = make_module(bot, monkeypatch, chat=fake_chat)
    result = module.command_handler("Boss", "useradmin buddy add 5", "tell")
    assert "is already on <botname>'s buddylist" in result
    assert fake_chat.added == []


def test_buddy_remove_existing(bot, monkeypatch):
    fake_chat = FakeChat(names={5: "Suzy"}, known_buddies=[5])
    module, _ = make_module(bot, monkeypatch, chat=fake_chat)
    result = module.command_handler("Boss", "useradmin buddy remove 5", "tell")
    assert "Removed ##seablue##Suzy##end##" in result
    assert fake_chat.removed == [5]


def test_buddy_remove_not_present(bot, monkeypatch):
    fake_chat = FakeChat(names={5: "Suzy"})
    module, _ = make_module(bot, monkeypatch, chat=fake_chat)
    result = module.command_handler("Boss", "useradmin buddy remove 5", "tell")
    assert "is not on <botname>'s buddylist" in result
    assert fake_chat.removed == []


# -- whois clearing -------------------------------------------------------------------

def test_whois_clear_all(bot, monkeypatch):
    module, fake_db = make_module(bot, monkeypatch)
    result = module.command_handler("Boss", "useradmin whois clear all", "tell")
    assert "Cleared all entries from <botname>'s whois database" in result
    assert any("TRUNCATE" in q for q in fake_db.queries)


def test_whois_clear_obsolete(bot, monkeypatch):
    module, fake_db = make_module(bot, monkeypatch)
    result = module.command_handler("Boss", "useradmin whois clear obsolete", "tell")
    assert "Cleared obsolete entries from <botname>'s whois database" in result


def test_whois_clear_member(bot, monkeypatch):
    module, fake_db = make_module(bot, monkeypatch)
    result = module.command_handler("Boss", "useradmin whois clear member", "tell")
    assert "Cleared member entries from <botname>'s whois database" in result


# -- overview -----------------------------------------------------------------------

def test_overview_sends_tell_and_returns_no_reply(bot, monkeypatch):
    sent = []
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))
    users = [_user(1, "Suzy"), _user(2, "Bob", level=GUEST), _user(3, "Ghost", level=ANONYMOUS),
              _user(4, "Baddie", level=BANNED)]
    module, _ = make_module(bot, monkeypatch, users=users, buddies={1: 1})
    result = module.command_handler("Boss", "useradmin", "tell")
    assert result is False
    assert len(sent) == 1
    name, msg = sent[0][0], sent[0][1]
    assert name == "Boss"
    assert "Members: ##seablue##1/4##end##" in msg
    assert "Buddies: ##seablue##1/1##end##" in msg


def test_overview_warns_on_invalid_user_level(bot, monkeypatch):
    logged = []
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: None)
    monkeypatch.setattr(bot, "log", lambda *a, **kw: logged.append(a))
    users = [_user(1, "Weird", level=99)]
    module, _ = make_module(bot, monkeypatch, users=users)
    module.command_handler("Boss", "useradmin", "tell")
    assert any("Invalid user_level" in str(entry) for entry in logged)
