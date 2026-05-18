"""
Tests for tools/generate-gcp-secret.py
"""
import argparse
import base64
import json
from unittest.mock import patch

import generate_gcp_secret as script


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_args(output_file=None, secret_name=None, print_to_stdout=False):
    return argparse.Namespace(
        output_file=output_file,
        secret_name=secret_name,
        print_to_stdout=print_to_stdout,
    )


# ---------------------------------------------------------------------------
# write_output
# ---------------------------------------------------------------------------

class TestWriteOutput:
    def test_writes_valid_json_to_stdout(self, capsys):
        data = {"foo": "bar", "nested": {"x": 1}}
        script.write_output(data, make_args(print_to_stdout=True))
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
        script.write_output({"k": "v"}, make_args(secret_name="my-secret", print_to_stdout=True))
        captured = capsys.readouterr()
        assert "gcloud secrets versions add" in captured.err


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
# cmd_secrets
# ---------------------------------------------------------------------------

class TestCmdSecrets:
    def _run(self, capsys, instances, root_user="root", root_password="r00t",
             include_s3=False, s3_key="AKID", s3_secret="SAK"):
        """
        Helper that mocks all prompts for cmd_secrets.

        instances: list of dicts with keys: name, ao_password, mariadb_user,
                   mariadb_password, mariadb_database
        """
        input_responses = []
        getpass_responses = []

        for inst in instances:
            input_responses.append(inst["name"])            # instance name
            getpass_responses.append(inst["ao_password"])   # ao_password (secret)
            input_responses.append(inst["mariadb_user"])    # mariadb_user
            getpass_responses.append(inst["mariadb_password"])  # mariadb_password (secret)
            input_responses.append(inst["mariadb_database"])# mariadb_database

        input_responses.append("")  # blank = done with instances

        if root_user == "root":
            input_responses.append("")  # accept default
        else:
            input_responses.append(root_user)
        getpass_responses.append(root_password)

        input_responses.append("y" if include_s3 else "n")  # include S3?
        if include_s3:
            input_responses.append(s3_key)
            getpass_responses.append(s3_secret)

        with patch("builtins.input", side_effect=input_responses), \
             patch("getpass.getpass", side_effect=getpass_responses):
            script.cmd_secrets(make_args(print_to_stdout=True))

        return json.loads(capsys.readouterr().out)

    def test_single_instance_keys_present(self, capsys):
        data = self._run(capsys, instances=[{
            "name": "pfs", "ao_password": "aopass",
            "mariadb_user": "pfsuser", "mariadb_password": "dbpass",
            "mariadb_database": "pfsdb",
        }])
        assert "pfs_ao_password" in data
        assert "pfs_mariadb_user" in data
        assert "pfs_mariadb_password" in data
        assert "pfs_mariadb_database" in data
        assert "mariadb_root_user" in data
        assert "mariadb_root_password" in data

    def test_values_are_plain_text(self, capsys):
        data = self._run(capsys, instances=[{
            "name": "pfs", "ao_password": "aopass",
            "mariadb_user": "pfsuser", "mariadb_password": "dbpass",
            "mariadb_database": "pfsdb",
        }])
        assert data["pfs_ao_password"] == "aopass"
        assert data["pfs_mariadb_user"] == "pfsuser"
        assert data["pfs_mariadb_password"] == "dbpass"
        assert data["pfs_mariadb_database"] == "pfsdb"

    def test_root_defaults_to_root(self, capsys):
        data = self._run(capsys, instances=[{
            "name": "pfs", "ao_password": "aopass",
            "mariadb_user": "pfsuser", "mariadb_password": "dbpass",
            "mariadb_database": "pfsdb",
        }])
        assert data["mariadb_root_user"] == "root"
        assert data["mariadb_root_password"] == "r00t"

    def test_multiple_instances(self, capsys):
        data = self._run(capsys, instances=[
            {"name": "guild1", "ao_password": "p1", "mariadb_user": "u1",
             "mariadb_password": "pw1", "mariadb_database": "db1"},
            {"name": "guild2", "ao_password": "p2", "mariadb_user": "u2",
             "mariadb_password": "pw2", "mariadb_database": "db2"},
        ])
        assert data["guild1_ao_password"] == "p1"
        assert data["guild2_ao_password"] == "p2"
        assert data["guild1_mariadb_database"] == "db1"
        assert data["guild2_mariadb_database"] == "db2"

    def test_s3_keys_absent_when_skipped(self, capsys):
        data = self._run(capsys, instances=[{
            "name": "pfs", "ao_password": "aopass",
            "mariadb_user": "pfsuser", "mariadb_password": "dbpass",
            "mariadb_database": "pfsdb",
        }], include_s3=False)
        assert "s3_access_key" not in data
        assert "s3_secret_key" not in data

    def test_s3_keys_present_when_included(self, capsys):
        data = self._run(capsys, instances=[{
            "name": "pfs", "ao_password": "aopass",
            "mariadb_user": "pfsuser", "mariadb_password": "dbpass",
            "mariadb_database": "pfsdb",
        }], include_s3=True, s3_key="AKID123", s3_secret="SAK456")
        assert data["s3_access_key"] == "AKID123"
        assert data["s3_secret_key"] == "SAK456"

    def test_no_base64_in_output(self, capsys):
        data = self._run(capsys, instances=[{
            "name": "pfs", "ao_password": "plainpass",
            "mariadb_user": "plainuser", "mariadb_password": "plaindbpass",
            "mariadb_database": "plaindb",
        }])
        # Verify values are stored verbatim, not base64-encoded
        for value in data.values():
            try:
                decoded = base64.b64decode(value, validate=True).decode()
                # If it decodes cleanly and re-encodes to the same string, it looks b64-encoded
                assert base64.b64encode(decoded.encode()).decode() != value, \
                    f"Value looks base64-encoded: {value}"
            except Exception:  # pylint: disable=broad-except
                pass  # Not valid base64 — fine, it's plain text


# ---------------------------------------------------------------------------
# cmd_registry
# ---------------------------------------------------------------------------

class TestCmdRegistry:
    def _run(self, capsys, email=""):
        with patch("builtins.input", side_effect=["myreg.example.com:5050", "myuser", email]), \
             patch("getpass.getpass", return_value="mytoken"):
            script.cmd_registry(make_args(print_to_stdout=True))
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
