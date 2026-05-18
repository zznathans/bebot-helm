#!/usr/bin/env python3
# pylint: disable=invalid-name  # filename uses hyphens per CLI convention
"""
Generate GCP Secret Manager payloads for ao-bebot ExternalSecrets.

All chart credentials live in a single GCP secret as a flat JSON object with
plain-text values. Use the `secrets` subcommand to generate that payload.

Registry pull credentials are a separate GCP secret; use the `registry`
subcommand for those.

Usage:
  # Generate the main bebot-secrets payload and upload directly:
  python tools/generate-gcp-secret.py secrets --print-to-stdout | \\
    gcloud secrets versions add bebot-secrets --data-file=-

  # Generate registry pull credentials:
  python tools/generate-gcp-secret.py registry --print-to-stdout | \\
    gcloud secrets versions add bebot-regcred --data-file=-
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
    """Serialize payload and write to an explicit destination."""
    payload = json.dumps(data, indent=2)

    wrote_output = False
    if getattr(args, "output_file", None):
        with open(args.output_file, "w", encoding="utf-8") as out_f:
            out_f.write(payload)
            out_f.write("\n")
        wrote_output = True

    if getattr(args, "print_to_stdout", False):
        print(payload)
        wrote_output = True

    if not wrote_output:
        print(
            "Refusing to write sensitive payload to stdout by default. "
            "Use --output-file <path> or --print-to-stdout.",
            file=sys.stderr,
        )
        sys.exit(2)

    if args.secret_name:
        print(
            "\n# Upload with:\n"
            "#   <above command> | "
            "gcloud secrets versions add <SECRET_NAME> --data-file=-",
            file=sys.stderr,
        )


def section(title: str, description: str) -> None:
    """Print a formatted section header to stderr."""
    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"  {title}", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)
    print(f"  {description}", file=sys.stderr)
    print(f"{'=' * 60}\n", file=sys.stderr)


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_secrets(args: argparse.Namespace) -> None:
    """
    Consolidated bebot-secrets payload.

    Generates a single JSON object containing all credentials used by the chart.
    Keys are plain-text strings (no base64 encoding).

    Per-instance keys (one set per bot instance):
      <name>_ao_password, <name>_mariadb_user, <name>_mariadb_password,
      <name>_mariadb_database

    Shared MariaDB root keys:
      mariadb_root_user, mariadb_root_password

    Optional S3 backup keys (if using backup.s3.externalSecret.enabled: true):
      s3_access_key, s3_secret_key
    """
    data: dict = {}

    # --- Bot instances ---
    section(
        "Bot Instance Credentials",
        "Enter credentials for each bot instance (createSecret: false).\n"
        "  Enter a blank instance name when done.",
    )

    while True:
        name = input("Instance name (blank to finish): ").strip()
        if not name:
            break
        print(f"\n  Credentials for instance '{name}':", file=sys.stderr)
        data[f"{name}_ao_password"]      = prompt_secret(f"  [{name}] AO account password")
        data[f"{name}_mariadb_user"]     = prompt_value(f"  [{name}] MariaDB username")
        data[f"{name}_mariadb_password"] = prompt_secret(f"  [{name}] MariaDB password")
        data[f"{name}_mariadb_database"] = prompt_value(f"  [{name}] MariaDB database name")

    # --- MariaDB root ---
    section(
        "MariaDB Root Credentials",
        "Shared root credentials for the in-cluster MariaDB\n"
        "  (mariadb.createSecret: false).",
    )

    data["mariadb_root_user"]     = prompt_value("Root username", default="root")
    data["mariadb_root_password"] = prompt_secret("Root password")

    # --- S3 backup (optional) ---
    section(
        "S3 Backup Credentials (optional)",
        "Only needed when backup.s3.externalSecret.enabled: true.\n"
        "  Press Enter with no input to skip.",
    )

    include_s3 = input("Include S3 credentials? [y/N]: ").strip().lower()
    if include_s3 == "y":
        data["s3_access_key"] = prompt_value("Access key ID")
        data["s3_secret_key"] = prompt_secret("Secret access key")

    write_output(data, args)


def cmd_registry(args: argparse.Namespace) -> None:
    """
    Container registry pull credentials (separate GCP secret).

    Produces a GCP secret with a single 'dockerconfigjson' key whose value is
    the JSON docker config string. Reference it from extraObjects in values.yaml
    to create a kubernetes.io/dockerconfigjson pull secret.
    """
    section(
        "Container Registry Credentials",
        "Pull credentials for the bebot image registry.",
    )

    registry = prompt_value("Registry URL", default="ghcr.io")
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

    data = {
        "dockerconfigjson": json.dumps(docker_config),
    }

    write_output(data, args)


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

COMMANDS = {
    "secrets":  (cmd_secrets,  "All bebot credentials in one consolidated payload"),
    "registry": (cmd_registry, "Container registry pull credentials (dockerconfigjson)"),
}


def main() -> None:
    """Parse CLI arguments and dispatch to the appropriate subcommand handler."""
    parser = argparse.ArgumentParser(
        prog="generate-gcp-secret",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-s", "--secret-name",
        metavar="NAME",
        help="GCP secret name — used to print the matching gcloud upload command.",
    )
    parser.add_argument(
        "--print-to-stdout",
        action="store_true",
        default=False,
        help="Print the JSON payload to stdout instead of requiring --output-file.",
    )
    parser.add_argument(
        "-o", "--output-file",
        metavar="PATH",
        help="Write the JSON payload to this file instead of stdout.",
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
