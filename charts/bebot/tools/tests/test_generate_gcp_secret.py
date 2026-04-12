"""
Tests for tools/generate-gcp-secret.py
"""
import argparse
import base64
import json
from pathlib import Path
from unittest.mock import patch

import generate_gcp_secret as script


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_args(output_file=None, secret_name=None):
    return argparse.Namespace(output_file=output_file, secret_name=secret_name)


# ---------------------------------------------------------------------------
# write_output
# ---------------------------------------------------------------------------

class TestWriteOutput:
    def test_writes_valid_json_to_stdout(self, capsys):
        data = {"foo": "bar", "nested": {"x": 1}}
        script.write_output(data, make_args())
        captured = capsys.readouterr()
        assert json.loads(captured.out) == data

    def test_writes_to_file(self, tmp_path):
        data = {"key": "value"}
        out_file = tmp_path / "secret.json"
        script.write_output(data, make_args(output_file=str(out_file)))
        assert json.loads(out_file.read_text()) == data

    def test_stdout_is_empty_when_writing_to_file(self, capsys, tmp_path):
        out_file = tmp_path / "secret.json"
        script.write_output({"k": "v"}, make_args(output_file=str(out_file)))
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_gcloud_hint_printed_to_stderr(self, capsys):
        script.write_output({"k": "v"}, make_args(secret_name="my-secret"))
        captured = capsys.readouterr()
        assert "my-secret" in captured.err


# ---------------------------------------------------------------------------
# prompt_value
# ---------------------------------------------------------------------------

class TestPromptValue:
    def test_returns_entered_value(self):
        with patch("builtins.input", return_value="hello"):
            assert script.prompt_value("Label") == "hello"

    def test_returns_default_on_empty_input(self):
        with patch("builtins.input", return_value=""):
            assert script.prompt_value("Label", default="fallback") == "fallback"

    def test_strips_whitespace(self):
        with patch("builtins.input", return_value="  trimmed  "):
            assert script.prompt_value("Label") == "trimmed"


# ---------------------------------------------------------------------------
# cmd_bot_config
# ---------------------------------------------------------------------------

class TestCmdBotConfig:
    def _run(self, capsys):
        # Prompt order: ao_password (secret), mariadb_user, mariadb_password (secret),
        #               mariadb_database, mariadb_host (has default)
        with patch("builtins.input", side_effect=["botuser", "botdb", ""]), \
             patch("getpass.getpass", side_effect=["aopass", "dbpass"]):
            script.cmd_bot_config(make_args())
        return json.loads(capsys.readouterr().out)

    def test_all_keys_present(self, capsys):
        data = self._run(capsys)
        assert set(data.keys()) == {
            "ao_password", "mariadb_user", "mariadb_password",
            "mariadb_database", "mariadb_host",
        }

    def test_values_populated(self, capsys):
        data = self._run(capsys)
        assert data["ao_password"] == "aopass"
        assert data["mariadb_user"] == "botuser"
        assert data["mariadb_password"] == "dbpass"
        assert data["mariadb_database"] == "botdb"

    def test_mariadb_host_defaults(self, capsys):
        data = self._run(capsys)
        assert data["mariadb_host"] == "bebot-mariadb"


# ---------------------------------------------------------------------------
# cmd_mariadb_root
# ---------------------------------------------------------------------------

class TestCmdMariadbRoot:
    def _run(self, capsys):
        # Prompt order: root-user (has default), root-password (secret)
        with patch("builtins.input", return_value=""), \
             patch("getpass.getpass", return_value="r00tpass"):
            script.cmd_mariadb_root(make_args())
        return json.loads(capsys.readouterr().out)

    def test_keys_present(self, capsys):
        data = self._run(capsys)
        assert set(data.keys()) == {"root-user", "root-password"}

    def test_root_user_defaults_to_root(self, capsys):
        data = self._run(capsys)
        assert data["root-user"] == "root"

    def test_root_password_value(self, capsys):
        data = self._run(capsys)
        assert data["root-password"] == "r00tpass"


# ---------------------------------------------------------------------------
# cmd_s3_credentials
# ---------------------------------------------------------------------------

class TestCmdS3Credentials:
    def _run(self, capsys):
        # Prompt order: access-key-id (value), secret-access-key (secret)
        with patch("builtins.input", return_value="AKIAIOSFODNN7EXAMPLE"), \
             patch("getpass.getpass", return_value="wJalrXUtnFEMI/K7MDENG"):
            script.cmd_s3_credentials(make_args())
        return json.loads(capsys.readouterr().out)

    def test_keys_present(self, capsys):
        data = self._run(capsys)
        assert set(data.keys()) == {"access-key-id", "secret-access-key"}

    def test_values(self, capsys):
        data = self._run(capsys)
        assert data["access-key-id"] == "AKIAIOSFODNN7EXAMPLE"
        assert data["secret-access-key"] == "wJalrXUtnFEMI/K7MDENG"


# ---------------------------------------------------------------------------
# cmd_registry
# ---------------------------------------------------------------------------

class TestCmdRegistry:
    def _run(self, capsys, email=""):
        # Prompt order: registry (has default), username, password (secret), email (has default)
        with patch("builtins.input", side_effect=["myreg.example.com:5050", "myuser", email]), \
             patch("getpass.getpass", return_value="mytoken"):
            script.cmd_registry(make_args())
        return json.loads(capsys.readouterr().out)

    def test_dockerconfigjson_key_present(self, capsys):
        data = self._run(capsys)
        assert "dockerconfigjson" in data

    def test_dockerconfigjson_is_valid_json(self, capsys):
        data = self._run(capsys)
        docker_cfg = json.loads(data["dockerconfigjson"])
        assert "auths" in docker_cfg

    def test_auth_base64_is_correct(self, capsys):
        data = self._run(capsys)
        docker_cfg = json.loads(data["dockerconfigjson"])
        registry_entry = docker_cfg["auths"]["myreg.example.com:5050"]
        expected_auth = base64.b64encode(b"myuser:mytoken").decode()
        assert registry_entry["auth"] == expected_auth

    def test_email_omitted_when_blank(self, capsys):
        data = self._run(capsys, email="")
        docker_cfg = json.loads(data["dockerconfigjson"])
        registry_entry = docker_cfg["auths"]["myreg.example.com:5050"]
        assert "email" not in registry_entry

    def test_email_included_when_provided(self, capsys):
        data = self._run(capsys, email="user@example.com")
        docker_cfg = json.loads(data["dockerconfigjson"])
        registry_entry = docker_cfg["auths"]["myreg.example.com:5050"]
        assert registry_entry["email"] == "user@example.com"
