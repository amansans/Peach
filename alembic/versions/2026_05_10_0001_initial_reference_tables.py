"""Initial reference tables: exchanges, sectors, indices, tickers, ticker_aliases, users.

Revision ID: 0001
Revises:
Create Date: 2026-05-10

This is the very first migration.  It creates every table the Phase 0
schema requires:

    * exchanges
    * sectors (self-referential GICS taxonomy)
    * indices
    * tickers (with company-age columns: founded_year, ipo_date, headquarters_country)
    * ticker_aliases
    * users (with the `user_role` Postgres ENUM)

The Postgres-side ENUM ``user_role`` is created explicitly so that the
downgrade path can drop it cleanly — relying on SQLAlchemy's implicit
auto-creation can leave the type orphaned in some Alembic versions.

This migration is written by hand rather than via autogenerate because
autogenerate has a few rough edges on a *first* migration (it sometimes
omits the naming convention until at least one table exists).  Subsequent
migrations should use ``alembic revision --autogenerate``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Postgres ENUM names
# ---------------------------------------------------------------------------
# We name the enum explicitly so the drop step in downgrade() can reference
# it by name.  Letting SQLAlchemy auto-name produces predictable but
# verbose names like `user_role_enum`; "user_role" is shorter and matches
# the column it serves.
# ---------------------------------------------------------------------------
USER_ROLE_ENUM_NAME = "user_role"


def upgrade() -> None:
    """Create every Phase 0 table.

    Order matters: a table that FKs to another must be created *after* its
    parent (Postgres validates FK targets at CREATE TABLE time).  Hence:
    exchanges → sectors → indices → tickers → ticker_aliases → users.
    """

    # -----------------------------------------------------------------------
    # exchanges
    # -----------------------------------------------------------------------
    op.create_table(
        "exchanges",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # MIC code.  8 chars is generous; real MICs are 4.
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_exchanges_code"),
    )
    op.create_index("ix_exchanges_code", "exchanges", ["code"])

    # -----------------------------------------------------------------------
    # sectors (self-referential GICS taxonomy)
    # -----------------------------------------------------------------------
    op.create_table(
        "sectors",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column(
            "parent_id",
            sa.Integer(),
            sa.ForeignKey("sectors.id", ondelete="CASCADE", name="fk_sectors_parent_id_sectors"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_sectors_code"),
        # CHECK constraint matches the model declaration.  The naming
        # convention (NAMING_CONVENTION["ck"]) prepends `ck_<table>_` so
        # we pass only the suffix here — passing the full name would
        # double-prefix it to `ck_sectors_ck_sectors_level_range`.
        sa.CheckConstraint("level BETWEEN 1 AND 4", name="level_range"),
    )
    op.create_index("ix_sectors_code", "sectors", ["code"])
    op.create_index("ix_sectors_parent_id", "sectors", ["parent_id"])

    # -----------------------------------------------------------------------
    # indices
    # -----------------------------------------------------------------------
    op.create_table(
        "indices",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_indices_code"),
    )
    op.create_index("ix_indices_code", "indices", ["code"])

    # -----------------------------------------------------------------------
    # tickers
    # -----------------------------------------------------------------------
    op.create_table(
        "tickers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column(
            "exchange_id",
            sa.Integer(),
            sa.ForeignKey("exchanges.id", ondelete="RESTRICT", name="fk_tickers_exchange_id_exchanges"),
            nullable=False,
        ),
        sa.Column(
            "sub_industry_id",
            sa.Integer(),
            sa.ForeignKey("sectors.id", ondelete="SET NULL", name="fk_tickers_sub_industry_id_sectors"),
            nullable=True,
        ),
        sa.Column("cik", sa.String(length=10), nullable=True),
        sa.Column("figi", sa.String(length=12), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("first_seen", sa.Date(), nullable=True),
        sa.Column("last_seen", sa.Date(), nullable=True),
        # Company-age columns — required for the Peer Comparison page.
        sa.Column("founded_year", sa.Integer(), nullable=True),
        sa.Column("ipo_date", sa.Date(), nullable=True),
        sa.Column("headquarters_country", sa.String(length=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("symbol", name="uq_tickers_symbol"),
    )
    op.create_index("ix_tickers_symbol", "tickers", ["symbol"])
    op.create_index("ix_tickers_exchange_id", "tickers", ["exchange_id"])
    op.create_index("ix_tickers_sub_industry_id", "tickers", ["sub_industry_id"])
    op.create_index("ix_tickers_cik", "tickers", ["cik"])

    # -----------------------------------------------------------------------
    # ticker_aliases
    # -----------------------------------------------------------------------
    op.create_table(
        "ticker_aliases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "ticker_id",
            sa.Integer(),
            sa.ForeignKey("tickers.id", ondelete="CASCADE", name="fk_ticker_aliases_ticker_id_tickers"),
            nullable=False,
        ),
        sa.Column("alias", sa.String(length=16), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("ticker_id", "alias", "valid_from", name="alias_per_ticker_period"),
    )
    op.create_index("ix_ticker_aliases_ticker_id", "ticker_aliases", ["ticker_id"])
    op.create_index("ix_ticker_aliases_alias", "ticker_aliases", ["alias"])

    # -----------------------------------------------------------------------
    # users
    # -----------------------------------------------------------------------
    # Create the Postgres ENUM via `postgresql.ENUM` with `create_type=False`
    # on the *column-level* use AND a separate `.create()` call.  This
    # gives us identical behavior across online and offline (--sql) modes
    # — `sa.Enum(create_type=False)` doesn't suppress the CREATE TYPE in
    # offline mode, causing duplicate DDL.
    user_role = postgresql.ENUM("admin", "user", name=USER_ROLE_ENUM_NAME, create_type=False)
    user_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.LargeBinary(), nullable=False),
        sa.Column("role", user_role, nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_username", "users", ["username"])


def downgrade() -> None:
    """Reverse of :func:`upgrade`.

    Tables are dropped in reverse FK-dependency order.  The ``user_role``
    ENUM is dropped last because it outlives the table that references it.
    """
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")

    # Drop the ENUM type now that no column references it.
    postgresql.ENUM(name=USER_ROLE_ENUM_NAME).drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_ticker_aliases_alias", table_name="ticker_aliases")
    op.drop_index("ix_ticker_aliases_ticker_id", table_name="ticker_aliases")
    op.drop_table("ticker_aliases")

    op.drop_index("ix_tickers_cik", table_name="tickers")
    op.drop_index("ix_tickers_sub_industry_id", table_name="tickers")
    op.drop_index("ix_tickers_exchange_id", table_name="tickers")
    op.drop_index("ix_tickers_symbol", table_name="tickers")
    op.drop_table("tickers")

    op.drop_index("ix_indices_code", table_name="indices")
    op.drop_table("indices")

    op.drop_index("ix_sectors_parent_id", table_name="sectors")
    op.drop_index("ix_sectors_code", table_name="sectors")
    op.drop_table("sectors")

    op.drop_index("ix_exchanges_code", table_name="exchanges")
    op.drop_table("exchanges")
