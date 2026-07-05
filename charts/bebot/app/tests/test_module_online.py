from bebot.commodities.base import BotError
from bebot.main_modules.online import Online
from fakes import FakePlayer, FakeSettings


class _FakeSettingsWithCreate(FakeSettings):
    """FakeSettings doesn't implement create() -- Online.__init__ calls it to
    register Online/Reinvite settings."""

    def create(self, module, setting, value, longdesc, defaultoptions="", hidden=False, disporder=1):
        self._values.setdefault((module, setting), value)


class FakeChat:
    """Local stand-in for aochat_wrapper.py used when testing Online in isolation."""

    def __init__(self, online_buddies=None, offline_buddies=None):
        self.online_buddies = set(online_buddies or [])
        self.offline_buddies = set(offline_buddies or [])
        self.invited: list[str] = []

    def buddy_exists(self, who):
        return who in self.online_buddies or who in self.offline_buddies

    def buddy_online(self, who):
        return who in self.online_buddies

    def pgroup_invite(self, user):
        self.invited.append(user)


class FakeNotify:
    def __init__(self, allow=True):
        self.allow = allow
        self.checked: list[str] = []

    def check(self, name):
        self.checked.append(name)
        return self.allow


class FakeAlts:
    """Local stand-in for alts.py used when testing Online in isolation."""

    def __init__(self, mains=None, alts=None):
        self.mains = mains or {}
        self.alts = alts or {}

    def main(self, char):
        return self.mains.get(char, char)

    def get_alts(self, char):
        return self.alts.get(char, [])


def make_online(bot, monkeypatch, users_rows=None, settings=None, chat=None, notify=None, alts=None,
                 player=None, guildbot=True) -> Online:
    bot.guildbot = guildbot
    bot.register_module(settings or _FakeSettingsWithCreate(), "settings")
    bot.register_module(chat or FakeChat(), "chat")
    bot.register_module(notify or FakeNotify(), "notify")
    bot.register_module(alts or FakeAlts(), "alts")
    bot.register_module(player or FakePlayer(), "player")
    rows = users_rows if users_rows is not None else []
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: rows)
    return Online(bot)


# -- construction --------------------------------------------------------------

def test_creates_table_on_construction(bot, monkeypatch):
    make_online(bot, monkeypatch)
    create_queries = [q for q in bot.db.queries if "CREATE TABLE" in q]
    assert len(create_queries) == 1
    assert "online" in create_queries[0]
    assert "reinvite" in create_queries[0]
    assert "level" in create_queries[0]


def test_registers_as_online_module(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    assert bot.core("online") is module


def test_creates_settings_guildbot_defaults_channel_both(bot, monkeypatch):
    settings = _FakeSettingsWithCreate()
    make_online(bot, monkeypatch, settings=settings, guildbot=True)
    assert settings.get("Online", "Channel") == "both"
    assert settings.get("Reinvite", "Enabled") is True
    assert settings.get("Reinvite", "Silent") is True


def test_creates_settings_non_guildbot_defaults_channel_pgroup(bot, monkeypatch):
    settings = _FakeSettingsWithCreate()
    make_online(bot, monkeypatch, settings=settings, guildbot=False)
    assert settings.get("Online", "Channel") == "pgroup"


def test_seeds_last_seen_cache_from_users_table(bot, monkeypatch):
    rows = [("someplayer", 12345), ("otherplayer", 67890)]
    module = make_online(bot, monkeypatch, users_rows=rows)
    assert module.get_last_seen("Someplayer") == 12345
    assert module.get_last_seen("Otherplayer") == 67890


# -- pgjoin / pgleave / in_chat -------------------------------------------------

def test_pgjoin_marks_in_chat_and_sets_reinvite(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    module.pgjoin("Someplayer")
    assert module.in_chat("someplayer") is True
    assert any("reinvite = '1'" in q and "Someplayer" in q for q in bot.db.queries)


def test_pgleave_clears_in_chat_and_unsets_reinvite(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    module.pgjoin("Someplayer")
    module.pgleave("Someplayer")
    assert module.in_chat("Someplayer") is False
    assert any("reinvite = '0'" in q and "Someplayer" in q for q in bot.db.queries)


def test_privgroup_joins_if_not_already_in_chat(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    module.privgroup("Newguy", "hello")
    assert module.in_chat("Newguy") is True


def test_privgroup_does_not_rejoin_if_already_in_chat(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    module.pgjoin("Existing")
    query_count_before = len(bot.db.queries)
    module.privgroup("Existing", "hello again")
    # No additional status_change/reinvite queries should be issued.
    assert len(bot.db.queries) == query_count_before


# -- buddy / in_org / gmsg -------------------------------------------------------

def test_buddy_logon_marks_gc_online(bot, monkeypatch):
    notify = FakeNotify(allow=True)
    module = make_online(bot, monkeypatch, notify=notify)
    module.buddy("Guildie", 1)
    assert module.in_org("Guildie") is True
    assert "Guildie" in notify.checked


def test_buddy_logoff_marks_gc_offline(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    module.buddy("Guildie", 1)
    module.buddy("Guildie", 0)
    assert module.in_org("Guildie") is False


def test_buddy_ignored_when_notify_check_fails(bot, monkeypatch):
    notify = FakeNotify(allow=False)
    module = make_online(bot, monkeypatch, notify=notify)
    module.buddy("Guildie", 1)
    assert module.in_org("Guildie") is False


def test_buddy_ignores_other_bots(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    bot.other_bots["Otherbot"] = True
    module.buddy("Otherbot", 1)
    assert module.in_org("Otherbot") is False


def test_buddy_ignores_non_logon_logoff_messages(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    module.buddy("Someone", 2)
    assert module.in_org("Someone") is False


def test_gmsg_treats_as_buddy_logon_if_not_in_org(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    module.gmsg("Guildie", "somegroup", "hi")
    assert module.in_org("Guildie") is True


def test_gmsg_no_op_if_already_in_org(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    module.buddy("Guildie", 1)
    query_count_before = len(bot.db.queries)
    module.gmsg("Guildie", "somegroup", "hi again")
    assert len(bot.db.queries) == query_count_before


# -- connect / disconnect --------------------------------------------------------

def test_connect_sets_everyone_offline(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    module.connect()
    assert any("status_gc = '0', status_pg = '0'" in q for q in bot.db.queries)


def test_connect_reinvites_pending_users(bot, monkeypatch):
    chat = FakeChat()
    settings = _FakeSettingsWithCreate()
    module = make_online(bot, monkeypatch, chat=chat, settings=settings)
    monkeypatch.setattr(
        bot.db, "select",
        lambda sql, *a, **kw: [("Pendinguser",)] if "reinvite" in sql else [],
    )
    settings.set("Reinvite", "Enabled", True)
    settings.set("Reinvite", "Silent", True)
    module.connect()
    assert "Pendinguser" in chat.invited


def test_connect_skips_reinvite_when_disabled(bot, monkeypatch):
    chat = FakeChat()
    settings = _FakeSettingsWithCreate()
    module = make_online(bot, monkeypatch, chat=chat, settings=settings)
    monkeypatch.setattr(
        bot.db, "select",
        lambda sql, *a, **kw: [("Pendinguser",)] if "reinvite" in sql else [],
    )
    settings.set("Reinvite", "Enabled", False)
    module.connect()
    assert chat.invited == []


def test_disconnect_sets_everyone_offline(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    module.disconnect()
    assert any("status_gc = '0', status_pg = '0'" in q for q in bot.db.queries)


# -- status_change / logoff -------------------------------------------------------

def test_status_change_invalid_where_returns_false(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    assert module.status_change("Someone", "bogus", 1) is False


def test_status_change_updates_last_seen_cache(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    module.status_change("Someone", "gc", 1)
    assert module.get_last_seen("Someone") is not False


def test_logoff_clears_gc_status(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    module.logoff("Someone")
    assert any("status_gc = '0'" in q and "Someone" in q for q in bot.db.queries)


# -- get_online_state: cross-call into chat --------------------------------------

def test_get_online_state_unknown_buddy(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    result = module.get_online_state("Nobody")
    assert result == {"content": "##white##Unknown##end##", "status": -1}


def test_get_online_state_online_buddy(bot, monkeypatch):
    chat = FakeChat(online_buddies=["Someone"])
    module = make_online(bot, monkeypatch, chat=chat)
    result = module.get_online_state("Someone")
    assert result == {"content": "##green##Online##end##", "status": 1}


def test_get_online_state_offline_buddy(bot, monkeypatch):
    chat = FakeChat(offline_buddies=["Someone"])
    module = make_online(bot, monkeypatch, chat=chat)
    result = module.get_online_state("Someone")
    assert result == {"content": "##red##Offline##end##", "status": 0}


# -- get_last_seen: cross-call into alts ------------------------------------------

def test_get_last_seen_no_data_returns_false(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    assert module.get_last_seen("Nobody") is False


def test_get_last_seen_checkalts_uses_main_when_more_recent(bot, monkeypatch):
    rows = [("Mainchar", 500), ("Altone", 100)]
    alts = FakeAlts(mains={"Altone": "Mainchar"}, alts={"Mainchar": ["Altone"]})
    module = make_online(bot, monkeypatch, users_rows=rows, alts=alts)
    result = module.get_last_seen("Altone", checkalts=True)
    assert result == (500, "Mainchar")


def test_get_last_seen_checkalts_uses_alt_when_more_recent(bot, monkeypatch):
    rows = [("Mainchar", 100), ("Altone", 500)]
    alts = FakeAlts(mains={"Altone": "Mainchar"}, alts={"Mainchar": ["Altone"]})
    module = make_online(bot, monkeypatch, users_rows=rows, alts=alts)
    result = module.get_last_seen("Altone", checkalts=True)
    assert result == (500, "Altone")


def test_get_last_seen_checkalts_no_data_anywhere_returns_false(bot, monkeypatch):
    alts = FakeAlts(mains={"Altone": "Mainchar"}, alts={"Mainchar": ["Altone"]})
    module = make_online(bot, monkeypatch, alts=alts)
    result = module.get_last_seen("Altone", checkalts=True)
    assert result is False


# -- otherbots / channels / list_users --------------------------------------------

def test_otherbots_defaults_to_own_botname(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    assert module.otherbots("t1.") == f"t1.botname = '{bot.botname}'"


def test_otherbots_includes_valid_other_bots(bot, monkeypatch):
    settings = _FakeSettingsWithCreate()
    player = FakePlayer(ids={"Secondbot": 99})
    module = make_online(bot, monkeypatch, settings=settings, player=player)
    settings.set("Online", "OtherBots", "Secondbot")
    result = module.otherbots("t1.")
    assert "Secondbot" in result
    assert bot.botname in result


def test_otherbots_skips_unknown_bot_names(bot, monkeypatch):
    settings = _FakeSettingsWithCreate()
    module = make_online(bot, monkeypatch, settings=settings)
    settings.set("Online", "OtherBots", "Nonexistentbot")
    result = module.otherbots("t1.")
    assert "Nonexistentbot" not in result


def test_channels_both(bot, monkeypatch):
    settings = _FakeSettingsWithCreate()
    module = make_online(bot, monkeypatch, settings=settings)
    settings.set("Online", "Channel", "both")
    assert module.channels("t1.") == "(t1.status_gc = 1 OR t1.status_pg = 1)"


def test_channels_guild(bot, monkeypatch):
    settings = _FakeSettingsWithCreate()
    module = make_online(bot, monkeypatch, settings=settings)
    settings.set("Online", "Channel", "guild")
    assert module.channels("t1.") == "t1.status_gc = 1"


def test_channels_pgroup(bot, monkeypatch):
    settings = _FakeSettingsWithCreate()
    module = make_online(bot, monkeypatch, settings=settings)
    settings.set("Online", "Channel", "pgroup")
    assert module.channels("t1.") == "t1.status_pg = 1"


def test_list_users_unknown_channel_returns_bot_error(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    result = module.list_users("bogus")
    assert isinstance(result, BotError)


def test_list_users_returns_nicknames(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [{"nickname": "Someone"}, {"nickname": "Other"}])
    result = module.list_users("gc")
    assert result == ["Someone", "Other"]


def test_list_users_no_users_returns_bot_error(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    monkeypatch.setattr(bot.db, "select", lambda sql, *a, **kw: [])
    result = module.list_users("pg")
    assert isinstance(result, BotError)


def test_list_users_with_botlist_filters_by_bots(bot, monkeypatch):
    module = make_online(bot, monkeypatch)
    captured = {}

    def fake_select(sql, *a, **kw):
        captured["sql"] = sql
        return [{"nickname": "Someone"}]

    monkeypatch.setattr(bot.db, "select", fake_select)
    module.list_users("both", "bota,botb")
    assert "botname='Bota'" in captured["sql"]
    assert "botname='Botb'" in captured["sql"]
