"""Add country_code to exchanges and indices for the US/CA filter.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-11

The user-facing reason: the screener needs a clean US-vs-Canadian
filter.  The architectural choice (per the approved plan) is to filter
*by listing exchange*, which means the data lives on ``exchanges`` and
the join is unambiguous.

We also add ``country_code`` to ``indices`` because every TSX index we
add (TSX60, TSXC) needs to know which exchange to attach newly-
discovered ticker stubs to — XNAS is the placeholder for US indices,
XTSE for Canadian.

Backfill strategy
-----------------
* Both columns are added NOT NULL with a server default of ``'US'``,
  then the server default is dropped immediately so future rows must
  be explicit.  This makes the upgrade safe on the existing database
  (which has only US rows up to now) without leaving a permissive
  default in place.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add country_code columns and backfill them for the existing rows."""

    # -----------------------------------------------------------------------
    # exchanges.country_code
    # -----------------------------------------------------------------------
    # Add NOT NULL with a transitional server_default of 'US' so the
    # backfill on existing rows is automatic.  Drop the default after,
    # so future inserts must specify the value explicitly.
    op.add_column(
        "exchanges",
        sa.Column("country_code", sa.String(length=2), nullable=False, server_default="US"),
    )
    op.alter_column("exchanges", "country_code", server_default=None)
    op.create_index("ix_exchanges_country_code", "exchanges", ["country_code"])

    # -----------------------------------------------------------------------
    # indices.country_code
    # -----------------------------------------------------------------------
    op.add_column(
        "indices",
        sa.Column("country_code", sa.String(length=2), nullable=False, server_default="US"),
    )
    op.alter_column("indices", "country_code", server_default=None)
    op.create_index("ix_indices_country_code", "indices", ["country_code"])


def downgrade() -> None:
    """Drop the two new columns and their indices."""
    op.drop_index("ix_indices_country_code", table_name="indices")
    op.drop_column("indices", "country_code")

    op.drop_index("ix_exchanges_country_code", table_name="exchanges")
    op.drop_column("exchanges", "country_code")
