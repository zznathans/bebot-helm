import re

from bebot.commodities.base import BotError
from bebot.main_modules.player_notes import PlayerNotes
from bebot.main_modules.player_notes_ui import PlayerNotesUi
from bebot.main_modules.tools import Tools
from fakes import FakePlayer, FakeSecurity


class _FakeAccessControl:
    """register_command() with subcommands needs create() *and*
    create_subcommand() -- FakeAccessControl from fakes.py only implements
    check_rights()/get_min_rights()."""

    def create(self, channel, command, access):
        pass

    def create_subcommand(self, channel, command, subcommand, access):
        pass


class FakeNotesDb:
    """A tiny in-memory stand-in for bot.db that actually understands the
    handful of SQL shapes core("player_notes")'s real PlayerNotes module
    issues (INSERT/SELECT pnid/SELECT */DELETE against #___player_notes),
    so PlayerNotesUi can be tested wired to the *real* already-ported
    PlayerNotes module (integration-style, per the task brief) instead of a
    fake core("player_notes").
    """

    _INSERT_RE = re.compile(
        r"INSERT INTO #___player_notes \(player, author, note, class, timestamp\) "
        r"VALUES \('([^']*)', '([^']*)', '([^']*)', (\d+), (\d+)\)"
    )

    def __init__(self):
        self.rows: list[dict] = []
        self.queries: list[str] = []
        self._next_pnid = 1

    def query(self, sql: str) -> bool:
        self.queries.append(sql)
        match = self._INSERT_RE.search(sql)
        if match:
            player, author, note, class_value, timestamp = match.groups()
            self.rows.append(
                {
                    "pnid": self._next_pnid,
                    "player": player,
                    "author": author,
                    "note": note,
                    "class": int(class_value),
                    "timestamp": int(timestamp),
                }
            )
            self._next_pnid += 1
        return True

    def select(self, sql: str, as_dict: bool = False):
        if "SELECT pnid FROM #___player_notes WHERE player" in sql:
            m = re.search(r"player = '([^']*)'", sql)
            matches = [r for r in self.rows if r["player"] == m.group(1)]
            if not matches:
                return []
            return [(max(matches, key=lambda r: r["pnid"])["pnid"],)]
        if sql.startswith("SELECT * FROM #___player_notes"):
            filtered = list(self.rows)
            m_player = re.search(r"player = '([^']*)'", sql)
            if m_player:
                filtered = [r for r in filtered if r["player"] == m_player.group(1)]
            if re.search(r"class = 0\b", sql):
                filtered = [r for r in filtered if r["class"] == 0]
            m_pnid = re.search(r"pnid = (\d+)", sql)
            if m_pnid:
                filtered = [r for r in filtered if r["pnid"] == int(m_pnid.group(1))]
            filtered.sort(key=lambda r: r["pnid"], reverse="DESC" in sql)
            return [
                (r["pnid"], r["player"], r["author"], r["note"], r["class"], r["timestamp"])
                for r in filtered
            ]
        return []

    def return_query(self, sql: str) -> bool:
        self.queries.append(sql)
        m = re.search(r"pnid = (\d+)", sql)
        if not m:
            return False
        pnid = int(m.group(1))
        before = len(self.rows)
        self.rows = [r for r in self.rows if r["pnid"] != pnid]
        return len(self.rows) < before

    def real_escape_string(self, value) -> str:
        return str(value).replace("'", "\\'")

    def define_tablename(self, table: str, use_prefix) -> str:
        return table


def make_module(bot, monkeypatch, *, security_access=True, player_ids=None):
    """Builds a PlayerNotesUi wired to the real, already-ported PlayerNotes
    core module (plus real Tools), with bot.db swapped for FakeNotesDb so
    add/get_notes/delete actually round-trip through in-memory storage."""
    fakedb = FakeNotesDb()
    monkeypatch.setattr(bot.db, "query", fakedb.query)
    monkeypatch.setattr(bot.db, "select", fakedb.select)
    monkeypatch.setattr(bot.db, "return_query", fakedb.return_query)
    bot.register_module(_FakeAccessControl(), "access_control")
    Tools(bot)
    bot.register_module(FakeSecurity(access=security_access), "security")
    bot.register_module(FakePlayer(ids=player_ids or {}), "player")
    PlayerNotes(bot)
    ui = PlayerNotesUi(bot)
    return ui, fakedb


# -- construction / registration ------------------------------------------------

def test_registers_as_player_notes_ui_module(bot, monkeypatch):
    ui, _ = make_module(bot, monkeypatch)
    assert bot.core("player_notes_ui") is ui


def test_registers_notes_command_on_all_channels(bot, monkeypatch):
    ui, _ = make_module(bot, monkeypatch)
    assert bot.commands["tell"]["notes"] is ui
    assert bot.commands["gc"]["notes"] is ui
    assert bot.commands["pgmsg"]["notes"] is ui


def test_registers_note_alias(bot, monkeypatch):
    make_module(bot, monkeypatch)
    assert bot.core("command_alias").exists("note")


def test_help_describes_commands(bot, monkeypatch):
    ui, _ = make_module(bot, monkeypatch)
    assert "notes" in ui.help["command"]
    assert "notes add <player> <note>" in ui.help["command"]


# -- add_note -------------------------------------------------------------------

def test_add_note_default_class(bot, monkeypatch):
    ui, fakedb = make_module(bot, monkeypatch)
    result = ui.add_note("Somechar", "Targetchar Was rude in gc")
    assert 'Successfully added "Was rude in gc" note to Targetchar as note id 1' == result
    assert fakedb.rows[0]["class"] == 0


def test_add_note_no_reason_text(bot, monkeypatch):
    ui, fakedb = make_module(bot, monkeypatch)
    result = ui.add_note("Somechar", "Targetchar")
    assert "Successfully added" in result
    assert fakedb.rows[0]["note"] == ""


def test_add_note_admin_allowed(bot, monkeypatch):
    ui, fakedb = make_module(bot, monkeypatch, security_access=True)
    result = ui.add_note("Adminchar", "Targetchar Banned for botting", admin=True)
    assert "Successfully added" in result
    assert fakedb.rows[0]["class"] == 2


def test_add_note_admin_denied_without_access(bot, monkeypatch):
    ui, fakedb = make_module(bot, monkeypatch, security_access=False)
    result = ui.add_note("Membairchar", "Targetchar Banned for botting", admin=True)
    assert isinstance(result, BotError)
    assert "ADMIN or higher" in result.get()
    assert fakedb.rows == []


# -- rem_note ---------------------------------------------------------------------

def test_rem_note_existing_id_deletes(bot, monkeypatch):
    ui, fakedb = make_module(bot, monkeypatch)
    ui.add_note("Somechar", "Targetchar A note")
    pnid = fakedb.rows[0]["pnid"]
    result = ui.rem_note(str(pnid))
    assert result == f"Deleted player note {pnid}"
    assert fakedb.rows == []


def test_rem_note_nonexistent_id_returns_error(bot, monkeypatch):
    ui, _ = make_module(bot, monkeypatch)
    result = ui.rem_note("999")
    assert isinstance(result, BotError)
    assert "Could not delete player note 999" in result.get()


# -- show_notes -------------------------------------------------------------------

def test_show_notes_unknown_player_returns_error(bot, monkeypatch):
    ui, _ = make_module(bot, monkeypatch, player_ids={})
    result = ui.show_notes("Somechar", "Nosuchguy")
    assert isinstance(result, BotError)
    assert "is not a valid character" in result.get()


def test_show_notes_no_notes_found(bot, monkeypatch):
    ui, _ = make_module(bot, monkeypatch, player_ids={"Targetchar": 1234})
    result = ui.show_notes("Somechar", "Targetchar")
    assert isinstance(result, BotError)
    assert "No notes found" in result.get()


def test_show_notes_lists_notes_for_player(bot, monkeypatch):
    ui, _ = make_module(bot, monkeypatch, player_ids={"Targetchar": 1234})
    ui.add_note("Somechar", "Targetchar First note")
    ui.add_note("Somechar", "Targetchar Second note")
    result = ui.show_notes("Somechar", "Targetchar")
    assert "Notes for Targetchar" in result
    assert "First note" in result
    assert "Second note" in result
    assert "Note #1" in result
    assert "Note #2" in result


def test_show_notes_labels_admin_and_ban_classes(bot, monkeypatch):
    ui, _ = make_module(bot, monkeypatch, player_ids={"Targetchar": 1234}, security_access=True)
    ui.add_note("Adminchar", "Targetchar Botting", admin=True)
    result = ui.show_notes("Adminchar", "Targetchar")
    assert "Admin Note #1" in result


def test_show_notes_hides_admin_notes_from_non_leaders(bot, monkeypatch):
    ui, _ = make_module(
        bot, monkeypatch, player_ids={"Targetchar": 1234}, security_access=True
    )
    ui.add_note("Adminchar", "Targetchar Botting", admin=True)
    # Flip the (mutable) fake security's access check to non-leader for the
    # viewing call -- bot.register_module() refuses to replace an already
    # registered module, so mutate the existing fake in place instead.
    bot.core("security").access = False
    result = ui.show_notes("Membairchar", "Targetchar")
    assert isinstance(result, BotError)
    assert "No notes found" in result.get()


# -- show_all_notes ---------------------------------------------------------------

def test_show_all_notes_no_notes(bot, monkeypatch):
    ui, _ = make_module(bot, monkeypatch)
    result = ui.show_all_notes("Somechar", "tell")
    assert result == ""


def test_show_all_notes_summarizes_counts_per_player(bot, monkeypatch):
    ui, _ = make_module(bot, monkeypatch, security_access=True)
    ui.add_note("Somechar", "Targetchar First note")
    ui.add_note("Somechar", "Targetchar Second note")
    ui.add_note("Adminchar", "Otherchar Banned", admin=True)
    result = ui.show_all_notes("Somechar", "tell")
    assert "All Players with Notes" in result
    assert "notes Targetchar" in result
    assert "notes Otherchar" in result
    assert "2 Normal Notes" in result
    assert "1 Admin Notes" in result


# -- command_handler dispatch ----------------------------------------------------

def test_command_handler_no_args_shows_overview(bot, monkeypatch):
    ui, _ = make_module(bot, monkeypatch)
    ui.add_note("Somechar", "Targetchar A note")
    result = ui.command_handler("Somechar", "notes", "tell")
    assert "All Players with Notes" in result


def test_command_handler_add_dispatches(bot, monkeypatch):
    ui, _ = make_module(bot, monkeypatch)
    result = ui.command_handler("Somechar", "notes add Targetchar Was rude", "tell")
    assert "Successfully added" in result


def test_command_handler_admin_dispatches(bot, monkeypatch):
    ui, _ = make_module(bot, monkeypatch, security_access=True)
    result = ui.command_handler("Adminchar", "notes admin Targetchar Botting", "tell")
    assert "Successfully added" in result


def test_command_handler_admin_denied(bot, monkeypatch):
    ui, _ = make_module(bot, monkeypatch, security_access=False)
    result = ui.command_handler("Membairchar", "notes admin Targetchar Botting", "tell")
    assert isinstance(result, BotError)
    assert "ADMIN or higher" in result.get()


def test_command_handler_rem_dispatches(bot, monkeypatch):
    ui, fakedb = make_module(bot, monkeypatch)
    ui.add_note("Somechar", "Targetchar A note")
    pnid = fakedb.rows[0]["pnid"]
    result = ui.command_handler("Somechar", f"notes rem {pnid}", "tell")
    assert result == f"Deleted player note {pnid}"


def test_command_handler_del_synonym_dispatches(bot, monkeypatch):
    ui, fakedb = make_module(bot, monkeypatch)
    ui.add_note("Somechar", "Targetchar A note")
    pnid = fakedb.rows[0]["pnid"]
    result = ui.command_handler("Somechar", f"notes del {pnid}", "tell")
    assert result == f"Deleted player note {pnid}"


def test_command_handler_player_name_shows_notes(bot, monkeypatch):
    ui, _ = make_module(bot, monkeypatch, player_ids={"Targetchar": 1234})
    ui.add_note("Somechar", "Targetchar A note")
    result = ui.command_handler("Somechar", "notes Targetchar", "tell")
    assert "Notes for Targetchar" in result


def test_command_handler_subcommand_matching_is_case_sensitive(bot, monkeypatch):
    """Faithful port of the PHP: unlike alias.py, the switch on the
    subcommand token is never lowercased first, so "notes ADD ..." falls
    through to the per-player lookup treating "ADD" as a player name."""
    ui, _ = make_module(bot, monkeypatch, player_ids={})
    result = ui.command_handler("Somechar", "notes ADD Targetchar Was rude", "tell")
    assert isinstance(result, BotError)
    assert "'ADD' is not a valid character" in result.get()
