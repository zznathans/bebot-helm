from bebot.main_modules import fun_filters
from bebot.main_modules.fun_filters import FunFilters


def make_fun_filters(bot) -> FunFilters:
    return FunFilters(bot)


# -- registration --------------------------------------------------------------

def test_registers_as_funfilters_module(bot):
    module = make_fun_filters(bot)
    assert bot.core("funfilters") is module


# -- rot13 ----------------------------------------------------------------------

def test_rot13_encodes_letters_leaves_digits_and_punctuation(bot):
    module = make_fun_filters(bot)
    assert module.rot13("Secret Message 42") == "Frperg Zrffntr 42"


def test_rot13_is_its_own_inverse(bot):
    module = make_fun_filters(bot)
    assert module.rot13(module.rot13("round trip")) == "round trip"


# -- nofont -----------------------------------------------------------------

def test_nofont_strips_opening_and_closing_font_tags(bot):
    module = make_fun_filters(bot)
    text = "<font color=#FF0000>red</font> and <font color=blue>blue</font> text"
    assert module.nofont(text) == "red and blue text"


def test_nofont_leaves_text_without_font_tags_unchanged(bot):
    module = make_fun_filters(bot)
    assert module.nofont("plain text") == "plain text"


# -- chef (Swedish Chef) ------------------------------------------------------

def test_chef_basic_sentence(bot):
    module = make_fun_filters(bot)
    result = module.chef("This is the best restaurant.")
    assert result == "Thees is zee best restoorunt.\nBork Bork Bork!"


def test_chef_the_and_over_and_multiple_sentences(bot):
    module = make_fun_filters(bot)
    result = module.chef("The food is over there.")
    assert result == "Zee fuud is oofer zeere-a.\nBork Bork Bork!"


def test_chef_appends_bork_after_each_terminator(bot):
    module = make_fun_filters(bot)
    result = module.chef("Hello world!")
    assert result == "Hellu vurld!\nBork Bork Bork!"


# -- eleet ----------------------------------------------------------------------

def test_eleet_translates_and_lowercases(bot):
    module = make_fun_filters(bot)
    result = module.eleet("You are an elite hacker for sure")
    assert result == "j00 r 4n l337 h4x0r f0r 5ur3"


def test_eleet_fixes_up_h07_to_h4wt(bot):
    module = make_fun_filters(bot)
    # "hot" -> lower "hot" -> o replaced with 0 -> "h0t" -> t replaced with 7 -> "h07"
    # -> fixed up to "h4Wt".
    result = module.eleet("hot")
    assert result == "h4Wt"


# -- fudd (Elmer Fudd) --------------------------------------------------------

def test_fudd_replaces_r_and_l_with_w(bot):
    module = make_fun_filters(bot)
    result = module.fudd("The rabbit runs really fast.")
    assert result == "De wabbit wuns weawwy fast."


def test_fudd_word_final_th_becomes_f(bot):
    module = make_fun_filters(bot)
    assert module.fudd("with") == "wif"


def test_fudd_period_after_n_gets_stutter(bot):
    module = make_fun_filters(bot)
    assert module.fudd("Fun. Sun.") == "Fun, uh-hah-hah-hah. Sun, uh-hah-hah-hah."


# -- pirate -----------------------------------------------------------------

def test_pirate_translates_common_words_without_terminal_punctuation(bot):
    module = make_fun_filters(bot)
    # No trailing '.', '!' or '?' -> the random "shout" logic never triggers,
    # keeping this test fully deterministic.
    result = module.pirate("My friend, you are the captain of this ship")
    assert result == "me matey, ye are th' Cap'n o' this ship"


def test_pirate_appends_shout_when_winner_true(bot, monkeypatch):
    module = make_fun_filters(bot)
    monkeypatch.setattr(module, "winner", lambda chance: True)
    monkeypatch.setattr(fun_filters.random, "choice", lambda seq: seq[0])
    result = module.pirate("Hello there.")
    assert result == "Hello there, avast."


def test_pirate_no_shout_when_winner_false(bot, monkeypatch):
    module = make_fun_filters(bot)
    monkeypatch.setattr(module, "winner", lambda chance: False)
    result = module.pirate("Hello there.")
    assert result == "Hello there."


def test_pirate_ing_becomes_in_apostrophe(bot):
    module = make_fun_filters(bot)
    result = module.pirate("I am sailing and singing")
    assert result == "I am sailin' and singin'"


# -- winner -------------------------------------------------------------------

def test_winner_returns_bool(bot):
    module = make_fun_filters(bot)
    assert isinstance(module.winner(2), bool)
