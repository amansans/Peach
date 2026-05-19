"""SQLAlchemy declarative base + shared mixins.

Every ORM model in `peach.db.models.*` inherits from `Base` here.  Centralising
the base in one module means:

1.  Alembic's autogenerate has a single `Base.metadata` to inspect.
2.  We can attach a project-wide naming convention so that every constraint
    (indexes, foreign keys, unique constraints) gets a deterministic name.
    Without a naming convention, Postgres generates random-looking names and
    Alembic produces fragile down-migrations.
3.  Shared mixins (timestamps, soft-delete if ever added) live next to the
    base where they're discoverable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

# ---------------------------------------------------------------------------
# Naming convention for constraints
# ---------------------------------------------------------------------------
# Each placeholder is filled in by SQLAlchemy at metadata-construction time:
#   %(table_name)s   — the table the constraint is on
#   %(column_0_name)s — the first column the constraint applies to
#   %(constraint_name)s — for ck/uq constraints, the developer-provided name
#   %(referred_table_name)s — for fk constraints
#
# The result is names like `ix_tickers_symbol`, `uq_users_username`,
# `fk_ticker_aliases_ticker_id_tickers` — predictable, greppable, and
# stable across `alembic revision --autogenerate` runs.
# ---------------------------------------------------------------------------
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Project-wide SQLAlchemy declarative base.

    Subclass this for every ORM model.  The shared `metadata` carries the
    naming convention above so that constraints have stable, predictable
    names across migrations.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # `__repr__` is rarely worth writing by hand on every model; this
    # auto-generated form shows the class name and primary key columns so
    # debugging logs and pytest failures are readable.  Subclasses can
    # override if they want a richer representation.
    def __repr__(self) -> str:  # pragma: no cover - cosmetic only
        # `primary_key` is a `PrimaryKeyConstraint`, which is iterable over
        # its Column members.  Iterating directly avoids mypy's confusion
        # about the `.columns` attribute on the SQLAlchemy 2.x types.
        pk_cols = [c.name for c in self.__table__.primary_key]
        pk_values = ", ".join(f"{c}={getattr(self, c, None)!r}" for c in pk_cols)
        return f"<{type(self).__name__} {pk_values}>"


class TimestampMixin:
    """Mixin adding `created_at` and `updated_at` columns to a model.

    `created_at` is set by Postgres on INSERT via `now()`.
    `updated_at` is set on INSERT *and* refreshed on every UPDATE via the
    SQLAlchemy `onupdate=func.now()` hook, which translates to a server-side
    expression so the value is sourced from the database clock rather than
    the application clock (avoids skew between hosts).

    Use as:
        class Foo(Base, TimestampMixin):
            ...

    Why not put these directly on `Base`?  Some tables (notably
    append-only fact tables like `fundamentals_facts`) don't need
    `updated_at` — rows are immutable once written.  Keeping the mixin
    optional lets each model opt in.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


def utcnow() -> datetime:
    """Return a tz-aware datetime representing the current UTC instant.

    Why not `datetime.utcnow()`?  As of Python 3.12, `utcnow()` returns a
    *naive* datetime, which silently produces wrong comparisons against
    tz-aware values.  Using `datetime.now(UTC)` makes the timezone explicit.

    Returns
    -------
    datetime
        A timezone-aware datetime with `tzinfo=UTC`.
    """
    return datetime.now(UTC)


# Re-export for convenience so `from peach.db.base import Base, TimestampMixin`
# is the single import most model modules need.
__all__: list[str] = ["Base", "TimestampMixin", "utcnow"]


# Type-narrowing alias used by some repository helpers; kept at the bottom
# of the module so subclasses defined elsewhere are still discoverable when
# this module is imported.
ModelT = Any
