from fakes import FakePlayer, FakeSecurity, FakeSettings, RecordingModule


class FakeChat:
    def __init__(self, group_name):
        self.group_name = group_name

    def lookup_group(self, gid):
        return self.group_name

    def get_gname(self, gid):
        return self.group_name


def base_deps(bot, player=None, security=None, settings=None):
    bot.register_module(player or FakePlayer(), "player")
    bot.register_module(security or FakeSecurity(), "security")
    bot.register_module(settings or FakeSettings(), "settings")


# -- inc_tell -------------------------------------------------------------------

def test_inc_tell_ignores_message_from_self(bot):
    base_deps(bot, player=FakePlayer(names={1: bot.botname}))
    logged = []
    bot.log = lambda *a, **kw: logged.append(a)
    bot.inc_tell([1, "hi"])
    assert logged == []


def test_inc_tell_ignores_other_bots(bot):
    bot.other_bots = {"OtherBot": True}
    base_deps(bot, player=FakePlayer(names={1: "OtherBot"}))
    sent = []
    bot.send_help = lambda to: sent.append(("help", to))
    bot.send_tell = lambda to, msg: sent.append(("tell", to, msg))
    bot.inc_tell([1, "hi"])
    assert sent == []


def test_inc_tell_sends_help_for_unfound_guest(bot):
    base_deps(bot, player=FakePlayer(names={1: "Someone"}), security=FakeSecurity(access=True))
    helped = []
    bot.send_help = lambda to: helped.append(to)
    bot.inc_tell([1, "gibberish"])
    assert helped == [1]


def test_inc_tell_sends_generic_message_when_access_denied(bot):
    base_deps(bot, player=FakePlayer(names={1: "Someone"}), security=FakeSecurity(access=False))
    bot.guildbot = True
    sent = []
    bot.send_tell = lambda to, msg: sent.append((to, msg))
    bot.inc_tell([1, "gibberish"])
    assert sent == [(1, "I only listen to members of the guild.")]


def test_inc_tell_sends_command_error_text(bot):
    settings = FakeSettings({("Core", "CommandErrortell"): True})
    from fakes import FakeAccessControl, FakeCommandAlias

    bot.register_module(FakePlayer(names={1: "Someone"}), "player")
    bot.register_module(FakeSecurity(), "security")
    bot.register_module(settings, "settings")
    bot.register_module(FakeAccessControl(allow=False, min_rights=3), "access_control")
    bot.register_module(FakeCommandAlias(), "command_alias")
    bot.register_command("tell", "help", RecordingModule())
    sent = []
    bot.send_tell = lambda to, msg: sent.append((to, msg))
    bot.inc_tell([1, "!help"])
    assert sent
    assert "help" in sent[0][1]


# -- inc_pgjoin / inc_pgleave -----------------------------------------------------

def test_inc_pgjoin_own_group_dispatches_pgjoin(bot):
    base_deps(bot, player=FakePlayer(names={2: "Newcomer"}))
    mod = RecordingModule()
    bot.register_event("pgjoin", None, mod)
    bot.inc_pgjoin([bot.botname, 2])
    assert mod.calls == [("pgjoin", ("Newcomer",), {})]


def test_inc_pgjoin_foreign_group_dispatches_extpgjoin(bot):
    base_deps(bot, player=FakePlayer(names={2: "Newcomer"}))
    mod = RecordingModule()
    bot.register_event("extpgjoin", None, mod)
    bot.inc_pgjoin(["OtherOrg", 2])
    assert mod.calls == [("extpgjoin", ("OtherOrg", "Newcomer"), {})]


def test_inc_pgleave_own_group_dispatches_pgleave(bot):
    base_deps(bot, player=FakePlayer(names={2: "Leaver"}))
    mod = RecordingModule()
    bot.register_event("pgleave", None, mod)
    bot.inc_pgleave([bot.botname, 2])
    assert mod.calls == [("pgleave", ("Leaver",), {})]


# -- inc_pgmsg --------------------------------------------------------------------

def test_inc_pgmsg_own_output_logged_and_not_redispatched(bot):
    settings = FakeSettings({("Core", "LogPGOutput"): True})
    base_deps(bot, player=FakePlayer(names={1: bot.botname, 2: bot.botname}), settings=settings)
    logged = []
    bot.log = lambda *a, **kw: logged.append(a)
    bot.handle_command_input = lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not dispatch"))
    bot.inc_pgmsg([1, 2, "hello"])
    assert logged


def test_inc_pgmsg_ignores_other_bots(bot):
    bot.other_bots = {"OtherBot": True}
    base_deps(bot, player=FakePlayer(names={1: bot.botname, 2: "OtherBot"}))
    dispatched = []
    bot.handle_command_input = lambda *a, **kw: dispatched.append(a) or False
    bot.inc_pgmsg([1, 2, "hello"])
    assert dispatched == []


def test_inc_pgmsg_dispatches_command_in_own_group(bot):
    base_deps(bot, player=FakePlayer(names={1: bot.botname, 2: "Someone"}))
    dispatched = []
    bot.handle_command_input = lambda user, msg, channel: dispatched.append((user, msg, channel)) or True
    bot.inc_pgmsg([1, 2, "!help"])
    assert dispatched == [("Someone", "!help", "pgmsg")]


def test_inc_pgmsg_dispatches_extpgmsg_for_foreign_group(bot):
    base_deps(bot, player=FakePlayer(names={1: "OtherOrg", 2: "Someone"}))
    dispatched = []
    bot.handle_command_input = lambda user, msg, channel, pgname=None: dispatched.append(
        (user, msg, channel, pgname)
    ) or True
    bot.inc_pgmsg([1, 2, "!help"])
    assert dispatched == [("Someone", "!help", "extpgmsg", "OtherOrg")]


# -- inc_gannounce ----------------------------------------------------------------

def test_inc_gannounce_sets_guildname_on_matching_code(bot):
    bot.inc_gannounce([None, "NewOrgName", 32772])
    assert bot.guildname == "NewOrgName"


def test_inc_gannounce_ignores_other_codes(bot):
    bot.guildname = "Unchanged"
    bot.inc_gannounce([None, "NewOrgName", 1])
    assert bot.guildname == "Unchanged"


# -- inc_pginvite -----------------------------------------------------------------

def test_inc_pginvite_dispatches_registered_modules(bot):
    base_deps(bot, player=FakePlayer(names={5: "SomeOrg"}))
    mod = RecordingModule()
    bot.register_event("pginvite", None, mod)
    bot.inc_pginvite([5])
    assert mod.calls == [("pginvite", ("SomeOrg",), {})]


# -- inc_gmsg ---------------------------------------------------------------------

def test_inc_gmsg_ignores_unknown_group(bot):
    bot.guildname = "MyGuild"
    bot.register_module(FakeChat("SomeOtherGroup"), "chat")
    base_deps(bot)
    dispatched = []
    bot.handle_command_input = lambda *a, **kw: dispatched.append(a) or False
    bot.inc_gmsg([99, 0, "hello"])
    assert dispatched == []


def test_inc_gmsg_dispatches_for_guild_channel(bot):
    bot.guildname = "MyGuild"
    bot.register_module(FakeChat("MyGuild"), "chat")
    base_deps(bot, player=FakePlayer(names={7: "Someone"}))
    dispatched = []
    bot.handle_command_input = lambda user, msg, channel: dispatched.append((user, msg, channel)) or True
    bot.inc_gmsg([99, 7, "!help"])
    assert dispatched == [("Someone", "!help", "gc")]


def test_inc_gmsg_ignores_own_output_when_logged(bot):
    bot.guildname = "MyGuild"
    bot.register_module(FakeChat("MyGuild"), "chat")
    base_deps(bot, player=FakePlayer(names={7: bot.botname}), settings=FakeSettings({("Core", "LogGCOutput"): True}))
    dispatched = []
    bot.handle_command_input = lambda *a, **kw: dispatched.append(a) or True
    bot.inc_gmsg([99, 7, "hello"])
    assert dispatched == []
