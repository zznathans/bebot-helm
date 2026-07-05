"""Integration tests proving the Alts<->Online circular cross-call interface
actually works end-to-end, with BOTH real modules registered on the same bot
(unlike test_module_alts.py/test_module_online.py, which fake out the other
side to test each module in isolation).

Cross-calls exercised here:
  * Alts.make_info_blob() -> bot.core("online").get_online_state(alt)
  * Alts.make_info_blob() -> bot.core("online").get_last_seen(alt)
  * Online.get_last_seen(checkalts=True) -> bot.core("alts").main(name)
  * Online.get_last_seen(checkalts=True) -> bot.core("alts").get_alts(main)
"""
from bebot.main_modules.alts import Alts
from bebot.main_modules.online import Online
from bebot.main_modules.tools import Tools
from fakes import FakePlayer, FakeSettings


class _FakeSettingsWithCreate(FakeSettings):
    def create(self, module, setting, value, longdesc, defaultoptions="", hidden=False, disporder=1):
        self._values.setdefault((module, setting), value)


class FakeChat:
    def __init__(self, online_buddies=None, offline_buddies=None):
        self.online_buddies = set(online_buddies or [])
        self.offline_buddies = set(offline_buddies or [])

    def buddy_exists(self, who):
        return who in self.online_buddies or who in self.offline_buddies

    def buddy_online(self, who):
        return who in self.online_buddies


class FakeNotify:
    def check(self, name):
        return True


def make_bot_with_both(bot, monkeypatch, alt_rows=None, users_rows=None, settings=None,
                        chat=None, player=None) -> tuple[Alts, Online]:
    Tools(bot)
    bot.register_module(settings or _FakeSettingsWithCreate(), "settings")
    bot.register_module(chat or FakeChat(), "chat")
    bot.register_module(FakeNotify(), "notify")
    bot.register_module(player or FakePlayer(), "player")

    def fake_select(sql, *a, **kw):
        if "#___alts" in sql:
            return alt_rows if alt_rows is not None else []
        if "#___users" in sql:
            return users_rows if users_rows is not None else []
        return []

    monkeypatch.setattr(bot.db, "select", fake_select)
    alts = Alts(bot)  # registers as bot.core("alts")
    online = Online(bot)  # registers as bot.core("online")
    return alts, online


def test_both_modules_register_and_can_see_each_other(bot, monkeypatch):
    alts, online = make_bot_with_both(bot, monkeypatch)
    assert bot.core("alts") is alts
    assert bot.core("online") is online


def test_alts_make_info_blob_calls_real_online_get_online_state(bot, monkeypatch):
    chat = FakeChat(online_buddies=["Altone"])
    alts, online = make_bot_with_both(
        bot, monkeypatch, alt_rows=[("Mainchar", "Altone")], chat=chat,
    )
    blob = alts.make_info_blob({"nickname": "Mainchar"}, "Mainchar", ["Altone"], 1)
    assert "##green##Online##end##" in blob


def test_alts_make_info_blob_shows_last_seen_from_real_online(bot, monkeypatch):
    chat = FakeChat(offline_buddies=["Altone"])
    settings = _FakeSettingsWithCreate()
    alts, online = make_bot_with_both(
        bot, monkeypatch,
        alt_rows=[("Mainchar", "Altone")],
        users_rows=[("Altone", 1000000000)],
        chat=chat,
        settings=settings,
    )
    settings.set("Alts", "LastSeen", True)
    blob = alts.make_info_blob({"nickname": "Mainchar"}, "Mainchar", ["Altone"], 1)
    assert "##red##Offline##end##" in blob
    assert "Last seen at" in blob


def test_online_get_last_seen_checkalts_calls_real_alts(bot, monkeypatch):
    alts, online = make_bot_with_both(
        bot, monkeypatch,
        alt_rows=[("Mainchar", "Altone"), ("Mainchar", "Alttwo")],
        users_rows=[("Mainchar", 100), ("Altone", 500), ("Alttwo", 50)],
    )
    # Querying via any alt should surface the most-recently-seen char across
    # the whole main+alts family, proven only by the real Alts cache.
    result = online.get_last_seen("Alttwo", checkalts=True)
    assert result == (500, "Altone")


def test_online_get_last_seen_checkalts_unregistered_char_is_its_own_main(bot, monkeypatch):
    alts, online = make_bot_with_both(
        bot, monkeypatch,
        alt_rows=[],
        users_rows=[("Loner", 42)],
    )
    result = online.get_last_seen("Loner", checkalts=True)
    assert result == (42, "Loner")


def test_full_round_trip_fancy_output_through_real_online(bot, monkeypatch):
    """End-to-end: Alts.fancy_output() (the public entry point real command
    modules would call) renders an alt whose online state and last-seen come
    from a real Online module, not a fake."""
    player = FakePlayer(ids={"Mainchar": 1})
    chat = FakeChat(online_buddies=["Altone"])
    alts, online = make_bot_with_both(
        bot, monkeypatch,
        alt_rows=[("Mainchar", "Altone")],
        chat=chat,
        player=player,
    )
    result = alts.fancy_output("Mainchar", 0)
    assert result["alts"] is True
    assert "Altone" in result["list"]
    assert "##green##Online##end##" in result["list"]
