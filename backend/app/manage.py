"""Local administrative commands. Credentials never appear in arguments."""

import argparse
import asyncio
import getpass
import os
from pathlib import Path
import secrets

from sqlalchemy import func, select, text

from app.server import configure_event_loop
from app.secret_files import restrict_file
from app.config import load_settings
from app.contracts.core import UserCreate
from app.database import Database
from app.models import User
from app.security import hash_password


async def bootstrap(args):
    path = Path(args.generate_password_file).resolve() if args.generate_password_file else None
    password = (
        secrets.token_hex(24)
        if path
        else getpass.getpass("Administrator password (minimum 10 characters): ")
    )
    value = UserCreate(email=args.email, display_name=args.name, password=password, role="admin")
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        output = os.fdopen(descriptor, "w", encoding="utf-8")
        restrict_file(path)
    else:
        output = None
    database = Database(load_settings())
    created = False
    try:
        async with database.transaction() as session:
            await session.execute(text("SELECT pg_advisory_xact_lock(7310116)"))
            count = await session.scalar(
                select(func.count()).select_from(User).where(User.is_active, User.role == "admin")
            )
            if count:
                raise ValueError("An active administrator already exists")
            row = User(
                email=str(value.email).casefold(),
                display_name=value.display_name,
                timezone=value.timezone,
                role="admin",
                password_hash=hash_password(password),
            )
            session.add(row)
        created = True
        if output:
            with output:
                output.write(
                    f"Email: {value.email}\nPassword: {password}\nChange this password after the first login.\n"
                )
                output.flush()
                os.fsync(output.fileno())
        print("Administrator created:", value.email)
        if path:
            print("Initial credentials saved to:", path)
    finally:
        if output and not output.closed:
            output.close()
        if path and not created:
            path.unlink(missing_ok=True)
        await database.close()


def schema_sql(args):
    from alembic import command
    from alembic.config import Config

    backend = Path(__file__).resolve().parents[1]
    target = Path(args.output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as output:
        config = Config(str(backend / "alembic.ini"), output_buffer=output)
        config.set_main_option("script_location", str(backend / "alembic"))
        command.upgrade(config, "head", sql=True)
    print("Schema SQL exported:", target)


def main():
    configure_event_loop()
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    account = commands.add_parser("bootstrap-admin")
    account.add_argument("--email", required=True)
    account.add_argument("--name", default="Administrator")
    account.add_argument("--generate-password-file")
    schema = commands.add_parser("schema-sql")
    schema.add_argument("--output", default="database/schema.sql")
    args = parser.parse_args()
    if args.command == "bootstrap-admin":
        asyncio.run(bootstrap(args))
    else:
        schema_sql(args)


if __name__ == "__main__":
    main()
