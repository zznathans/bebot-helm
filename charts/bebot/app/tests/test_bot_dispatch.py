from fakes import (
    FakeAccessControl,
    FakeCommandAlias,
    FakePlayer,
    FakeSecurity,
    FakeSettings,
    RecordingModule,
)


def register_dispatch_deps(bot, settings=None, access_control=None, security=None):
    bot.register_module(settings or FakeSettings(), "settings")
    bot.register_module(access_control or FakeAccessControl(), "access_control")
    bot.register_module(security or FakeSecurity(), "security")
    bot.register_module(FakeCommandAlias(), "command_alias")
    bot.register_module(FakePlayer(), "player")


# -- find_similar_command -----------------------------------------------------

def test_find_similar_command_exact_match(bot):
    bot.register_command("tell", "help", RecordingModule())
    assert bot.find_similar_command("tell", "help") == [0]


def test_find_similar_command_no_match_below_threshold(bot):
    bot.register_module(FakeSettings({("Core", "SimilarMinimum"): 99}), "settings")
    bot.register_command("tell", "help", RecordingModule())
    assert bot.find_similar_command("tell", "halp") == [0]


def test_find_similar_command_finds_close_match(bot):
    bot.register_module(FakeSettings({("Core", "SimilarMinimum"): 50}), "settings")
    bot.register_command("tell", "help", RecordingModule())
    ratio, candidate = bot.find_similar_command("tell", "halp")
    assert candidate == "help"
    assert ratio > 50


# -- check_access_and_execute --------------------------------------------------

def test_check_access_and_execute_unknown_command_returns_false(bot):
    register_dispatch_deps(bot)
    assert bot.check_access_and_execute("User", "help", "help", "tell", None) is False


def test_check_access_and_execute_denies_access(bot):
    register_dispatch_deps(bot, access_control=FakeAccessControl(allow=False))
    mod = RecordingModule()
    bot.register_command("tell", "help", mod)
    assert bot.check_access_and_execute("User", "help", "help", "tell", None) is False
    assert mod.calls == []


def test_check_access_and_execute_grants_access_and_calls_handler(bot):
    register_dispatch_deps(bot, access_control=FakeAccessControl(allow=True))
    mod = RecordingModule()
    bot.register_command("gc", "help", mod)
    assert bot.check_access_and_execute("User", "help", "help", "gc", None) is True
    assert mod.calls == [("gc", ("User", "help"), {})]


def test_check_access_and_execute_extpgmsg_passes_pgname(bot):
    register_dispatch_deps(bot, access_control=FakeAccessControl(allow=True))
    mod = RecordingModule()
    bot.register_command("extpgmsg", "help", mod)
    assert bot.check_access_and_execute("User", "help", "help", "extpgmsg", "SomeOrg") is True
    assert mod.calls == [("extpgmsg", ("SomeOrg", "User", "help"), {})]


# -- handle_command_input ------------------------------------------------------

def test_handle_command_input_no_commands_for_channel(bot):
    register_dispatch_deps(bot)
    assert bot.handle_command_input("User", "!help", "tell") is False


def test_handle_command_input_banned_user_is_banned_and_stopped(bot):
    register_dispatch_deps(bot, security=FakeSecurity(banned=True))
    bot.register_command("tell", "help", RecordingModule())
    banned = []
    bot.send_ban = lambda to, msg=False: banned.append(to)
    result = bot.handle_command_input("BadUser", "!help", "tell")
    assert result is True
    assert banned == ["BadUser"]


def test_handle_command_input_auto_prefixes_tells(bot):
    register_dispatch_deps(bot, access_control=FakeAccessControl(allow=True))
    mod = RecordingModule()
    bot.register_command("tell", "help", mod)
    result = bot.handle_command_input("User", "help", "tell")
    assert result is True
    assert mod.calls == [("tell", ("User", "help"), {})]


def test_handle_command_input_dispatches_matching_command(bot):
    register_dispatch_deps(bot, access_control=FakeAccessControl(allow=True))
    mod = RecordingModule()
    bot.register_command("gc", "help", mod)
    result = bot.handle_command_input("User", "!help", "gc")
    assert result is True
    assert mod.calls == [("gc", ("User", "help"), {})]


def test_handle_command_input_sets_command_error_text_on_denied_access(bot):
    settings = FakeSettings({("Core", "CommandErrorgc"): True})
    register_dispatch_deps(bot, settings=settings, access_control=FakeAccessControl(allow=False, min_rights=3))
    mod = RecordingModule()
    bot.register_command("gc", "help", mod)
    result = bot.handle_command_input("User", "!help", "gc")
    assert result is False
    assert bot.command_error_text is not None
    assert "help" in bot.command_error_text


def test_handle_command_input_no_prefix_mode(bot):
    bot.commpre = ""
    register_dispatch_deps(bot, access_control=FakeAccessControl(allow=True))
    mod = RecordingModule()
    bot.register_command("gc", "help", mod)
    result = bot.handle_command_input("User", "help", "gc")
    assert result is True
    assert mod.calls == [("gc", ("User", "help"), {})]


def test_handle_command_input_similar_check_dispatches_close_match(bot):
    settings = FakeSettings({("Core", "SimilarCheck"): True, ("Core", "SimilarMinimum"): 50})
    register_dispatch_deps(bot, settings=settings, access_control=FakeAccessControl(allow=True))
    mod = RecordingModule()
    bot.register_command("gc", "help", mod)
    result = bot.handle_command_input("User", "!halp", "gc")
    assert result is True
    assert mod.calls == [("gc", ("User", "help"), {})]


# -- hand_to_chat ---------------------------------------------------------------

def test_hand_to_chat_short_circuits_when_already_found(bot):
    mod = RecordingModule(return_value=True)
    bot.register_event("tells", None, mod)
    result = bot.hand_to_chat(True, "User", "hi", "tells")
    assert result is True
    assert mod.calls == []


def test_hand_to_chat_calls_generic_channel_handlers(bot):
    mod = RecordingModule(return_value=True)
    bot.register_event("tells", None, mod)
    result = bot.hand_to_chat(False, "User", "hi", "tells")
    assert result is True
    assert mod.calls == [("tells", ("User", "hi"), {})]


def test_hand_to_chat_gmsg_uses_org_alias_for_guildname(bot):
    bot.guildname = "MyGuild"
    mod = RecordingModule(return_value=True)
    bot.commands.setdefault("gmsg", {}).setdefault("org", {})["RecordingModule"] = mod
    result = bot.hand_to_chat(False, "User", "hi", "gmsg", "MyGuild")
    assert result is True
    assert mod.calls == [("gmsg", ("User", "org", "hi"), {})]


def test_hand_to_chat_extprivgroup_passes_group(bot):
    mod = RecordingModule(return_value=True)
    bot.commands.setdefault("extprivgroup", {})["RecordingModule"] = mod
    result = bot.hand_to_chat(False, "User", "hi", "extprivgroup", "SomeOrg")
    assert result is True
    assert mod.calls == [("extprivgroup", ("SomeOrg", "User", "hi"), {})]


def test_hand_to_chat_no_handlers_returns_found_unchanged(bot):
    result = bot.hand_to_chat(False, "User", "hi", "tells")
    assert result is False
