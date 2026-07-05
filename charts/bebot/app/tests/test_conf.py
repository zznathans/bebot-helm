import pytest

from bebot.conf import load_bot_config


def write_conf(tmp_path, filename="bot_conf.py", **lines):
    path = tmp_path / filename
    body = "\n".join(f"{key} = {value!r}" for key, value in lines.items())
    path.write_text(body)
    return path


def test_load_bot_config_reads_defaults(tmp_path):
    write_conf(tmp_path, ao_username="acct", bot_name="mybot", dimension="5")
    config = load_bot_config(str(tmp_path))
    assert config.ao_username == "acct"
    assert config.bot_name == "mybot"
    assert config.log_format == "json"
    assert config.log_timestamp == "none"
    assert config.command_prefix == "!"


def test_load_bot_config_reads_overrides(tmp_path):
    write_conf(
        tmp_path,
        ao_username="acct",
        bot_name="mybot",
        dimension="5",
        log_format="text",
        command_prefix="#",
        guild_id=42,
    )
    config = load_bot_config(str(tmp_path))
    assert config.log_format == "text"
    assert config.command_prefix == "#"
    assert config.guild_id == 42


def test_load_bot_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_bot_config(str(tmp_path))


def test_load_bot_config_named_instance(tmp_path):
    write_conf(tmp_path, filename="pfs_bot_conf.py", ao_username="acct", bot_name="pfsbot", dimension="5")
    config = load_bot_config(str(tmp_path), "pfs")
    assert config.bot_name == "pfsbot"


def test_load_bot_config_falls_back_to_pw_file(tmp_path):
    write_conf(tmp_path, ao_username="acct", bot_name="mybot", dimension="5")
    (tmp_path / "pw").write_text("secretpassword\n")
    config = load_bot_config(str(tmp_path))
    assert config.ao_password == "secretpassword"


def test_load_bot_config_explicit_password_wins_over_pw_file(tmp_path):
    write_conf(tmp_path, ao_username="acct", bot_name="mybot", dimension="5", ao_password="inline")
    (tmp_path / "pw").write_text("frompwfile")
    config = load_bot_config(str(tmp_path))
    assert config.ao_password == "inline"


def test_server_and_port_resolve_from_dimension_alias(tmp_path):
    write_conf(tmp_path, ao_username="acct", bot_name="mybot", dimension="5")
    config = load_bot_config(str(tmp_path))
    assert config.resolved_dimension == "Rubi-Ka"
    assert config.server == "chat.d1.funcom.com"
    assert config.port == 7105


def test_resolved_dimension_passes_through_unknown_value(tmp_path):
    write_conf(tmp_path, ao_username="acct", bot_name="mybot", dimension="Rubi-Ka-2019")
    config = load_bot_config(str(tmp_path))
    assert config.resolved_dimension == "Rubi-Ka-2019"
