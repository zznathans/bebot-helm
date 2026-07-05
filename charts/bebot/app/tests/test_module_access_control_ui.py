from bebot.commodities.base import BaseActiveModule
from bebot.main_modules.access_control import AccessControl
from bebot.main_modules.access_control_ui import AccessControlUi
from bebot.main_modules.settings import Settings
from bebot.main_modules.tools import Tools
from fakes import RecordingModule


class _DummyCommand(BaseActiveModule):
    """Minimal BaseActiveModule stand-in used to register a real command +
    access_control entry for a channel, the way any other main_module would,
    so AccessControlUi has something real to list/update."""

    def command_handler(self, name, msg, origin):
        return "ok"


def register_dummy(bot, channel: str, command: str, access: str = "GUEST", subcommands=None) -> _DummyCommand:
    module = _DummyCommand(bot, f"Dummy_{command}")
    module.register_command(channel, command, access, subcommands)
    return module


def make_ui(bot) -> AccessControlUi:
    Tools(bot)
    Settings(bot)
    AccessControl(bot)
    bot.register_module(RecordingModule("help"), "help")
    return AccessControlUi(bot)


# -- construction --------------------------------------------------------------

def test_registers_as_access_control_ui_module(bot):
    module = make_ui(bot)
    assert bot.core("access_control_ui") is module


def test_registers_channel_and_commands_commands(bot):
    module = make_ui(bot)
    assert bot.commands["tell"]["channel"] is module
    assert bot.commands["tell"]["commands"] is module
    assert bot.commands["gc"]["commands"] is module
    assert bot.commands["pgmsg"]["commands"] is module


def test_ensures_commands_tell_access_forced_to_owner_on_first_run(bot):
    module = make_ui(bot)
    ac = bot.core("access_control")
    assert ac.access_cache["commands"]["*"]["tell"] == "OWNER"
    # register_command("all", "commands", "SUPERADMIN") must not have clobbered it back down
    assert ac.access_cache["commands"]["*"]["gc"] == "SUPERADMIN"


# -- command_handler dispatch ---------------------------------------------------

def test_command_handler_unknown_shows_help_link(bot):
    module = make_ui(bot)
    result = module.command_handler("Admin", "commands bogus_thing_xyz", "tell")
    assert "Help" in result
    assert "commands" in result


def test_command_handler_commands_dispatches_show_channels(bot):
    module = make_ui(bot)
    register_dummy(bot, "tell", "foo")
    result = module.command_handler("Admin", "commands", "tell")
    assert "Select a channel" in result


def test_command_handler_channel_shows_locks(bot):
    module = make_ui(bot)
    result = module.command_handler("Admin", "channel", "tell")
    assert "guild chat" in result
    assert "unlocked" in result


def test_command_handler_channel_lock_unlock_dispatches(bot):
    module = make_ui(bot)
    result = module.command_handler("Admin", "channel lock gc", "tell")
    assert "locked from use" in result
    result = module.command_handler("Admin", "channel unlock gc", "tell")
    assert "free to be used" in result


# -- show_channels ---------------------------------------------------------------

def test_show_channels_lists_registered_channels(bot):
    module = make_ui(bot)
    register_dummy(bot, "tell", "foo")
    result = module.show_channels()
    assert "commands tell" in result
    assert "commands all" in result
    assert "commands extpgmsg" not in result


def test_show_channels_includes_guild_channel_when_registered(bot):
    module = make_ui(bot)
    register_dummy(bot, "gc", "foo")
    result = module.show_channels()
    assert "commands gc" in result


def test_show_channels_omits_guild_channel_when_not_guildbot(make_bot):
    bot = make_bot(guildbot=False)
    module = make_ui(bot)
    result = module.show_channels()
    assert "commands gc" not in result


# -- show_levels ------------------------------------------------------------------

def test_show_levels_no_commands_in_channel(bot):
    # In practice AccessControlUi's own "channel"/"commands" commands are
    # always registered to every channel, so this branch is only reachable
    # if a channel's command table is empty outright -- simulate that here.
    module = make_ui(bot)
    bot.commands["pgmsg"] = {}
    result = module.show_levels("pgmsg")
    assert result == "No commands defined in this channel!"


def test_show_levels_all_no_commands_defined(bot):
    module = make_ui(bot)
    bot.commands["gc"] = {}
    bot.commands["pgmsg"] = {}
    bot.commands["tell"] = {}
    result = module.show_levels("all")
    assert result == "No commands defined!"


def test_show_levels_lists_registered_command_with_options(bot):
    module = make_ui(bot)
    register_dummy(bot, "tell", "foo", access="GUEST")
    result = module.show_levels("tell")
    assert "foo" in result
    assert "commands update tell foo" in result
    # GUEST is the current level so it should appear as plain shortcut text,
    # not a clickable "change to GUEST" link
    assert "commands update tell foo G" not in result


def test_show_levels_all_channel_shows_na_for_unregistered_channels(bot):
    module = make_ui(bot)
    register_dummy(bot, "tell", "foo", access="GUEST")
    result = module.show_levels("all")
    assert "N/A" in result
    assert "foo" in result


def test_show_levels_with_subcommands_shows_subs_link(bot):
    module = make_ui(bot)
    register_dummy(bot, "tell", "foo", access="GUEST", subcommands={"bar": "ADMIN"})
    result = module.show_levels("tell")
    assert "commands subs foo" in result


# -- show_sub_levels --------------------------------------------------------------

def test_show_sub_levels_unknown_command(bot):
    module = make_ui(bot)
    result = module.show_sub_levels("nonexistent")
    assert "Does not Exist" in result


def test_show_sub_levels_no_subs_defined(bot):
    module = make_ui(bot)
    register_dummy(bot, "tell", "foo")
    result = module.show_sub_levels("foo")
    assert "No Subcommand access levels defined" in result


def test_show_sub_levels_lists_subcommand_with_del_link(bot):
    module = make_ui(bot)
    register_dummy(bot, "tell", "foo", subcommands={"bar": "ADMIN"})
    result = module.show_sub_levels("foo")
    assert "foo bar" in result
    assert "commands del tell foo bar" in result


# -- update_level -----------------------------------------------------------------

def test_update_level_invalid_shortcut_rejected(bot):
    module = make_ui(bot)
    result = module.update_level("tell", "foo", "ZZ")
    assert result == "Invalid access level selected!"


def test_update_level_invalid_full_name_rejected(bot):
    module = make_ui(bot)
    result = module.update_level("tell", "foo", "NOTALEVEL")
    assert result == "Invalid access level selected!"


def test_update_level_cannot_disable_commands_in_tell(bot):
    module = make_ui(bot)
    result = module.update_level("tell", "commands", "D")
    assert "cannot disable" in result


def test_update_level_cannot_disable_commands_in_all(bot):
    module = make_ui(bot)
    result = module.update_level("all", "commands", "DISABLED")
    assert "cannot disable" in result


def test_update_level_updates_single_channel(bot):
    module = make_ui(bot)
    register_dummy(bot, "tell", "foo", access="GUEST")
    result = module.update_level("tell", "foo", "A")
    ac = bot.core("access_control")
    assert ac.access_cache["foo"]["*"]["tell"] == "ADMIN"
    assert "foo" in result
    assert "ADMIN" in result


def test_update_level_updates_all_channels(bot):
    module = make_ui(bot)
    register_dummy(bot, "tell", "foo", access="GUEST")
    module.update_level("all", "foo", "ADMIN")
    ac = bot.core("access_control")
    assert ac.access_cache["foo"]["*"]["tell"] == "ADMIN"
    assert ac.access_cache["foo"]["*"]["gc"] == "ADMIN"
    assert ac.access_cache["foo"]["*"]["pgmsg"] == "ADMIN"


def test_update_level_subcommand_writes_directly_and_refreshes_cache(bot):
    module = make_ui(bot)
    register_dummy(bot, "tell", "foo", subcommands={"bar": "ADMIN"})
    help_module = bot.core("help")
    result = module.update_level("tell", "foo", "OWNER", "bar")
    ac = bot.core("access_control")
    assert ac.access_cache["foo"]["bar"]["tell"] == "OWNER"
    assert "foo bar" in result
    insert_queries = [q for q in bot.db.queries if q.startswith("INSERT INTO #___access_control")]
    assert any("'foo', 'bar', 'tell', 'OWNER'" in q for q in insert_queries)
    assert ("update_cache", (), {}) in help_module.calls


def test_command_handler_update_dispatches(bot):
    module = make_ui(bot)
    register_dummy(bot, "tell", "foo", access="GUEST")
    result = module.command_handler("Admin", "commands update tell foo A", "tell")
    assert "ADMIN" in result


def test_command_handler_update_subcommand_dispatches(bot):
    module = make_ui(bot)
    register_dummy(bot, "tell", "foo", subcommands={"bar": "ADMIN"})
    result = module.command_handler("Admin", "commands update tell foo bar O", "tell")
    ac = bot.core("access_control")
    assert ac.access_cache["foo"]["bar"]["tell"] == "OWNER"
    assert "foo bar" in result


def test_command_handler_add_subcommand_dispatches(bot):
    module = make_ui(bot)
    register_dummy(bot, "tell", "foo", subcommands={"bar": "ADMIN"})
    result = module.command_handler("Admin", "commands add tell foo bar O", "tell")
    ac = bot.core("access_control")
    assert ac.access_cache["foo"]["bar"]["tell"] == "OWNER"


def test_command_handler_del_subcommand_sets_deleted(bot):
    module = make_ui(bot)
    register_dummy(bot, "tell", "foo", subcommands={"bar": "ADMIN"})
    result = module.command_handler("Admin", "commands del tell foo bar", "tell")
    ac = bot.core("access_control")
    assert ac.access_cache["foo"]["bar"]["tell"] == "DELETED"
    assert "DELETED" in result


def test_command_handler_rem_subcommand_sets_deleted(bot):
    module = make_ui(bot)
    register_dummy(bot, "tell", "foo", subcommands={"bar": "ADMIN"})
    result = module.command_handler("Admin", "commands rem tell foo bar", "tell")
    ac = bot.core("access_control")
    assert ac.access_cache["foo"]["bar"]["tell"] == "DELETED"


def test_command_handler_subs_dispatches(bot):
    module = make_ui(bot)
    register_dummy(bot, "tell", "foo", subcommands={"bar": "ADMIN"})
    result = module.command_handler("Admin", "commands subs foo", "tell")
    assert "foo bar" in result


def test_command_handler_channel_specific_view_dispatches(bot):
    module = make_ui(bot)
    register_dummy(bot, "gc", "foo", access="GUEST")
    result = module.command_handler("Admin", "commands gc", "tell")
    assert "foo" in result


# -- channel_lock / show_channel_locks --------------------------------------------

def test_channel_lock_gc(bot):
    module = make_ui(bot)
    result = module.channel_lock("gc", True)
    assert "guild chat" in result
    assert "locked from use" in result
    assert bot.core("settings").get("AccessControl", "LockGc") is True


def test_channel_lock_pgmsg(bot):
    module = make_ui(bot)
    result = module.channel_lock("pgmsg", False)
    assert "private group" in result
    assert "free to be used" in result
    assert bot.core("settings").get("AccessControl", "LockPgroup") is False


def test_channel_lock_invalid_channel(bot):
    module = make_ui(bot)
    result = module.channel_lock("tell", True)
    assert "Error" in result


def test_show_channel_locks_reflects_settings(bot):
    module = make_ui(bot)
    module.channel_lock("gc", True)
    result = module.show_channel_locks()
    assert "guild chat" in result
    assert "locked" in result
    assert "private group" in result
    assert "unlocked" in result
