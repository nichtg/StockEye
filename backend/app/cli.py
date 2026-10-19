"""Command-line admin tasks, run inside the VM's container (no sign-in needed).

- ``python -m app.cli create-admin --email you@example.com``: create or promote an admin.
- ``python -m app.cli refresh-discover``: rebuild the Discover lists now, in the foreground, and
  print how many rows each list got. Use it after a night when the lists came out empty.
"""

import argparse
import asyncio
import getpass
import os
import sys

from app.auth.passwords import PasswordPolicyError, validate_password
from app.config import get_settings
from app.db import create_client
from app.repositories import users
from app.services.accounts import AccountService
from app.services.container import build_services


async def create_admin(email: str, password: str) -> str:
    """Create an admin, or promote the existing user with this email. Returns a status message."""
    settings = get_settings()
    client = create_client(settings.mongodb_uri.get_secret_value())
    try:
        db = client[settings.mongodb_db]
        await users.install_indexes(db)
        accounts = AccountService(db, settings)
        user, created = await accounts.create_or_promote_admin(email, password)
        if created:
            return f"Admin {user.email} created."
        return f"{user.email} already existed and has been promoted to admin."
    finally:
        await client.close()


async def refresh_discover() -> list[tuple[str, int]]:
    """Run one Discover build with the app's own service wiring; (list id, row count) per list."""
    settings = get_settings()
    client = create_client(settings.mongodb_uri.get_secret_value())
    try:
        db = client[settings.mongodb_db]
        services = await build_services(settings, db)
        try:
            await services.discover.refresh()
            page = await services.discover.lists()
        finally:
            await services.aclose()
        return [(lst.id, len(lst.rows)) for lst in page.lists]
    finally:
        await client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-admin", help="create (or promote) an admin user")
    admin.add_argument("--email", required=True)
    sub.add_parser("refresh-discover", help="rebuild the Discover lists now and print row counts")
    args = parser.parse_args(argv)

    if args.command == "refresh-discover":
        for list_id, count in asyncio.run(refresh_discover()):
            print(f"{list_id}: {count} rows")
        return 0

    password = os.environ.get("STOCKEYE_ADMIN_PASSWORD") or getpass.getpass("Password: ")
    try:  # fail fast, before any database I/O; the account module re-checks as the real gate
        validate_password(password, args.email)
    except PasswordPolicyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(asyncio.run(create_admin(args.email, password)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
