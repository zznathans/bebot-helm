from fakes import FakeColors, FakeHelp


def test_replace_string_tags(bot):
    bot.guildname = "MyGuild"
    bot.commpre = "!"
    result = bot.replace_string_tags("<botname> says <pre>help in <guildname>")
    assert result == "Testbot says !help in MyGuild"


def test_replace_string_tags_handles_missing_guildname(bot):
    bot.guildname = None
    result = bot.replace_string_tags("<guildname>|end")
    assert result == "|end"


def test_send_ban_sends_default_message_once(bot):
    sent = []
    bot.send_tell = lambda to, msg: sent.append((to, msg))
    bot.send_ban("Someone")
    assert sent == [("Someone", "You are banned from <botname>.")]


def test_send_ban_is_rate_limited(bot):
    sent = []
    bot.send_tell = lambda to, msg: sent.append((to, msg))
    bot.send_ban("Someone")
    result = bot.send_ban("Someone")
    assert result is False
    assert len(sent) == 1


def test_send_ban_custom_message(bot):
    sent = []
    bot.send_tell = lambda to, msg: sent.append((to, msg))
    bot.send_ban("Someone", "Custom ban reason")
    assert sent == [("Someone", "Custom ban reason")]


def test_send_permission_denied_returns_message_when_kind_zero(bot):
    result = bot.send_permission_denied("Someone", "mycommand", kind=0)
    assert result == "You do not have permission to access mycommand"


def test_send_permission_denied_sends_output_when_kind_given(bot):
    bot.register_module(FakeColors(), "colors")
    sent = []
    bot.send_tell = lambda to, msg, low=0: sent.append((to, msg))
    bot.send_permission_denied("Someone", "mycommand", kind=1)
    assert sent == [("Someone", "You do not have permission to access mycommand")]


def test_send_output_routes_tell(bot):
    bot.register_module(FakeColors(), "colors")
    sent = []
    bot.send_tell = lambda to, msg, low=0: sent.append(("tell", to, msg))
    bot.send_output("Someone", "hi", 0)
    assert sent == [("tell", "Someone", "hi")]


def test_send_output_routes_pgroup(bot):
    bot.register_module(FakeColors(), "colors")
    sent = []
    bot.send_pgroup = lambda msg: sent.append(("pgroup", msg))
    bot.send_output("Someone", "hi", "pgmsg")
    assert sent == [("pgroup", "hi")]


def test_send_output_routes_gc(bot):
    bot.register_module(FakeColors(), "colors")
    sent = []
    bot.send_gc = lambda msg, low=0: sent.append(("gc", msg))
    bot.send_output("Someone", "hi", "gc")
    assert sent == [("gc", "hi")]


def test_send_output_routes_both(bot):
    bot.register_module(FakeColors(), "colors")
    sent = []
    bot.send_gc = lambda msg, low=0: sent.append(("gc", msg))
    bot.send_pgroup = lambda msg: sent.append(("pgroup", msg))
    bot.send_output("Someone", "hi", "both")
    assert ("gc", "hi") in sent
    assert ("pgroup", "hi") in sent


def test_send_output_unknown_kind_logs_error(bot):
    bot.register_module(FakeColors(), "colors")
    logged = []
    bot.log = lambda first, second, msg: logged.append((first, second, msg))
    bot.send_output("Someone", "hi", "bogus")
    assert logged[0][0] == "OUTPUT"
    assert logged[0][1] == "ERROR"


def test_send_help_without_command(bot):
    sent = []
    bot.send_tell = lambda to, msg: sent.append((to, msg))
    bot.send_help("Someone")
    assert sent == [("Someone", "/tell <botname> <pre>help")]


def test_send_help_with_command_uses_help_module(bot):
    bot.register_module(FakeHelp(), "help")
    sent = []
    bot.send_tell = lambda to, msg: sent.append((to, msg))
    bot.send_help("Someone", "mycommand")
    assert sent == [("Someone", "help for mycommand")]
