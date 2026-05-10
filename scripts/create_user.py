"""Create (or update) a Peach user.

Usage
-----
    uv run python -m scripts.create_user --username alice --email alice@example.com
    uv run python -m scripts.create_user --username admin --email a@b.com --role admin
    make create-user username=alice email=alice@example.com

The script prompts for a password interactively — never accept passwords
on the command line because they leak into shell history and `ps` output.

Behavior
--------
* If the username does not exist, a new row is inserted.
* If the username already exists, the password and role are *updated*
  (useful for password resets in v1; in Phase 4 the API will own
  password-change flow).
* The password is bcrypt-hashed (cost factor 12) before storage.

Why bcrypt over argon2 or scrypt?
---------------------------------
bcrypt is well-understood, widely audited, has stable interop across
languages (handy if we ever introduce a non-Python service), and has
fewer parameter pitfalls than scrypt.  Argon2 is mathematically superior
but the Python bindings rotate more often.  For 2-5 users we don't need
the extra complexity.
"""

from __future__ import annotations

import getpass
import sys
from typing import Annotated

import bcrypt
import structlog
import typer
from sqlalchemy import select

from peach.db.models.auth import User, UserRole
from peach.db.session import session_scope

log = structlog.get_logger(__name__)

app = typer.Typer(add_completion=False, help=__doc__)


# bcrypt cost factor.  12 is the 2024-recommended minimum for an interactive
# login flow on commodity hardware — roughly ~250 ms per hash on a modern
# CPU.  Higher means slower logins but stronger resistance to offline
# brute force; 12 is a good balance for a small private app.
BCRYPT_ROUNDS = 12


def _prompt_password() -> bytes:
    """Prompt twice for a password, verifying both inputs match.

    Returns the password as raw bytes so it can be passed straight to
    bcrypt without an extra UTF-8 round-trip.

    Exits the process with an error message if the passwords don't match
    or if the password is suspiciously short (<8 chars).
    """
    pw1 = getpass.getpass("Password: ")
    pw2 = getpass.getpass("Password (again): ")

    if pw1 != pw2:
        typer.secho("Passwords do not match.", fg=typer.colors.RED, err=True)
        sys.exit(1)

    if len(pw1) < 8:
        # Not a hard policy — just a sanity floor.  Users who want a
        # stronger policy can ignore this and the Phase 4 API can enforce
        # something richer (e.g., zxcvbn score).
        typer.secho(
            "Password is shorter than 8 characters; please pick a longer one.",
            fg=typer.colors.RED,
            err=True,
        )
        sys.exit(1)

    return pw1.encode("utf-8")


def _hash_password(plaintext: bytes) -> bytes:
    """bcrypt-hash a plaintext password and return the resulting hash bytes.

    The bcrypt output embeds the salt and cost factor inline, so we store
    it as a single opaque blob.  Verification later uses
    ``bcrypt.checkpw(plaintext, stored_hash)`` — never decrypt; never
    compare with `==`.
    """
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(plaintext, salt)


@app.command()
def main(
    username: Annotated[
        str, typer.Option(..., "--username", "-u", help="Login name (lowercase, no spaces).")
    ],
    email: Annotated[str, typer.Option(..., "--email", "-e", help="Contact email address.")],
    role: Annotated[
        UserRole,
        typer.Option(
            "--role",
            "-r",
            help="Role to assign.  'admin' grants the safety-mode toggle and user-management privileges.",
            case_sensitive=False,
        ),
    ] = UserRole.USER,
) -> None:
    """Create a new user, or reset an existing one's password and role."""

    # Normalise username: lowercase + strip whitespace.  Doing this here
    # avoids subtle duplicates ("Alice" vs "alice") and matches the
    # convention the Phase 4 login endpoint will use.
    username = username.strip().lower()
    if not username or " " in username:
        typer.secho(
            "Username must be non-empty and contain no spaces.", fg=typer.colors.RED, err=True
        )
        sys.exit(1)

    plaintext = _prompt_password()
    password_hash = _hash_password(plaintext)

    with session_scope() as session:
        existing = session.scalars(select(User).where(User.username == username)).first()

        if existing is None:
            # New user.
            session.add(
                User(
                    username=username,
                    email=email,
                    password_hash=password_hash,
                    role=role,
                    is_active=True,
                )
            )
            action = "created"
        else:
            # Existing user — overwrite password + role, leave audit fields
            # like `last_login_at` untouched.  `is_active` is set to True
            # so this command also serves as an "unlock" for a deactivated
            # user.
            existing.password_hash = password_hash
            existing.role = role
            existing.email = email
            existing.is_active = True
            action = "updated"

    log.info("create_user.complete", username=username, role=role.value, action=action)
    typer.secho(f"User '{username}' {action} (role={role.value}).", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
