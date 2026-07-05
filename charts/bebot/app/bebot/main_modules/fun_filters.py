"""Ported from Core/FunFilters.php.

Pure text-transformation module -- no dependencies on other core() modules.
Core/StringFilter.php (ported separately as string_filter.py) dispatches to
this module by name (``bot.core("funfilters")``) for its ``funmode`` command,
calling ``rot13``, ``chef``, ``eleet``, ``fudd``, ``pirate`` and ``nofont``
with a single ``text`` argument each -- those method names/signatures are
kept exact to match that caller.

Two faithfully-reproduced quirks from the PHP original, and one deliberate
fix, are worth calling out:

- ``eleet()``'s "replace f with ph, only at start of word" step is, in the
  PHP source, ``preg_replace("/\\f/", "ph", $text)`` written inside a
  double-quoted string -- PHP interprets ``\\f`` in a double-quoted string as
  a literal form-feed control character (0x0C), not the regex escape the
  comment describes. The pattern therefore searches for a literal form-feed
  byte, which essentially never appears in chat text, making this step a
  near no-op in practice. That real (buggy) behavior is reproduced here
  rather than the commented intent, since the two other engineers' code
  (StringFilter) depends on eleet() producing exactly what BeBot has always
  produced.
- ``nofont()``'s second PHP regex, ``preg_replace("/</font>/", "", $text)``,
  uses "/" as its own delimiter while "/" also appears inside the pattern
  text -- in real PHP this is a regex compile error (unknown modifier 'f')
  and preg_replace returns NULL, i.e. nofont() would always return an empty
  value in the original. That is almost certainly an unintentional bug (the
  clear intent, matching the function's own comment, is to also strip
  ``</font>`` closing tags after the opening ``<font ...>`` tags are
  removed), so the intended behavior is implemented here instead of the
  crash-on-every-call bug.
- ``pirate()``'s translation table has four entries keyed with ``\\y...\\b``
  / ``\\Y...\\b`` (for "yalm"/"yalmaha"/"Yalm"/"Yalmaha") instead of
  ``\\b...\\b``. ``\\y`` is not a valid PCRE escape, so in the original PHP
  this crashes preg_replace on every single call to pirate() (not just when
  the text mentions motorcycles), permanently corrupting the rest of that
  call's output. That's fixed here to the evidently-intended ``\\b`` word
  boundary so pirate() actually works.
"""
from __future__ import annotations

import codecs
import random
import re

from ..commodities.base import BasePassiveModule

# mt_getrandmax() on the vast majority of real-world (32-bit int) PHP builds.
_MT_RAND_MAX = 2147483647

# (regex pattern, replacement) pairs, applied in order, case-insensitively --
# ported verbatim from FunFilters::pirate()'s $trans_table, in the same
# order (later entries can be unreachable if an earlier, broader pattern
# already consumed the same text -- e.g. "him" is fully replaced before
# "him." is ever considered -- this mirrors the PHP original faithfully).
_PIRATE_TRANSLATIONS: list[tuple[str, str]] = [
    (r"\bmy\b", "me"),
    (r"\bboss\b", "admiral"),
    (r"\bmanager\b", "admiral"),
    (r"\b[Cc]aptain\b", "Cap'n"),
    (r"\bmyself\b", "meself"),
    (r"\byour\b", "yer"),
    (r"\byou\b", "ye"),
    (r"\bfriend\b", "matey"),
    (r"\bfriends\b", "maties"),
    (r"\bco[-]?worker\b", "shipmate"),
    (r"\bco[-]?workers\b", "shipmates"),
    (r"\bearlier\b", "afore"),
    (r"\bold\b", "auld"),
    (r"\bthe\b", "th'"),
    (r"\bof\b", "o'"),
    (r"\bdon't\b", "dern't"),
    (r"\bdo not\b", "dern't"),
    (r"\bnever\b", "ne'er"),
    (r"\bever\b", "e'er"),
    (r"\bover\b", "o'er"),
    (r"\bYes\b", "Aye"),
    (r"\bNo\b", "Nay"),
    (r"\bdon't know\b", "dinna"),
    (r"\bhadn't\b", "ha'nae"),
    (r"\bdidn't\b", "di'nae"),
    (r"\bwasn't\b", "weren't"),
    (r"\bhaven't\b", "ha'nae"),
    (r"\bfor\b", "fer"),
    (r"\bbetween\b", "betwixt"),
    (r"\baround\b", "aroun'"),
    (r"\bto\b", "t'"),
    (r"\bit's\b", "'tis"),
    (r"\bwoman\b", "wench"),
    (r"\blady\b", "wench"),
    (r"\bwife\b", "lady"),
    (r"\bgirl\b", "lass"),
    (r"\bgirls\b", "lassies"),
    (r"\bguy\b", "lubber"),
    (r"\bman\b", "lubber"),
    (r"\bfellow\b", "lubber"),
    (r"\bdude\b", "lubber"),
    (r"\bboy\b", "lad"),
    (r"\bboys\b", "laddies"),
    (r"\bchildren\b", "minnows"),
    (r"\bkids\b", "minnows"),
    (r"\bhim\b", "that scurvey dog"),
    (r"\bher\b", "that comely wench"),
    (r"\bhim\.\b", "that drunken sailor"),
    (r"\bHe\b", "The ornery cuss"),
    (r"\bShe\b", "The winsome lass"),
    (r"\bhe's\b", "he be"),
    (r"\bshe's\b", "she be"),
    (r"\bwas\b", "were bein'"),
    (r"\bHey\b", "Avast"),
    (r"\bher\.\b", "that lovely lass"),
    (r"\bfood\b", "chow"),
    (r"\broad\b", "sea"),
    (r"\broads\b", "seas"),
    (r"\bstreet\b", "river"),
    (r"\bstreets\b", "rivers"),
    (r"\bhighway\b", "ocean"),
    (r"\bhighways\b", "oceans"),
    (r"\bcar\b", "boat"),
    (r"\bcars\b", "boats"),
    (r"\btruck\b", "schooner"),
    (r"\btrucks\b", "schooners"),
    (r"\bSUV\b", "ship"),
    (r"\bmachine\b", "contraption"),
    (r"\bairplane\b", "flying machine"),
    (r"\bjet\b", "flying machine"),
    (r"\byalm\b", "flying machine"),
    (r"\byalmaha\b", "flying machine"),
    (r"\bYalmaha\b", "flying machine"),
    (r"\bYalm\b", "flying machine"),
    (r"\bdriving\b", "sailing"),
    (r"\bdrive\b", "sail"),
    (r"\bloot\b", "booty"),
    (r"\blooting\b", "plunderin"),
]

# array_rand'd shouts appended after a matching end-of-sentence stub, ported
# verbatim from FunFilters::pirate().
_PIRATE_SHOUTS = [
    ", avast{stub}",
    "{stub} Ahoy!",
    ", and a bottle of rum!",
    ", by Blackbeard's sword{stub}",
    ", by Davy Jones' locker{stub}",
    "{stub} Walk the plank!",
    "{stub} Aarrr!",
    "{stub} Yaaarrrrr!",
    ", pass the grog!",
    ", and dinna spare the whip!",
    ", with a chest full of booty{stub}",
    ", and a bucket o' chum{stub}",
    ", we'll keel-haul ye!",
    "{stub} Shiver me timbers!",
    "{stub} And hoist the mainsail!",
    "{stub} And swab the deck!",
    ", ye scurvey dog{stub}",
    "{stub} Fire the cannons!",
    ", to be sure{stub}",
    ", I'll warrant ye{stub}",
]

# str_replace($norm, $trans, $text) in FunFilters::eleet() -- applied as a
# sequence of individual replacements (each feeding the next), not a
# simultaneous substitution, so ordering matters (e.g. "elite" -> "l33t"
# happens before the later "t" -> "7" pass, which then further mangles that
# "l33t" into "l337" -- faithfully reproduced).
_ELEET_NORM = [
    "porn", "elite", "eleet", "your", "you're", "are", "fool", "you",
    "newbie", "noobie", "hoot", "loot", "hacker", "fear", "skill", "skills",
    "dude", "sucks", "suck", "a", "e", "i", "o", "s", "t", "for",
]
_ELEET_TRANS = [
    "pr0n", "l33t", "l33t", "l33t", "ur", "r", "f00", "j00", "n00b", "n00b",
    "w00t", "13wt", "h4x0r", "ph33r", "sk1llz", "sk1llz", "d00d", "sux0r",
    "sux0r", "4", "3", "1", "0", "5", "7", "4",
]


class FunFilters(BasePassiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("funfilters")

    def rot13(self, text: str) -> str:
        return codecs.encode(text, "rot13")

    def nofont(self, text: str) -> str:
        text = re.sub(r"<font.*?>", "", text)
        text = re.sub(r"</font>", "", text)
        return text

    def chef(self, text: str) -> str:
        the = "116, 104, 101"
        capital_the = "84, 72, 69"
        text = text.replace("THE", capital_the)
        text = text.replace("The", capital_the)
        text = text.replace("the", the)
        # Change 'e' at the end of a word to 'e-a' (excluding "the", already
        # swapped out above).
        text = re.sub(r"e\b", "e-a", text)
        # Stuff that happens at the end of a word.
        text = re.sub(r"en\b", "ee", text)
        text = re.sub(r"th\b", "t", text)
        # Stuff that happens if not the first letter of a word.
        text = re.sub(r"\Bf", "ff", text)
        # Change 'o' to 'u' and 'u' to 'oo', but only if not the first
        # letter of the word. First stash non-leading o/O as "111"...
        text = re.sub(r"\Bo", "111", text, flags=re.I)
        # ...then change u to oo...
        text = re.sub(r"\Bu", "oo", text, flags=re.I)
        # ...then change the stashed "111" to u.
        text = text.replace("111", "u")
        # If a word starts with o|O, change to oo|Oo.
        text = re.sub(r"\bo", "oo", text)
        text = re.sub(r"\bO", "Oo", text)
        # Fix the word "bork", which has been mangled to "burk".
        text = re.sub(r"\b[Bb]urk", "bork", text)
        # Stuff to do to letters that are the first letter of any word.
        text = re.sub(r"\be", "i", text)
        text = re.sub(r"\bE", "I", text)
        # Stuff that always happens.
        text = text.replace("tiun", "shun")
        text = text.replace(the, "zee")
        text = text.replace(capital_the, "Zee")
        text = text.replace("v", "f")
        text = text.replace("V", "F")
        text = text.replace("w", "v")
        text = text.replace("W", "V")
        # Stuff to do to letters that are not the last letter of a word:
        # change a to e and A to E.
        text = re.sub(r"a(?!\b)", "e", text)
        text = re.sub(r"A(?!\b)", "E", text)
        text = text.replace("en", "un")  # "an" -> "un"
        text = text.replace("En", "Un")  # "An" -> "Un"
        text = text.replace("eoo", "oo")  # "au" -> "oo"
        text = text.replace("Eoo", "Oo")  # "Au" -> "Oo"
        text = text.replace("uv", "oo")  # "ow" -> "oo"
        # Change 'i' to 'ee', but not at the beginning of a word, and only
        # affect the first 'i' in each word.
        text = re.sub(r"\B[^a-hj-zA-HJ-Z]*i", "ee", text)
        # Special punctuation at the end of sentences.
        text = re.sub(r"([.!?])", r"\1\nBork Bork Bork!", text)
        return text

    def pirate(self, text: str) -> str:
        text = text.strip()
        for pattern, replacement in _PIRATE_TRANSLATIONS:
            text = re.sub(pattern, replacement, text, flags=re.I)
        # Change "ing" to "in'".
        text = re.sub(r"ing\b", "in'", text, flags=re.I)
        text = re.sub(r"ings\b", "in's", text, flags=re.I)

        win = False
        stub = ""
        match = re.search(r"(\.( |\t|$))", text)
        if match:
            win = self.winner(2)
            stub = match.group(1)
        else:
            match = re.search(r"([!?]( \t|$))", text)
            if match:
                win = self.winner(3)
                stub = match.group(1)

        if win:
            shout = random.choice(_PIRATE_SHOUTS).format(stub=stub)
            text = text.rstrip(stub) if stub else text
            text = text + shout
        return text

    def eleet(self, text: str) -> str:
        text = text.lower()
        # Translate most of it -- sequential, cumulative replacements.
        for norm, trans in zip(_ELEET_NORM, _ELEET_TRANS):
            text = text.replace(norm, trans)
        # Replace f with ph, only at start of word -- in the PHP source this
        # is written inside a double-quoted string as "/\f/", where PHP
        # interprets \f as a literal form-feed byte rather than the regex
        # escape the surrounding comment describes, so this only ever
        # matches a literal form-feed character (faithfully reproduced).
        text = text.replace("\x0c", "ph")
        # Fix some excessive weirdness.
        text = text.replace("ph00", "f00")
        text = text.replace("1337", "l33t")
        # Add some other weirdness.
        text = text.replace("h07", "h4Wt")
        return text

    def fudd(self, text: str) -> str:
        text = re.sub(r"[rl]", "w", text)
        text = re.sub(r"qu", "qw", text)
        text = re.sub(r"th\b", "f", text)
        text = re.sub(r"th\B", "d", text)
        text = re.sub(r"n\.", "n, uh-hah-hah-hah.", text)
        text = re.sub(r"[RL]", "W", text)
        text = re.sub(r"Qu", "Qw", text)
        text = re.sub(r"QU", "QW", text)
        text = re.sub(r"TH\b", "F", text)
        text = re.sub(r"TH\B", "D", text)
        text = re.sub(r"Th", "D", text)
        text = re.sub(r"N\.", "N, uh-hah-hah-hah.", text)
        return text

    def winner(self, chance: int) -> bool:
        rand_int = random.randint(0, _MT_RAND_MAX)
        highlow = random.randint(0, 1)  # 0 = low, 1 = high
        if highlow:
            split = round(_MT_RAND_MAX / chance)
            return rand_int >= split
        split = round(_MT_RAND_MAX - _MT_RAND_MAX / chance)
        return rand_int <= split
