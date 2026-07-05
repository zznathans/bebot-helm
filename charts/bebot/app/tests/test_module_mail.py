import base64

from bebot.main_modules.logon_notifies import LogonNotifies
from bebot.main_modules.mail import Mail
from bebot.main_modules.preferences import Preferences
from bebot.main_modules.settings import Settings
from bebot.main_modules.tools import Tools
from fakes import FakeAccessControl


class _FakeAccessControlWithCreate(FakeAccessControl):
    def create(self, channel, command, access):
        pass


class FakeAlts:
    def __init__(self, mains=None, alts=None):
        self.mains = dict(mains or {})
        self.alts_map = dict(alts or {})

    def main(self, name):
        return self.mains.get(name, name)

    def get_alts(self, main):
        return self.alts_map.get(main, [])


class FakeSecurity:
    def __init__(self, access=True):
        self.access = access

    def check_access(self, player, level):
        return self.access


class FakeChat:
    def __init__(self, existing=None, online=None):
        self.existing = set(existing or [])
        self.online = set(online or [])

    def buddy_exists(self, who):
        return who in self.existing

    def buddy_online(self, who):
        return who in self.online


def make_mail(bot, monkeypatch, alts=None, security=None, chat=None, select_rows=None) -> Mail:
    """Builds a Mail module wired to the real, already-ported
    Tools/Settings/Preferences/LogonNotifies core modules, with fake
    Alts/Security/Chat (this module's only other dependencies).

    `select_rows`, if given, is only installed as `bot.db.select`'s return
    value *after* all the dependency modules (and Mail itself) have
    finished construction -- their own "does this already exist?"
    existence-check queries need to see an empty result set, not whatever
    a given test wants Mail's own queries to see.
    """
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [])
    bot.register_module(_FakeAccessControlWithCreate(), "access_control")
    Tools(bot)
    Settings(bot)
    Preferences(bot)
    LogonNotifies(bot)
    bot.register_module(alts if alts is not None else FakeAlts(), "alts")
    bot.register_module(security if security is not None else FakeSecurity(), "security")
    bot.register_module(chat if chat is not None else FakeChat(), "chat")
    mail = Mail(bot)
    if select_rows is not None:
        monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: select_rows)
    return mail


def _encode(message: str) -> str:
    return base64.b64encode(message.encode("utf-8")).decode("ascii")


# -- construction ---------------------------------------------------------------

def test_creates_table_on_construction(bot, monkeypatch):
    make_mail(bot, monkeypatch)
    create_queries = [q for q in bot.db.queries if "CREATE TABLE" in q and "mail_message" in q]
    assert len(create_queries) == 1
    assert "received TIMESTAMP NOT NULL" in create_queries[0]


def test_registers_as_mail_module(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch)
    assert bot.core("mail") is mail


def test_registers_mail_and_mailed_commands(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch)
    for channel in ("tell", "gc", "pgmsg"):
        assert bot.commands[channel]["mail"] is mail
        assert bot.commands[channel]["mailed"] is mail


def test_registers_settings(bot, monkeypatch):
    make_mail(bot, monkeypatch)
    assert bot.core("settings").get("Mail", "Max_life_read") == "6_months"
    assert bot.core("settings").get("Mail", "Max_life_unread") == "1_year"


def test_registers_prefs_definitions(bot, monkeypatch):
    make_mail(bot, monkeypatch)
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___preferences_def")]
    assert any("Life_read" in q for q in insert_queries)
    assert any("Life_unread" in q for q in insert_queries)
    assert any("Logon_notification" in q for q in insert_queries)


def test_help_describes_commands(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch)
    assert "mail" in mail.help["command"]
    assert "mailed" in mail.help["command"]
    assert "mail send <name> <message>" in mail.help["command"]


# -- command_handler dispatch ----------------------------------------------------

def test_dispatch_mail_no_target_shows_mail_list(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch)
    monkeypatch.setattr(mail, "mail_list", lambda user: "the-list")
    result = mail.command_handler("Someone", "mail", "tell")
    assert "the-list" in result


def test_dispatch_mail_read_with_target(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch)
    captured = {}

    def fake_read(user, mid):
        captured["args"] = (user, mid)
        return "the-message"

    monkeypatch.setattr(mail, "mail_read", fake_read)
    result = mail.command_handler("Someone", "mail read 5", "tell")
    assert captured["args"] == ("Someone", 5)
    assert "the-message" in result


def test_dispatch_mail_read_nonnumeric_target_is_intval_zero(bot, monkeypatch):
    """Faithful port of a PHP quirk: is_int(intval($target)) is always true,
    so a non-numeric target silently becomes message id 0 rather than an
    error. See the module docstring."""
    mail = make_mail(bot, monkeypatch)
    captured = {}

    def fake_read(user, mid):
        captured["args"] = (user, mid)
        return "whatever"

    monkeypatch.setattr(mail, "mail_read", fake_read)
    mail.command_handler("Someone", "mail read abc", "tell")
    assert captured["args"] == ("Someone", 0)


def test_dispatch_mail_delete_with_target(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch)
    captured = {}

    def fake_delete(user, mid):
        captured["args"] = (user, mid)
        return "deleted"

    monkeypatch.setattr(mail, "mail_delete", fake_delete)
    result = mail.command_handler("Someone", "mail delete 7", "tell")
    assert captured["args"] == ("Someone", 7)
    assert result == "deleted"


def test_dispatch_mail_delete_no_target_falls_through_to_list(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch)
    monkeypatch.setattr(mail, "mail_list", lambda user: "the-list")
    result = mail.command_handler("Someone", "mail delete", "tell")
    assert "the-list" in result


def test_dispatch_mail_send(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch)
    captured = {}

    def fake_send(sender, recipient, message):
        captured["args"] = (sender, recipient, message)
        return "sent"

    monkeypatch.setattr(mail, "mail_send", fake_send)
    result = mail.command_handler("Someone", "mail send Bob hello there friend", "tell")
    assert captured["args"] == ("Someone", "Bob", "hello there friend")
    assert result == "sent"


def test_dispatch_mailed_shows_mail_sent(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch)
    monkeypatch.setattr(mail, "mail_sent", lambda user: "sent-list")
    result = mail.command_handler("Someone", "mailed", "tell")
    assert "sent-list" in result


def test_dispatch_unknown_subcommand_returns_error(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch)
    result = mail.command_handler("Someone", "mail bogus", "tell")
    assert "Unknown sub command" in result
    assert "bogus" in result


# -- gc/pgmsg re-declared to force tell (no leaking mail to public/group) -------

def test_gc_forces_tell(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch)
    calls = []
    monkeypatch.setattr(mail, "tell", lambda name, msg: calls.append((name, msg)))
    mail.gc("Someone", "mail")
    assert calls == [("Someone", "mail")]


def test_pgmsg_forces_tell(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch)
    calls = []
    monkeypatch.setattr(mail, "tell", lambda name, msg: calls.append((name, msg)))
    mail.pgmsg("Someone", "mail")
    assert calls == [("Someone", "mail")]


# -- notify() ---------------------------------------------------------------------

def test_notify_does_nothing_on_startup(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch)
    sent = []
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))
    mail.notify("Someone", startup=True)
    assert sent == []


def test_notify_does_nothing_when_pref_falsy(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch)
    bot.core("prefs").cache["def"] = {"mail": {"logon_notification": ""}}
    sent = []
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))
    mail.notify("Someone", startup=False)
    assert sent == []


def test_notify_sends_tell_when_new_mail(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch)
    bot.core("prefs").cache["def"] = {"mail": {"logon_notification": "Yes"}}
    monkeypatch.setattr(mail, "new_mail_count", lambda mailbox: 3)
    monkeypatch.setattr(mail, "mail_list", lambda user: "the-list")
    sent = []
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))
    mail.notify("Someone", startup=False)
    assert len(sent) == 1
    assert sent[0][0] == "Someone"
    assert "3" in sent[0][1]


def test_notify_no_send_when_no_new_mail(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch)
    bot.core("prefs").cache["def"] = {"mail": {"logon_notification": "Yes"}}
    monkeypatch.setattr(mail, "new_mail_count", lambda mailbox: 0)
    sent = []
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))
    mail.notify("Someone", startup=False)
    assert sent == []


# -- new_mail_count -----------------------------------------------------------

def test_new_mail_count_zero_when_no_rows(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch)
    assert mail.new_mail_count("Somebox") == 0


def test_new_mail_count_returns_count(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch, select_rows=[{"no_of_messages": 4}])
    assert mail.new_mail_count("Somebox") == 4


# -- mail_list / mail_sent / mail_read -------------------------------------------

def test_mail_list_no_mail(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch, select_rows=[])
    result = mail.mail_list("Someone")
    assert "No mail for you." in result


def test_mail_list_shows_unread_and_read_headers(bot, monkeypatch):
    rows = [
        {"id": 1, "received": "2024-01-01 10:00:00", "recipient": "Someone", "sender": "Bob",
         "message": _encode("hello"), "is_read": 0},
        {"id": 2, "received": "2024-01-02 10:00:00", "recipient": "Someone", "sender": "Bob",
         "message": _encode("read message"), "is_read": 1},
    ]
    mail = make_mail(bot, monkeypatch, select_rows=rows)
    result = mail.mail_list("Someone")
    assert "--- Unread messages ---" in result
    assert "--- Read messages ---" in result
    assert "hello" in result
    assert "read message" in result


def test_mail_list_truncates_long_messages(bot, monkeypatch):
    long_message = "x" * 30
    rows = [{"id": 1, "received": "2024-01-01 10:00:00", "recipient": "Someone", "sender": "Bob",
             "message": _encode(long_message), "is_read": 0}]
    mail = make_mail(bot, monkeypatch, select_rows=rows)
    result = mail.mail_list("Someone")
    assert "x" * 20 + "..." in result
    assert "x" * 30 not in result


def test_mail_sent_no_mail(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch, select_rows=[])
    result = mail.mail_sent("Someone")
    assert "No mail from you." in result


def test_mail_sent_shows_read_and_unread_markers(bot, monkeypatch):
    rows = [
        {"id": 1, "received": "2024-01-01 10:00:00", "recipient": "Bob", "sender": "Someone",
         "message": _encode("hi"), "is_read": 0},
        {"id": 2, "received": "2024-01-02 10:00:00", "recipient": "Alice", "sender": "Someone",
         "message": _encode("yo"), "is_read": 1},
    ]
    mail = make_mail(bot, monkeypatch, select_rows=rows)
    result = mail.mail_sent("Someone")
    assert "(Unread)" in result
    assert "(Read)" in result


def test_mail_read_not_found(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch, select_rows=[])
    result = mail.mail_read("Someone", 99)
    assert "Message 99 was not found." in result


def test_mail_read_marks_as_read(bot, monkeypatch):
    rows = [{"id": 5, "received": "2024-01-01 10:00:00", "recipient": "Someone", "sender": "Bob",
             "message": _encode("secret message"), "is_read": 0}]
    mail = make_mail(bot, monkeypatch, select_rows=rows)
    result = mail.mail_read("Someone", 5)
    assert "secret message" in result
    update_queries = [q for q in bot.db.queries if q.startswith("UPDATE #___mail_message SET is_read=true")]
    assert len(update_queries) == 1
    assert "id=5" in update_queries[0]


# -- mail_send ---------------------------------------------------------------

def test_mail_send_rejects_unknown_recipient(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch, security=FakeSecurity(access=False))
    result = mail.mail_send("Someone", "Nobody", "hi there")
    assert "is not a known member" in result


def test_mail_send_rejects_empty_message(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch)
    result = mail.mail_send("Someone", "Bob", "")
    assert "empty messages" in result


def test_mail_send_inserts_and_returns_confirmation(bot, monkeypatch):
    alts = FakeAlts(mains={"Bob": "Bob"})
    mail = make_mail(bot, monkeypatch, alts=alts)
    result = mail.mail_send("Someone", "Bob", "hello friend")
    assert result == "Message sent to Bob (Bob)."
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___mail_message")]
    assert len(insert_queries) == 1
    assert "'Bob'" in insert_queries[0]
    assert "'Someone'" in insert_queries[0]


def test_mail_send_notifies_online_recipients(bot, monkeypatch):
    alts = FakeAlts(mains={"Bob": "Bob"}, alts={"Bob": ["Bobalt"]})
    chat = FakeChat(existing={"Bob", "Bobalt"}, online={"Bobalt"})
    mail = make_mail(bot, monkeypatch, alts=alts, chat=chat)
    sent = []
    monkeypatch.setattr(bot, "send_tell", lambda *a, **kw: sent.append(a))
    mail.mail_send("Someone", "Bob", "hello friend")
    assert len(sent) == 1
    assert sent[0][0] == "Bobalt"


def test_mail_send_escapes_html_lt_in_message(bot, monkeypatch):
    alts = FakeAlts(mains={"Bob": "Bob"})
    mail = make_mail(bot, monkeypatch, alts=alts)
    mail.mail_send("Someone", "Bob", "1 < 2")
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___mail_message")]
    # Message body is base64-encoded after the "<" -> "&lt;" substitution,
    # so the raw literal shouldn't appear, but decoding it should show the
    # escaped form.
    assert "1 < 2" not in insert_queries[0]


# -- mail_delete ---------------------------------------------------------------

def test_mail_delete_success(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch, select_rows=[[5]])
    result = mail.mail_delete("Someone", 5)
    assert result == "Mail 5 has been deleted."
    delete_queries = [q for q in bot.db.queries if q.startswith("DELETE FROM #___mail_message")]
    assert len(delete_queries) == 1


def test_mail_delete_not_found(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch, select_rows=[])
    result = mail.mail_delete("Someone", 99)
    assert "was either not found or did not belong to Someone" in result
    delete_queries = [q for q in bot.db.queries if q.startswith("DELETE FROM #___mail_message")]
    assert len(delete_queries) == 0


# -- make_item_blob -----------------------------------------------------------

def test_make_item_blob_replaces_botname_and_pre(bot, monkeypatch):
    mail = make_mail(bot, monkeypatch)
    result = mail.make_item_blob("Title", "hi <botname>, try <pre>mail")
    assert bot.botname in result
    assert "<botname>" not in result
    assert "<pre>" not in result
    assert result.startswith('<a href="text://')
    assert result.endswith("Title</a>")
