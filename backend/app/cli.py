"""Command-line admin tasks: ``python -m app.cli create-admin --email you@example.com``."""

import argparse
import asyncio
import getpass
import os
import sys

from app.auth.passwords import Argon2Hasher, PasswordPolicyError, validate_password
from app.config import get_settings
from app.db import create_client
from app.repositories import users
from app.repositories.users import EmailTakenError, UsersRepository


async def create_admin(email: str, password: str) -> str:
    """Create an admin, or promote the existing user with this email. Returns a status message."""
    settings = get_settings()
    client = create_client(settings.mongodb_uri)
    try:
        db = client[settings.mongodb_db]
        await users.install_indexes(db)
        repo = UsersRepository(db)
        try:
            await repo.create(email, Argon2Hasher().hash(password), role="admin")
        except EmailTakenError:
            existing = await repo.get_by_email(email)
            if existing is None:  # deleted between the two calls; extremely unlikely
                raise
            await repo.update(existing.id, "active", "admin")
            return f"{email.lower()} already existed and has been promoted to admin."
        return f"Admin {email.lower()} created."
    finally:
        await client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-admin", help="create (or promote) an admin user")
    admin.add_argument("--email", required=True)
    args = parser.parse_args(argv)

    password = os.environ.get("STOCKEYE_ADMIN_PASSWORD") or getpass.getpass("Password: ")
    try:
        validate_password(password, args.email)
    except PasswordPolicyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(asyncio.run(create_admin(args.email, password)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
