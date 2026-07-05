"""Ported from Modules/Mail.php (class `Mail`).

Lets members send each other asynchronous "mail" messages via tell,
delivered to a recipient's *main* character (resolved through
`core("alts")`) so alts share one mailbox. Built on top of already-ported
Core modules: `core("alts")` (main/alt resolution), `core("prefs")`
(per-user "how long to keep read/unread mail" + "notify on logon"
preferences), `core("settings")` (bot-wide max-life settings),
`core("security")` (recipient existence/access check for `mail send`),
`core("tools")` (`chatcmd()`/`sanitize_player()`), and `core("chat")`
(buddy-list online checks for the "you've got new mail" ping).

Scope notes / intentional deviations from the PHP:
  * Schema-version migration (`get_version()`/`update_table()`/
    `set_version()`, stepping the `mail_message` table's `recieved` typo'd
    column to `received`) is dropped, matching the precedent set by
    settings.py/access_control.py/player_notes.py/alts.py/online.py
    elsewhere in this port: the table is created directly with the final
    (v2) schema below since there's nothing to migrate for a fresh Python
    port. This codebase's `MySQL.query()`/`.select()` also has no
    `get_version`/`set_version`/`update_table` methods at all (see
    `bebot/mysql.py`), so there'd be nothing to call even if we wanted to.
  * `register_event("cron", "12hour")` was already commented out in the
    PHP original (`//$this -> register_event("cron", "12hour");`), so
    `cron()`'s "TODO: expire old messages" body was already dead code
    upstream. The method is kept here for parity but is likewise never
    registered/invoked.
  * `connect()`'s `$this->start = time() + $this->bot->crondelay` is
    ported faithfully (`self.start`) even though nothing else in the PHP
    class ever reads `$this->start` back -- it's vestigial state upstream,
    kept only so a reader diffing against the PHP doesn't wonder where it
    went.
  * This codebase's `Bot`/`MySQL` layer doesn't track affected-row counts
    the way `mysqli_affected_rows($this->bot->db->CONN)` did in PHP (see
    `bebot/mysql.py`: `query()` returns a plain bool). `mail_delete()`
    therefore checks for the row's existence with a `SELECT` before
    issuing the `DELETE`, rather than trusting a post-hoc affected-rows
    count -- same net effect (only delete/report success for a message
    that belongs to `name`'s mailbox) via a different, available
    mechanism.
  * `mail_send()`'s PHP has a latent bug worth flagging rather than
    silently fixing: it computes `$recipent = ...->sanitize_player(
    $recipient)` (note the misspelled variable name) and then never uses
    `$recipent` again -- every subsequent use in the function
    (`alts->main($recipient)`, `check_access($recipient, ...)`, the
    INSERT's `recipient` column) reads the *original*, unsanitized
    `$recipient`. This port reproduces that faithfully: `sanitize_player`
    is still called (in case it has side effects one day) but its result
    is discarded, same as upstream.
  * `command_handler()`'s target-is-a-message-id check
    (`is_int(intval($com['target']))`) is *always* true in PHP --
    `intval()` on any string, including `""` or `"abc"`, returns an int
    (`0` for non-numeric input), and `is_int()` on that result is always
    true. So the real behavior is just "was a target token present at
    all", and a non-numeric target silently becomes message id `0` rather
    than raising an error. This port keeps that permissive parsing
    (`_php_intval()` below) rather than "fixing" it into a stricter
    numeric check.
  * `parse_com()` (Commodities/01_BaseActiveModule.php) isn't a general
    utility in this Python port -- nothing else needs it yet -- so its
    specific behavior for Mail's `array('com','sub','target','message')`
    pattern (split the raw command text on spaces into at most 4 pieces)
    is reimplemented locally as a plain `msg.split(" ", 3)` in
    `command_handler()`, which is equivalent for this module's pattern.
    The item-reference-preservation step in `parse_com()` (temporarily
    replacing `<a href="itemref://...">` spans with `##item_N##` markers
    so splitting on spaces doesn't mangle them) is not ported: item
    references are an Ao-specific feature nothing else in this codebase
    parses yet either.
  * `notify()`'s PHP condition is
    `$this->bot->core("prefs")->get($name, "Mail", "Logon_notification")
    == true`. Since `prefs->get()` returns the raw string preference value
    ("Yes" or "No"), and PHP's loose `==` treats *any* non-empty,
    non-"0" string as equal to `true`, this condition is actually true for
    both "Yes" and "No" -- only an unset/empty preference would disable
    it. This is reproduced faithfully via a plain `bool(value)` truthiness
    check in Python (a non-empty string is truthy regardless of content),
    rather than "fixing" it into an actual `== "Yes"` comparison.
  * Message bodies are still round-tripped through `base64` (matching
    `base64_encode`/`base64_decode` in the PHP) purely for byte-for-byte
    behavioral parity with existing stored data/tooling expectations, not
    because Python needs it.
  * `stripslashes()` is reproduced with a small regex helper
    (`_stripslashes()`) that undoes the same backslash-escaping
    `mysqli_real_escape_string()`/`db.real_escape_string()` introduces on
    the way in, so round-tripped messages don't retain literal backslashes
    in front of quotes.
  * `mail_read()`'s/`mail_send()`'s `strtotime("+N unit")` expiry-date math
    is reimplemented with plain calendar arithmetic in `_expires_at()`
    (weeks/months/years, no external date library -- this repo doesn't
    depend on `python-dateutil`), operating on the same
    `Life_read`/`Max_life_unread` "N_unit" preference/setting strings
    (e.g. `"1_month"`, `"6_months"`).
  * Nothing here touches Core/Ao/Whois.php, IRC/relay bridges, or the
    dynamic Core/Modules/ plugin loader.
"""
from __future__ import annotations

import base64
import calendar
import re
import time
from datetime import datetime, timedelta

from ..commodities.base import BaseActiveModule


def _ucfirst(text: str) -> str:
    """PHP's ucfirst(): only the first character is uppercased."""
    return text[:1].upper() + text[1:] if text else text


def _php_intval(text: str) -> int:
    """PHP's intval(): parses a leading optional sign + digits, else 0."""
    if text is None:
        return 0
    match = re.match(r"\s*([+-]?\d+)", text)
    return int(match.group(1)) if match else 0


def _stripslashes(text: str) -> str:
    return re.sub(r"\\(.)", r"\1", text)


def _collapse_newlines(text: str, replacement: str) -> str:
    return re.sub(r"\r\n|\r|\n", replacement, text)


def _expires_at(spec: str, base: datetime | None = None) -> datetime:
    """Turns a "N_unit" spec (e.g. "1_month", "2_weeks", "6_months",
    "1_year") into an absolute datetime, mirroring the PHP's
    strtotime("+N unit") without a datetime-arithmetic library dependency.
    """
    base = base or datetime.now()
    spec = (spec or "").strip().lower()
    match = re.match(r"(\d+)_(\w+?)s?$", spec)
    if not match:
        return base
    count, unit = int(match.group(1)), match.group(2)
    if unit == "week":
        return base + timedelta(weeks=count)
    if unit == "month":
        month_index = base.month - 1 + count
        year = base.year + month_index // 12
        month = month_index % 12 + 1
        day = min(base.day, calendar.monthrange(year, month)[1])
        return base.replace(year=year, month=month, day=day)
    if unit == "year":
        try:
            return base.replace(year=base.year + count)
        except ValueError:
            return base.replace(year=base.year + count, day=28)
    return base


class Mail(BaseActiveModule):
    def __init__(self, bot):
        super().__init__(bot, type(self).__name__)
        self.start = 0

        db = bot.db
        db.query(
            f"CREATE TABLE IF NOT EXISTS {db.define_tablename('mail_message', True)} "
            "(id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, "
            "received TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "expires TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "is_read BOOL DEFAULT FALSE, "
            "mailbox VARCHAR(13), recipient VARCHAR(13), sender VARCHAR(13), message TEXT)"
        )

        self.register_module("mail")
        self.register_command("all", "mail", "GUEST")
        self.register_command("all", "mailed", "GUEST")
        self.register_event("logon_notify")
        self.register_event("connect")

        settings = self.bot.core("settings")
        settings.create(
            "Mail", "Max_life_read", "6_months", "How long should a read message be kept?",
            "1_week;2_weeks;1_month;6_months;1_year;2_years",
        )
        settings.create(
            "Mail", "Max_life_unread", "1_year", "How long should an unread message be kept?",
            "1_week;2_weeks;1_month;6_months;1_year;2_years",
        )

        prefs = self.bot.core("prefs")
        prefs.create(
            "Mail", "Life_read", "How long should a read message be kept?", "1_month",
            "1_week;2_weeks;1_month;6_months;1_year;2_years",
        )
        prefs.create(
            "Mail", "Life_unread", "How long should an unread message be kept?", "6_months",
            "1_week;2_weeks;1_month;6_months;1_year;2_years",
        )
        prefs.create(
            "Mail", "Logon_notification", "Do you want to be notified about new mail when you log on?",
            "Yes", "Yes;No",
        )

        self.help["description"] = "Module to send mail messages to other members of the bot."
        self.help["command"] = {
            "mail": "Shows a list of messages for you.",
            "mailed": "Shows a list of messages from you.",
            "mail send <name> <message>": "Send the mail <message> to player <name>",
        }
        self.help["notes"] = "Mail is delivered to any registered alt of the player <name>"

    # -- dispatch ---------------------------------------------------------------
    def command_handler(self, name, msg, origin):
        self.error.reset()
        parts = msg.split(" ", 3)
        com = parts[0] if len(parts) > 0 else ""
        sub = parts[1] if len(parts) > 1 else ""
        target = parts[2] if len(parts) > 2 else None
        message = parts[3] if len(parts) > 3 else None

        if _ucfirst(com) == "Mailed":
            return self.make_item_blob("Mailed list", self.mail_sent(name))

        sub_cf = _ucfirst(sub)
        if sub_cf == "Delete" and target is not None:
            return self.mail_delete(name, _php_intval(target))
        if sub_cf in ("", "Read", "Delete"):
            if target is not None:
                mid = _php_intval(target)
                return self.make_item_blob(f"Mail item {mid}", self.mail_read(name, mid))
            return self.make_item_blob("Mail list", self.mail_list(name))
        if sub_cf == "Send":
            return self.mail_send(name, target, message)

        self.error.set(f"Unknown sub command '##highlight##{sub}##end##'. ")
        return self.error.message()

    # -- re-declared so replies always go to a tell, never gc/pgmsg (we don't want
    # to leak mail contents to a public/group channel) ---------------------------
    def gc(self, name, msg) -> None:
        self.tell(name, msg)

    def pgmsg(self, name, msg) -> None:
        self.tell(name, msg)

    # -- logon notification (registered via register_event("logon_notify")) -------
    def notify(self, name, startup: bool = False) -> None:
        if not startup and bool(self.bot.core("prefs").get(name, "Mail", "Logon_notification")):
            mailbox = self.bot.core("alts").main(name)
            no_of_messages = self.new_mail_count(mailbox)
            if no_of_messages != 0:
                self.bot.send_tell(
                    name,
                    self.make_item_blob(
                        f"You've got ##error##{no_of_messages}##end## new messages.",
                        self.mail_list(name),
                    ),
                )

    def connect(self) -> None:
        self.start = time.time() + self.bot.crondelay

    def cron(self, duration=None) -> None:
        # TODO: Check for messages that are older than "max life" and discard
        # them. Never invoked -- see module docstring (register_event("cron",
        # ...) is commented out upstream too).
        pass

    # -- queries -----------------------------------------------------------------
    def new_mail_count(self, mailbox: str) -> int:
        result = self.bot.db.select(
            f"SELECT COUNT(id) AS no_of_messages FROM #___mail_message WHERE mailbox='{mailbox}' AND is_read=0",
            True,
        )
        if not result:
            return 0
        return result[0]["no_of_messages"]

    def mail_list(self, user: str) -> str:
        mailbox = self.bot.core("alts").main(user)
        window = f"##yellow##:::##end## Mail for ##highlight##{user}##end## ({mailbox}) ##yellow##:::##end##<br><br>"
        messages = self.bot.db.select(
            f"SELECT * FROM #___mail_message WHERE mailbox='{mailbox}' ORDER BY is_read, received DESC", True
        ) or []
        if not messages:
            return window + "No mail for you."
        tools = self.bot.core("tools")
        unread_header = False
        read_header = False
        for message in messages:
            body = _collapse_newlines(_stripslashes(base64.b64decode(message["message"]).decode("utf-8", "replace")), " ")
            is_read = bool(message["is_read"])
            if not is_read and not unread_header:
                window += "--- Unread messages ---<br>"
                unread_header = True
            if is_read and not read_header:
                window += "<br>--- Read messages ---<br>"
                read_header = True
            if len(body) > 23:
                body = body[:20] + "..."
            window += tools.chatcmd(f"mail delete {message['id']}", "[delete]") + " "
            window += f"{message['received']} "
            window += f"To: ##highlight##{message['recipient']}##end## "
            window += f"From: ##highlight##{message['sender']}##end##  ::: "
            window += tools.chatcmd(f"mail read {message['id']}", body) + "<br>"
        return window

    def mail_sent(self, user: str) -> str:
        window = f"##yellow##:::##end## Mail from ##highlight##{user}##end## ##yellow##:::##end##<br><br>"
        messages = self.bot.db.select(
            f"SELECT * FROM #___mail_message WHERE sender='{user}' ORDER BY id DESC", True
        ) or []
        if not messages:
            return window + "No mail from you."
        for message in messages:
            body = _collapse_newlines(_stripslashes(base64.b64decode(message["message"]).decode("utf-8", "replace")), " ")
            window += "(Unread) " if not message["is_read"] else "(Read) "
            if len(body) > 23:
                body = body[:20] + "..."
            window += f"{message['received']} "
            window += f"To: ##highlight##{message['recipient']}##end## "
            window += f"From: ##highlight##{message['sender']}##end##  ::: "
            window += body + "<br>"
        return window

    def mail_read(self, user: str, mail_id: int) -> str:
        mailbox = self.bot.core("alts").main(user)
        window = f"##yellow##:::##end## Mail for ##highlight##{user}##end## ({mailbox}) ##yellow##:::##end##<br><br>"
        messages = self.bot.db.select(
            f"SELECT * FROM #___mail_message WHERE id={mail_id} AND mailbox='{mailbox}'", True
        ) or []
        if not messages:
            return window + f"<br>Message {mail_id} was not found."
        message = messages[0]
        tools = self.bot.core("tools")
        window += f"##highlight##To:##end## {message['recipient']}<br>"
        window += f"##highlight##From:##end## {message['sender']}<br>"
        window += f"##highlight##Sent:##end## {message['received']}<br><br>"
        body = _collapse_newlines(_stripslashes(base64.b64decode(message["message"]).decode("utf-8", "replace")), "<br>")
        window += f"##normal##{body}##end##<br><br>"
        window += "[" + tools.chatcmd(f"mail delete {message['id']}", "delete") + "] "
        window += "[" + tools.chatcmd(
            f"mail send {message['sender']} The message you sent on {message['received']} has been read",
            "Notify sender",
        ) + "]"

        life_read = self.bot.core("prefs").get(user, "Mail", "Life_read")
        expires = _expires_at(life_read)
        self.bot.db.query(
            f"UPDATE #___mail_message SET is_read=true, expires='{expires.strftime('%Y-%m-%d %H:%M:%S')}' "
            f"WHERE id={mail_id} AND is_read=false"
        )
        return window

    def mail_send(self, sender: str, recipient: str, message: str):
        # sanitize_player()'s result is intentionally discarded -- see module
        # docstring for the faithfully-preserved PHP bug this reproduces.
        self.bot.core("tools").sanitize_player(recipient)
        mailbox = self.bot.core("alts").main(recipient)
        max_life_unread = self.bot.core("settings").get("Mail", "Max_life_unread")
        expires = _expires_at(max_life_unread)

        if not self.bot.core("security").check_access(recipient, "GUEST"):
            self.error.set(
                f"The recipient ({recipient}) is not a known member or guest of this bot. Please check spelling."
            )
            return self.error.message()
        if not message:
            return "There is no point in sending empty messages. Usage: <pre>mail send &lt;recipient&gt; &lt;message&gt;"

        db = self.bot.db
        mail_message = db.real_escape_string(message).replace("<", "&lt;")
        mail_message_b64 = base64.b64encode(mail_message.encode("utf-8")).decode("ascii")
        db.query(
            "INSERT INTO #___mail_message (mailbox, recipient, sender, message, expires) VALUES("
            f"'{mailbox}', '{recipient}', '{sender}', '{mail_message_b64}', "
            f"'{expires.strftime('%Y-%m-%d %H:%M:%S')}')"
        )

        chat = self.bot.core("chat")
        alts = list(self.bot.core("alts").get_alts(mailbox) or [])
        alts.append(mailbox)
        online = [alt for alt in alts if chat.buddy_exists(alt) and chat.buddy_online(alt)]
        for send_to in online:
            self.bot.send_tell(
                send_to,
                self.make_item_blob("You've just received a new message.", self.mail_list(send_to)),
            )
        return f"Message sent to {recipient} ({mailbox})."

    def mail_delete(self, name: str, mail_id: int):
        mailbox = self.bot.core("alts").main(name)
        existing = self.bot.db.select(
            f"SELECT id FROM #___mail_message WHERE id={mail_id} AND mailbox='{mailbox}'"
        )
        if not existing:
            self.error.set(f"Mail message '{mail_id}' was either not found or did not belong to {name}.")
            return self.error.message()
        self.bot.db.query(f"DELETE FROM #___mail_message WHERE id={mail_id} AND mailbox='{mailbox}'")
        return f"Mail {mail_id} has been deleted."

    # -- specialized make_blob to make ITEMREFs clickable --------------------------
    def make_item_blob(self, title: str, content: str) -> str:
        content = content.replace("<botname>", self.bot.botname)
        content = content.replace("<pre>", str(self.bot.commpre).replace("\\", ""))
        content = content.replace('"', "'")
        return f'<a href="text://{content}">{title}</a>'
