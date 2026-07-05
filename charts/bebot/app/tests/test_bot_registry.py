from fakes import RecordingModule


def test_register_module_success(bot):
    mod = RecordingModule("mod")
    bot.register_module(mod, "MyModule")
    assert bot.exists_module("mymodule")
    assert bot.core("mymodule") is mod


def test_register_module_duplicate_keeps_original_and_logs(bot):
    first = RecordingModule("first")
    second = RecordingModule("second")
    bot.register_module(first, "dupe")
    bot.register_module(second, "dupe")
    assert bot.core("dupe") is first


def test_unregister_module(bot):
    mod = RecordingModule("mod")
    bot.register_module(mod, "mymodule")
    bot.unregister_module("MyModule")
    assert not bot.exists_module("mymodule")


def test_exists_module_false_for_unknown(bot):
    assert bot.exists_module("nope") is False


def test_core_returns_dummy_module_for_missing(bot):
    dummy = bot.core("missing")
    assert bool(dummy) is False
    result = dummy.some_method("x")
    assert "not loaded" in result


def test_register_command_single_channel(bot):
    mod = RecordingModule()
    bot.register_command("tell", "help", mod)
    assert bot.exists_command("tell", "help")
    assert bot.get_command_handler("tell", "help") == "RecordingModule"


def test_register_command_all_expands_to_all_channels(bot):
    mod = RecordingModule()
    bot.register_command("all", "help", mod)
    assert bot.exists_command("all", "help")
    for channel in ("gc", "tell", "pgmsg"):
        assert bot.exists_command(channel, "help")


def test_unregister_command(bot):
    mod = RecordingModule()
    bot.register_command("tell", "help", mod)
    bot.unregister_command("tell", "help")
    assert not bot.exists_command("tell", "help")


def test_unregister_command_all(bot):
    mod = RecordingModule()
    bot.register_command("all", "help", mod)
    bot.unregister_command("all", "help")
    assert not bot.exists_command("all", "help")


def test_exists_command_all_requires_every_channel(bot):
    mod = RecordingModule()
    bot.register_command("tell", "help", mod)
    assert not bot.exists_command("all", "help")


def test_get_command_handler_returns_empty_for_unknown(bot):
    assert bot.get_command_handler("tell", "nope") == ""
