"""ORM model package — one module per aggregate.

Each module exports SQLAlchemy ORM classes for a cohesive group of tables.
Importing this package re-exports the most-used models so callers can do::

    from peach.db.models import Ticker, User, Index

without remembering which submodule each lives in.

CRITICAL: every model module MUST be imported here so that Alembic's
autogenerate sees them via `Base.metadata`.  A model defined but never
imported will silently be invisible to migrations.
"""

from peach.db.models.auth import User
from peach.db.models.membership import IndexMembership
from peach.db.models.prices import CorporateAction, OHLCVDaily
from peach.db.models.reference import (
    Exchange,
    Index,
    Sector,
    Ticker,
    TickerAlias,
)

__all__: list[str] = [
    "CorporateAction",
    "Exchange",
    "Index",
    "IndexMembership",
    "OHLCVDaily",
    "Sector",
    "Ticker",
    "TickerAlias",
    "User",
]
