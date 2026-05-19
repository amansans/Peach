"""Authentication-related ORM models.

Phase 0 ships only the ``users`` table.  The corresponding API routes,
password verification, and JWT issuance arrive in Phase 4 — but having the
table from day one means:

* migration history starts clean (no awkward "add auth in Phase 4" migration
  that depends on every other table being already present);
* :class:`User` can be referenced as a foreign key from
  ``backtest_runs.triggered_by_user_id`` (Phase 7) and
  ``agent_runs.triggered_by_user_id`` (Phase 11) without a schema rework;
* the bootstrap script in :mod:`scripts.create_user` works end-to-end before
  the API is built, which de-risks Phase 4.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from peach.db.base import Base, TimestampMixin


class UserRole(StrEnum):
    """Application-level roles.

    Two roles are enough for v1:

    * ``ADMIN`` — can create users, trigger backtests, run agent verdicts,
      and toggle the safety-mode flag.
    * ``USER`` — can view screener output, run "deep dive" agent verdicts
      (bounded by cost), and request backtests.

    Permissions are checked at the FastAPI route layer (Phase 4); no role
    information ever influences which *data* a user sees, since data is
    shared across all users (per the approved plan).
    """

    ADMIN = "admin"
    USER = "user"


class User(Base, TimestampMixin):
    """An authenticated principal of the application.

    Password storage
    ----------------
    Passwords are hashed with bcrypt and stored as raw bytes in
    `password_hash`.  Using `LargeBinary` (rather than `String`) avoids any
    chance of accidental encoding/decoding issues — bcrypt outputs raw
    bytes that include the salt and cost parameter inline.

    We never store the plaintext password, not even briefly.  The
    `scripts.create_user` CLI prompts for the password interactively and
    passes the bcrypt-hashed value here.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Unique login identifier.  Lowercase-on-write is enforced at the
    # application layer (scripts + API routes) rather than via a generated
    # column — keeps the migration story simple.
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    # Email is collected for contact / future password-reset purposes.
    # Indexed but not unique — sharing an email across users isn't useful
    # but isn't harmful either, and enforcing uniqueness costs us nothing
    # to leave optional now.
    email: Mapped[str] = mapped_column(String(255), nullable=False)

    # bcrypt output (~60 bytes).  See module docstring for storage rationale.
    password_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # Role string is stored as a Postgres ENUM for clarity in pgadmin /
    # ad-hoc queries; SQLAlchemy handles the mapping to/from `UserRole`.
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=UserRole.USER,
    )

    # `is_active = False` revokes login without losing the row (preserves
    # audit trail / FK references from `backtest_runs.triggered_by_user_id`).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Set whenever a successful login issues a token (Phase 4).  Useful for
    # detecting dormant accounts.
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__: list[str] = ["User", "UserRole"]
