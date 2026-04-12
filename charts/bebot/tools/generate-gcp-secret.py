#!/usr/bin/env python3
"""
Generate GCP Secret Manager payloads for ao-bebot ExternalSecrets.

Each subcommand corresponds to a secret type used by the chart. The output is
a JSON object that should be stored as the secret's value in GCP Secret Manager.
The ExternalSecret resources in the chart will pull individual properties from it.

Usage:
  # Print payload to stdout:
  python tools/generate-gcp-secret.py bot-config

  # Pipe directly to gcloud:
  python tools/generate-gcp-secret.py bot-config | \\
    gcloud secrets versions add ao-bebot-pfs --data-file=-

  # Save to file, then upload:
  python tools/generate-gcp-secret.py mariadb-root --output-file /tmp/secret.json
  gcloud secrets versions add ao-bebot-mariadb-root --data-file=/tmp/secret.json
"""

import argparse
import base64
import getpass
import json
import sys


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def prompt_value(label: str, default: str | None = None) -> str:
    """Prompt for a non-sensitive value, with optional default."""
    suffix = f" [{default}]" if default is not None else ""
    value = input(f"{label}{suffix}: ").strip()
    if not value:
        if default is not None:
            return default
        # Empty with no default — re-prompt
        return prompt_value(label, default)
    return value


def prompt_secret(label: str) -> str:
    """Prompt for a sensitive value using getpass (input not echoed)."""
    while True:
        value = getpass.getpass(f"{label}: ")
        if value:
            return value
        print("  Value cannot be empty, please try again.", file=sys.stderr)


def write_output(data: dict, args: argparse.Namespace) -> None:
    """Serialize payload and write to stdout or file."""
    payload = json.dumps(data, indent=2)

    if args.output_file:
        with open(args.output_file, "w") as fh:
            fh.write(payload + "\n")
        print(f"\nPayload written to: {args.output_file}", file=sys.stderr)
        if args.secret_name:
            print(
                f"\nUpload with:\n"
                f"  gcloud secrets versions add {args.secret_name} "
                f"--data-file={args.output_file}",
                file=sys.stderr,
            )
    else:
        print(payload)
        if args.secret_name:
            print(
                f"\n# Upload with:\n"
                f"#   <above command> | "
                f"gcloud secrets versions add {args.secret_name} --data-file=-",
                file=sys.stderr,
            )


def section(title: str, description: str) -> None:
    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"  {title}", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)
    print(f"  {description}", file=sys.stderr)
    print(f"{'=' * 60}\n", file=sys.stderr)


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_bot_config(args: argparse.Namespace) -> None:
    """
    Bot instance credentials.

    Used when an instance has createSecret: false.
    The chart ExternalSecret expects these keys:
      ao_password, mariadb_user, mariadb_password, mariadb_database, mariadb_host
    """
    section(
        "Bot Instance Config",
        "Credentials for a single bot instance (createSecret: false).",
    )

    data = {
        "ao_password":       prompt_secret("AO account password"),
        "mariadb_user":      prompt_value("MariaDB username"),
        "mariadb_password":  prompt_secret("MariaDB password"),
        "mariadb_database":  prompt_value("MariaDB database name"),
        "mariadb_host":      prompt_value("MariaDB host", default="bebot-mariadb"),
    }

    write_output(data, args)


def cmd_mariadb_root(args: argparse.Namespace) -> None:
    """
    MariaDB root credentials.

    Used when mariadb.createSecret: false.
    The chart ExternalSecret expects these keys:
      root-user, root-password
    """
    section(
        "MariaDB Root Credentials",
        "Root credentials for the in-cluster MariaDB (mariadb.createSecret: false).",
    )

    data = {
        "root-user":     prompt_value("Root username", default="root"),
        "root-password": prompt_secret("Root password"),
    }

    write_output(data, args)


def cmd_s3_credentials(args: argparse.Namespace) -> None:
    """
    S3 backup credentials.

    Used when backup.s3.externalSecret.enabled: true.
    The chart ExternalSecret expects these keys:
      access-key-id, secret-access-key
    """
    section(
        "S3 Backup Credentials",
        "AWS/S3-compatible credentials for the backup job (backup.s3.externalSecret.enabled: true).",
    )

    data = {
        "access-key-id":     prompt_value("Access key ID"),
        "secret-access-key": prompt_secret("Secret access key"),
    }

    write_output(data, args)


def cmd_registry(args: argparse.Namespace) -> None:
    """
    Container registry pull credentials.

    Produces a GCP secret with a single 'dockerconfigjson' key whose value is
    the JSON docker config string. The extraObjects ExternalSecret in values.yaml
    renders this into a kubernetes.io/dockerconfigjson secret.
    """
    section(
        "Container Registry Credentials",
        "Pull credentials for the bebot image registry (bebot-regcred ExternalSecret).",
    )

    registry = prompt_value(
        "Registry URL",
        default="gitlab-ca-tor-1.yeetbox.net:5050",
    )
    username = prompt_value("Username")
    password = prompt_secret("Password / access token")
    email    = prompt_value("Email (leave blank to omit)", default="")

    auth_b64 = base64.b64encode(f"{username}:{password}".encode()).decode()

    auth_entry: dict = {
        "username": username,
        "password": password,
        "auth":     auth_b64,
    }
    if email:
        auth_entry["email"] = email

    docker_config = {"auths": {registry: auth_entry}}

    # The ExternalSecret template references {{ .dockerconfigjson }}, so the
    # GCP secret must contain a 'dockerconfigjson' property whose value is the
    # raw docker config JSON string.
    data = {
        "dockerconfigjson": json.dumps(docker_config),
    }

    write_output(data, args)


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

COMMANDS = {
    "bot-config":    (cmd_bot_config,    "Bot instance credentials (ao_password, mariadb_*)"),
    "mariadb-root":  (cmd_mariadb_root,  "MariaDB root credentials (root-user, root-password)"),
    "s3-credentials":(cmd_s3_credentials,"S3 backup credentials (access-key-id, secret-access-key)"),
    "registry":      (cmd_registry,      "Container registry pull credentials (dockerconfigjson)"),
}


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="generate-gcp-secret",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-o", "--output-file",
        metavar="FILE",
        help="Write JSON payload to FILE instead of stdout.",
    )
    parser.add_argument(
        "-s", "--secret-name",
        metavar="NAME",
        help="GCP secret name — used to print the matching gcloud upload command.",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    for name, (_, help_text) in COMMANDS.items():
        subparsers.add_parser(name, help=help_text)

    args = parser.parse_args()

    try:
        COMMANDS[args.command][0](args)
    except KeyboardInterrupt:
        print("\n\nAborted.", file=sys.stderr)
        sys.exit(1)
    except EOFError:
        print("\n\nInput stream closed unexpectedly.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
