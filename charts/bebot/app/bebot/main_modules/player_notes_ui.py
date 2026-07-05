"""Ported from Modules/PlayerNotesUi.php (class `PlayerNotes_UI`).

Thin chat-command UI over the already-ported `core("player_notes")`
(main_modules/player_notes.py): lets a MEMBER add a note to a player, view
notes for one player or a "who has notes" overview of everyone, and lets an
ADMIN delete a note by its numeric id or add an "admin"-class note.

Scope notes / intentional deviations from the PHP:
  * `command_handler()`'s PHP switch has a genuinely dead `'admin'` branch:
    `$admin = explode(" ", $msg[2], 2);` indexes the *third character* of
    the raw command string (`$msg[2]`, PHP string-offset syntax) rather
    than the parsed remainder of the command, so as literally written it
    can never produce a usable admin note (and the preceding duplicate
    `case 'add':` right above it is unreachable dead code too, since the
    first `case 'add':` already returns). Faithfully reproducing this would
    make "notes admin <player> <note>" permanently non-functional, which
    is a stronger break than the "harmless but inert" quirks preserved
    verbatim elsewhere in this port (see settings_ui.py, shortcuts_ui.py) --
    there's no working behavior left to be faithful *to*. Instead this
    implements the clearly-intended behavior: "notes admin <player> <note>"
    adds an admin-class note, gated by the same runtime
    `core("security").check_access(author, "ADMIN")` check `add_note()`
    already performs in the PHP.
  * Subcommand matching in `command_handler()` is deliberately kept
    case-sensitive, same as the PHP (`switch ($com['sub'])` with no
    `strtolower()` applied to it here, unlike alias.py's Core/Alias.php
    which explicitly lowercases its subcommand token first) -- so
    "notes ADD Foo reason" falls through to the default per-player lookup,
    treating "ADD" as a player name to search notes for, exactly mirroring
    upstream rather than "fixing" it to be case-insensitive.
  * `show_notes()`'s timestamp used `gmdate($FormatString, ...)`. Nothing
    in this port consumes the `Time/FormatString` setting yet (see
    main_modules/time.py's and alts.py's docstrings -- no gmdate()
    implementation exists), so this renders the UTC timestamp with a fixed
    "%Y-%m-%d %H:%M:%S" format instead, matching that established
    precedent.
  * The PHP UI layer re-normalizes `$author`/`$player` inline
    (`ucfirst(strtoupper(...))`/`ucfirst(strtolower(...))`) before calling
    into Core/PlayerNotes.php. The already-ported `core("player_notes")`
    (`add()`/`get_notes()`) and `core("player")` (`id()`) already sanitize
    every name argument themselves via `core("tools").sanitize_player()`,
    so this doesn't duplicate that normalization here.
  * `del($pnid)` was ported as `delete(pnid)` on player_notes.py (`del` is
    a Python keyword) -- `rem_note()` below calls that instead.
  * Matching the PHP's `register_command()` call verbatim: only `add` and
    `rem` are registered as access-controlled subcommands (MEMBER/ADMIN
    respectively). `del` is accepted by the dispatcher as a synonym for
    `rem` but is *not* separately registered, so it falls back to the base
    "notes" command's MEMBER access -- a latent permission gap in the PHP
    original, preserved as-is rather than silently tightened.
"""
from __future__ import annotations

import time

from ..commodities.base import BaseActiveModule, BotError


class PlayerNotesUi(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.register_module("player_notes_ui")
        self.register_command("all", "notes", "MEMBER", {"add": "MEMBER", "rem": "ADMIN"})
        self.register_alias("notes", "note")
        self.help["description"] = "Allows viewing, adding and deleting notes attached to a player."
        self.help["command"] = {
            "notes": "Shows an overview of all players that have notes.",
            "notes <player>": "Shows the notes for <player>.",
            "notes add <player> <note>": "Adds <note> to <player>.",
            "notes admin <player> <note>": "Adds <note> to <player> as an admin note. Requires ADMIN access.",
            "notes rem <pnid>": "Deletes the note with id <pnid>.",
        }

    # -- dispatch ---------------------------------------------------------------
    def command_handler(self, name, msg, origin):
        parts = msg.split(" ", 2)
        sub = parts[1] if len(parts) > 1 else ""
        args = parts[2] if len(parts) > 2 else ""
        if sub == "add":
            return self.add_note(name, args)
        if sub == "admin":
            return self.add_note(name, args, admin=True)
        if sub in ("rem", "del"):
            return self.rem_note(args)
        if sub == "":
            return self.show_all_notes(name, origin)
        return self.show_notes(name, sub)

    # -- mutation -------------------------------------------------------------------
    def add_note(self, author: str, msg: str, admin: bool = False):
        parts = msg.split(" ", 1)
        player = parts[0] if parts else ""
        note = parts[1] if len(parts) > 1 else ""
        if admin:
            if self.bot.core("security").check_access(author, "ADMIN"):
                return self.bot.core("player_notes").add(player, author, note, "admin")
            self.error.set("Your access level must be ADMIN or higher to add admin notes.")
            return self.error
        return self.bot.core("player_notes").add(player, author, note, "default")

    def rem_note(self, pnid: str):
        return self.bot.core("player_notes").delete(pnid)

    # -- views --------------------------------------------------------------------
    def show_notes(self, source: str, player: str):
        player_id = self.bot.core("player").id(player)
        if isinstance(player_id, BotError) or not player_id:
            self.error.set(f"Player '{player}' is not a valid character")
            return self.error
        result = self.bot.core("player_notes").get_notes(source, player, "all", "DESC")
        if isinstance(result, BotError):
            return result
        tools = self.bot.core("tools")
        display_player = tools.sanitize_player(player)
        inside = f"Notes for {display_player}:\n\n"
        for pnid, _player, author, note, note_class, timestamp in result:
            if note_class == 1:
                inside += "Ban Reason #"
            elif note_class == 2:
                inside += "Admin Note #"
            else:
                inside += "Note #"
            when = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(timestamp))
            inside += f"{pnid} added by {author} on {when}:\n"
            inside += note
            inside += "\n\n"
        return "Notes for " + tools.make_blob(display_player, inside)

    def show_all_notes(self, source: str, origin) -> str:
        result = self.bot.core("player_notes").get_notes(source, "All", "all", "DESC")
        if isinstance(result, BotError):
            return ""
        tools = self.bot.core("tools")
        counts: dict[str, dict[int, int]] = {}
        for _pnid, player, _author, _note, note_class, _timestamp in result:
            per_player = counts.setdefault(player, {})
            per_player[note_class] = per_player.get(note_class, 0) + 1
        inside = "  :: All Players with Notes ::\n\n"
        for player, data in counts.items():
            admin_notes = data.get(2, 0)
            ban_notes = data.get(1, 0)
            normal_notes = data.get(0, 0)
            inside += (
                f"{tools.chatcmd(f'notes {player}', player, origin)} "
                f"{admin_notes} Admin Notes, {ban_notes} Ban Notes, {normal_notes} Normal Notes\n"
            )
        return "All Players with Notes :: " + tools.make_blob("Click to view", inside)
