import json
import os
import time


class FakeDB:
    def __init__(self):
        self.queries: list[str] = []

    def real_escape_string(self, value: str) -> str:
        return value.replace("'", "\\'")

    def query(self, sql: str) -> bool:
        self.queries.append(sql)
        return True


def test_log_text_mode_format(bot, capsys):
    bot.log_format = "text"
    bot.log_timestamp = "none"
    bot.log("GROUP", "chat", "hello")
    out = capsys.readouterr().out
    assert out == "Testbot [GROUP]\t[chat]\thello\n"


def test_log_text_mode_sanitizes_message(bot, capsys):
    bot.log_format = "text"
    bot.log("GROUP", "chat", '<font color=#fff>hi</font> ##highlight##x##end## <a href="url">link</a>done</a>')
    out = capsys.readouterr().out
    assert "<font" not in out
    assert "</font>" not in out
    assert "[x]" in out
    assert "[link]" in out
    assert "done[/link]" in out


def test_log_json_mode_emits_valid_json(bot, capsys):
    bot.log_format = "json"
    bot.log("GROUP", "chat", "hello")
    out = capsys.readouterr().out
    record = json.loads(out)
    assert record["bot"] == "Testbot"
    assert record["first"] == "GROUP"
    assert record["second"] == "chat"
    assert record["message"] == "hello"
    time.strptime(record["timestamp"], "%Y-%m-%dT%H:%M:%SZ")


def test_log_json_mode_does_not_prefix_botname(bot, capsys):
    bot.log_format = "json"
    bot.log("GROUP", "chat", "hello")
    out = capsys.readouterr().out
    assert not out.startswith("Testbot ")


def test_log_security_channel_sends_to_gc_when_guildbot(bot, capsys):
    sent = []
    bot.guildbot = True
    bot.send_gc = lambda msg: sent.append(("gc", msg))
    bot.send_pgroup = lambda msg: sent.append(("pgroup", msg))
    bot.log("CORE", "security", "breach detected")
    capsys.readouterr()
    assert sent[0][0] == "gc"
    security_file = os.path.join(bot.log_path, "security.txt")
    with open(security_file) as fh:
        assert "breach detected" in fh.read()


def test_log_security_channel_sends_to_pgroup_when_not_guildbot(bot, capsys):
    sent = []
    bot.guildbot = False
    bot.send_gc = lambda msg: sent.append(("gc", msg))
    bot.send_pgroup = lambda msg: sent.append(("pgroup", msg))
    bot.log("CORE", "security", "breach detected")
    capsys.readouterr()
    assert sent[0][0] == "pgroup"


def test_log_mode_all_writes_dated_file_for_any_first(make_bot, capsys):
    bot = make_bot(log="all")
    bot.log("CORE", "debug", "anything")
    capsys.readouterr()
    dated_file = os.path.join(bot.log_path, f"{time.strftime('%Y-%m-%d', time.gmtime())}.txt")
    with open(dated_file) as fh:
        assert "anything" in fh.read()


def test_log_mode_chat_only_writes_for_chat_channels(make_bot, capsys):
    bot = make_bot(log="chat")
    bot.log("CORE", "debug", "should not be written")
    capsys.readouterr()
    dated_file = os.path.join(bot.log_path, f"{time.strftime('%Y-%m-%d', time.gmtime())}.txt")
    assert not os.path.exists(dated_file)

    bot.log("GROUP", "chat", "should be written")
    capsys.readouterr()
    with open(dated_file) as fh:
        assert "should be written" in fh.read()


def test_log_write_to_db_inserts_row(bot, capsys):
    fake_db = FakeDB()
    bot.db = fake_db
    bot.log("CORE", "debug", "logged to db", write_to_db=True)
    capsys.readouterr()
    assert len(fake_db.queries) == 1
    assert "INSERT INTO" in fake_db.queries[0]
    assert "logged to db" in fake_db.queries[0]


def test_log_write_to_db_truncates_long_messages(bot, capsys):
    fake_db = FakeDB()
    bot.db = fake_db
    bot.log("CORE", "debug", "x" * 600, write_to_db=True)
    capsys.readouterr()
    assert "x" * 500 in fake_db.queries[0]
    assert "x" * 501 not in fake_db.queries[0]
