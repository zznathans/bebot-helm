from bebot.main_modules.color_config_ui import ColorConfigUi
from bebot.main_modules.colors import Colors
from bebot.main_modules.tools import Tools


def make_module(bot) -> ColorConfigUi:
    Tools(bot)
    Colors(bot)
    return ColorConfigUi(bot)


# -- construction --------------------------------------------------------------

def test_registers_as_color_config_ui_module(bot):
    module = make_module(bot)
    assert bot.core("color_config_ui") is module


def test_registers_color_command(bot):
    make_module(bot)
    assert bot.commands["tell"]["color"] is bot.core("color_config_ui")
    assert bot.commands["gc"]["color"] is bot.core("color_config_ui")
    assert bot.commands["pgmsg"]["color"] is bot.core("color_config_ui")


def test_help_documents_kept_subset_only(bot):
    module = make_module(bot)
    assert set(module.help["command"].keys()) == {"color", "color <tag>"}


# -- dispatch -------------------------------------------------------------------

def test_command_handler_rejects_non_color_message(bot):
    module = make_module(bot)
    result = module.command_handler("Somechar", "theme", "tell")
    assert "unhandled command" in result


def test_command_handler_bare_color_lists_tags(bot):
    module = make_module(bot)
    result = module.command_handler("Somechar", "color", "tell")
    assert "Defined colors" in result


def test_command_handler_color_with_tag_shows_detail(bot):
    module = make_module(bot)
    result = module.command_handler("Somechar", "color highlight", "tell")
    assert "Color: highlight" in result


# -- show_colors ------------------------------------------------------------------

def test_show_colors_lists_every_defined_tag(bot):
    module = make_module(bot)
    colors = bot.core("colors")
    blob = module.show_colors()
    for tag in colors.color_tags:
        if tag == "##end##":
            continue
        name = tag.strip("#")
        assert name in blob


def test_show_colors_includes_font_codes(bot):
    module = make_module(bot)
    blob = module.show_colors()
    assert "<font color=#FFFFFF>" in blob


def test_show_colors_no_tags_defined_message(bot):
    module = make_module(bot)
    colors = bot.core("colors")
    colors.color_tags = {}
    assert module.show_colors() == "No color tags defined at all!"


def test_show_colors_excludes_end_tag_as_a_listed_color(bot):
    module = make_module(bot)
    blob = module.show_colors()
    # "end" itself is a closing tag, not a selectable color -- it shouldn't
    # appear as a standalone listed entry the way "normal"/"error"/etc do.
    assert "##end##end##end##" not in blob


# -- show_color -------------------------------------------------------------------

def test_show_color_known_tag_shows_code_and_preview(bot):
    module = make_module(bot)
    result = module.show_color("error")
    assert "Font code:" in result
    assert "<font color=#FF0000>" in result
    assert "Sample text in error" in result


def test_show_color_is_case_insensitive(bot):
    module = make_module(bot)
    result_lower = module.show_color("error")
    result_upper = module.show_color("ERROR")
    assert "Color: error" in result_lower
    assert "Color: error" in result_upper


def test_show_color_strips_surrounding_hashes(bot):
    module = make_module(bot)
    result = module.show_color("##warning##")
    assert "Color: warning" in result


def test_show_color_unknown_tag_returns_error(bot):
    module = make_module(bot)
    result = module.show_color("nonexistent")
    assert "##error##" in result
    assert "nonexistent" in result


def test_show_color_end_tag_is_not_selectable(bot):
    module = make_module(bot)
    result = module.show_color("end")
    assert "##error##" in result
