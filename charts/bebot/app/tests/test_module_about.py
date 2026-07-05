from bebot.main_modules.about import About
from bebot.main_modules.command_alias import CommandAlias
from bebot.main_modules.tools import Tools
from fakes import FakeAccessControl


class _FakeAccessControlWithCreate(FakeAccessControl):
    """FakeAccessControl doesn't implement create() -- register_command()
    calls it to register the access level required for the "about" command."""

    def create(self, channel, command, access):
        pass


def make_module(bot) -> About:
    bot.register_module(_FakeAccessControlWithCreate(), "access_control")
    Tools(bot)
    CommandAlias(bot)
    return About(bot)


# -- construction / registration --------------------------------------------------

def test_registers_as_about_module(bot):
    module = make_module(bot)
    assert bot.core("about") is module


def test_registers_about_command_on_all_channels(bot):
    module = make_module(bot)
    for channel in ("tell", "gc", "pgmsg"):
        assert bot.commands[channel]["about"] is module


def test_registers_version_alias(bot):
    make_module(bot)
    assert bot.core("command_alias").exists("version")
    assert bot.core("command_alias").replace("version") == "about"


def test_help_describes_about_command(bot):
    module = make_module(bot)
    assert "about" in module.help["command"]


# -- about_blob -----------------------------------------------------------------

def test_command_handler_about_shows_client_and_credits(bot):
    module = make_module(bot)
    result = module.command_handler("Someuser", "about", "tell")
    assert "Bot Client:" in result
    assert "BeBot (Python port)" in result
    assert "Alreadythere (RK2)" in result
    assert "Temar (RK1 / Doomsayer)" in result
    assert "More details" in result


def test_command_handler_about_uses_chatcmd_link_on_ao(bot, monkeypatch):
    module = make_module(bot)
    monkeypatch.setattr(bot, "game", "Ao")
    result = module.command_handler("Someuser", "about", "tell")
    assert "chatcmd:///start" in result
    assert "BeBot website and support forums" in result


def test_command_handler_about_uses_plain_link_off_ao(bot, monkeypatch):
    module = make_module(bot)
    monkeypatch.setattr(bot, "game", "coc")
    result = module.command_handler("Someuser", "about", "tell")
    assert "chatcmd:///start http://bebot.link" not in result
    assert "BeBot website and support forums: http://bebot.link" in result


def test_command_handler_unhandled_command(bot):
    module = make_module(bot)
    result = module.command_handler("Someuser", "bogus", "tell")
    assert "Broken plugin" in result
    assert "bogus" in result
