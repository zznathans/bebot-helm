"""Tests for main_modules/is_module.py (ported from Modules/Is.php, class `Is`)."""
from __future__ import annotations

from bebot.commodities.base import BotError
from bebot.main_modules.is_module import IsModule
from bebot.main_modules.settings import Settings
from bebot.main_modules.tools import Tools


class FakePlayer:
    def __init__(self, ids: dict[str, int] | None = None):
        self._ids = dict(ids or {})

    def id(self, name):
        if name in self._ids:
            return self._ids[name]
        return BotError(None, "player")


class FakeAlts:
    def __init__(self, mains=None, alts=None):
        self._mains = dict(mains or {})
        self._alts = dict(alts or {})

    def main(self, char):
        return self._mains.get(char, char)

    def get_alts(self, main):
        return list(self._alts.get(main, []))


class FakeChat:
    def __init__(self, existing_online=None, existing_offline=None):
        self.online = set(existing_online or [])
        self.known = set(existing_online or []) | set(existing_offline or [])
        self.added: list[str] = []
        self.removed: list[str] = []

    def buddy_exists(self, who):
        return who in self.known

    def buddy_online(self, who):
        return who in self.online

    def buddy_add(self, who):
        self.added.append(who)
        self.known.add(who)

    def buddy_remove(self, who):
        self.removed.append(who)
        self.known.discard(who)
        self.online.discard(who)


class FakeOnline:
    def __init__(self, last_seen=None):
        self._last_seen = last_seen

    def get_last_seen(self, name, checkalts=False):
        return self._last_seen


def make_module(
    bot,
    ids=None,
    mains=None,
    alts=None,
    online_names=None,
    offline_known=None,
    checkalts=True,
    buddy_slots=20,
    timeout=15,
    last_seen=False,
) -> IsModule:
    Settings(bot)
    Tools(bot)
    bot.register_module(FakePlayer(ids or {}), "player")
    bot.register_module(FakeAlts(mains, alts), "alts")
    bot.register_module(FakeChat(online_names, offline_known), "chat")
    bot.register_module(FakeOnline(last_seen), "online")

    module = IsModule(bot)
    settings = bot.core("settings")
    settings.save("Is", "CheckAlts", checkalts)
    settings.save("Is", "Buddy_slots", buddy_slots)
    settings.save("Is", "Timeout", timeout)
    return module


# -- construction -----------------------------------------------------------------

def test_registers_as_is_module(bot):
    module = make_module(bot)
    assert bot.core("is") is module


def test_creates_settings(bot):
    make_module(bot)
    settings = bot.core("settings")
    for name in ("Errormsg", "Buddy_slots", "Timeout", "CheckAlts"):
        assert settings.exists("Is", name)


def test_registers_buddy_and_cron_events(bot):
    module = make_module(bot)
    assert type(module).__name__ in bot.commands.get("buddy", {})
    assert type(module).__name__ in bot._cron_jobs.get(3, {})


# -- command_handler ----------------------------------------------------------------

def test_queue_busy_short_circuits(bot):
    module = make_module(bot, ids={"Target": 1})
    module.is_queue["Asker"] = {"chn": "tell", "trg": "Target", "tmo": 0}
    result = module.command_handler("Asker", "is Target", "tell")
    assert result == "Please wait until your previous lookup is completed"


def test_invalid_player_name_returns_error(bot):
    module = make_module(bot, ids={})
    result = module.command_handler("Asker", "is Nobody", "tell")
    assert isinstance(result, BotError)
    assert "no valid character name" in result.message()
    assert "Asker" not in module.is_queue


def test_asking_about_self_bot_name(bot, monkeypatch):
    module = make_module(bot, ids={"Testbot": 1})
    result = module.command_handler("Asker", "is Testbot", "tell")
    assert result == "I'm online!"
    assert "Asker" not in module.is_queue


def test_asking_about_self_via_alt(bot):
    module = make_module(
        bot,
        ids={"Target": 1},
        mains={"Target": "Asker"},
        alts={"Asker": ["Target"]},
        checkalts=True,
    )
    result = module.command_handler("Asker", "is Target", "tell")
    assert result == "Why are you asking me if you are online?!"
    assert "Asker" not in module.is_queue


def test_checkalts_off_only_checks_single_player(bot):
    module = make_module(bot, ids={"Target": 1}, checkalts=False, online_names=["Target"])
    module.command_handler("Asker", "is Target", "tell")
    # Immediate resolution since Target is already a known buddy.
    assert "Asker" not in module.is_queue


def test_immediate_resolution_when_all_alts_known_online(bot, monkeypatch):
    sent = []
    monkeypatch.setattr(bot, "send_output", lambda *a, **kw: sent.append(a))
    module = make_module(
        bot,
        ids={"Target": 1},
        mains={"Target": "Target"},
        alts={"Target": []},
        online_names=["Target"],
        checkalts=True,
    )
    module.command_handler("Asker", "is Target", "tell")
    assert "Asker" not in module.is_queue
    assert len(sent) == 1
    assert "Online" in sent[0][1]


def test_immediate_resolution_when_all_alts_known_offline(bot, monkeypatch):
    sent = []
    monkeypatch.setattr(bot, "send_output", lambda *a, **kw: sent.append(a))
    module = make_module(
        bot,
        ids={"Target": 1},
        mains={"Target": "Target"},
        alts={"Target": []},
        offline_known=["Target"],
        checkalts=True,
    )
    module.command_handler("Asker", "is Target", "tell")
    assert "Offline" in sent[0][1]


def test_queues_when_alt_not_on_buddy_list_and_slots_available(bot):
    module = make_module(
        bot,
        ids={"Target": 1},
        mains={"Target": "Target"},
        alts={"Target": []},
        buddy_slots=20,
    )
    module.command_handler("Asker", "is Target", "tell")
    assert module.is_queue["Asker"]["Target"] == "Queued"
    assert module.queue_counter == 1
    assert "Target" in bot.core("chat").added


def test_waits_when_no_slots_available(bot):
    module = make_module(
        bot,
        ids={"Target": 1},
        mains={"Target": "Target"},
        alts={"Target": []},
        buddy_slots=0,
    )
    module.command_handler("Asker", "is Target", "tell")
    assert module.is_queue["Asker"]["Target"] == "Waiting"
    assert module.queue_counter == 0


# -- buddy() ------------------------------------------------------------------------

def test_buddy_resolves_online_and_sends_when_complete(bot, monkeypatch):
    sent = []
    monkeypatch.setattr(bot, "send_output", lambda *a, **kw: sent.append(a))
    module = make_module(bot)
    module.is_queue["Asker"] = {"chn": "tell", "trg": "Target", "tmo": 999999999999, "Target": "Queued"}
    module.queue_counter = 1
    module.buddy("Target", 1)
    assert "Asker" not in module.is_queue
    assert len(sent) == 1
    assert "Online" in sent[0][1]
    assert module.queue_counter == 0


def test_buddy_does_not_send_until_all_alts_resolved(bot, monkeypatch):
    sent = []
    monkeypatch.setattr(bot, "send_output", lambda *a, **kw: sent.append(a))
    module = make_module(bot)
    module.is_queue["Asker"] = {
        "chn": "tell", "trg": "Target", "tmo": 999999999999,
        "Target": "Queued", "Alt2": "Queued",
    }
    module.queue_counter = 2
    module.buddy("Target", 1)
    assert "Asker" in module.is_queue
    assert sent == []
    module.buddy("Alt2", 0)
    assert "Asker" not in module.is_queue
    assert len(sent) == 1


def test_buddy_ignores_non_login_logoff_messages(bot):
    module = make_module(bot)
    module.is_queue["Asker"] = {"chn": "tell", "trg": "Target", "tmo": 999999999999, "Target": "Queued"}
    module.buddy("Target", 5)
    assert module.is_queue["Asker"]["Target"] == "Queued"


# -- cron() -------------------------------------------------------------------------

def test_cron_promotes_waiting_to_queued_when_slots_free(bot):
    module = make_module(bot, buddy_slots=20)
    module.is_queue["Asker"] = {
        "chn": "tell", "trg": "Target", "tmo": __import__("time").time() + 100,
        "Target": "Waiting",
    }
    module.cron()
    assert module.is_queue["Asker"]["Target"] == "Queued"
    assert module.queue_counter == 1
    assert "Target" in bot.core("chat").added


def test_cron_times_out_and_sends(bot, monkeypatch):
    sent = []
    monkeypatch.setattr(bot, "send_output", lambda *a, **kw: sent.append(a))
    module = make_module(bot)
    bot.core("chat").known.add("Target")  # on buddy list
    module.is_queue["Asker"] = {
        "chn": "tell", "trg": "Target", "tmo": 1,  # already expired
        "Target": "Queued",
    }
    module.queue_counter = 1
    module.cron()
    assert "Asker" not in module.is_queue
    assert "Target" in bot.core("chat").removed
    assert module.queue_counter == 0
    assert "timed out" in sent[0][1]


def test_cron_noop_when_queue_empty(bot):
    module = make_module(bot)
    module.cron()  # should not raise


# -- last_seen() --------------------------------------------------------------------

def test_last_seen_checkalts_true_renders_tuple(bot):
    module = make_module(bot, checkalts=True, last_seen=(1700000000, "Target"))
    result = module.last_seen("Target")
    assert "last seen at" in result
    assert "Target" in result


def test_last_seen_checkalts_false_renders_timestamp(bot):
    module = make_module(bot, checkalts=False, last_seen=1700000000)
    result = module.last_seen("Target")
    assert "last seen at" in result


def test_last_seen_falsy_returns_empty_string(bot):
    module = make_module(bot, last_seen=False)
    assert module.last_seen("Target") == ""
