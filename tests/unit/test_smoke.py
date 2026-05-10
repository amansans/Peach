"""Smoke tests — verify the package imports cleanly and core invariants hold.

These tests intentionally avoid touching the database.  The goal is fast
feedback that the import graph is healthy, settings validation works for
sensible inputs, and the model metadata registers every expected table.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from peach.config.settings import Settings
from peach.db.base import Base
from peach.db.models import (
    Exchange,
    Index,
    Sector,
    Ticker,
    TickerAlias,
    User,
)
from peach.db.models.auth import UserRole


def test_package_imports() -> None:
    """The top-level peach package imports without side effects.

    A failure here usually means a circular import was introduced.
    """
    import peach  # the import itself is the test

    assert peach.__version__


def test_all_models_registered_with_metadata() -> None:
    """Every Phase 0 model must appear in `Base.metadata`.

    This guards against the failure mode where a model module is created
    but never imported — autogenerate would silently skip the new table.
    The `peach.db.models.__init__` re-export is the canonical safeguard;
    this test pins the invariant.
    """
    expected_tables = {
        "exchanges",
        "sectors",
        "indices",
        "tickers",
        "ticker_aliases",
        "users",
    }
    actual_tables = set(Base.metadata.tables.keys())
    missing = expected_tables - actual_tables
    assert not missing, f"Models defined but not registered with metadata: {missing}"


def test_settings_rejects_short_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pydantic must reject a JWT secret shorter than 32 characters.

    Validating this here means we don't have to wait for Phase 4 to find
    out that the validation rule actually fires.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
    monkeypatch.setenv("JWT_SECRET_KEY", "too-short")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_settings_accepts_full_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pydantic accepts a well-formed configuration and exposes typed fields."""
    # The DB URL uses a placeholder hostname / creds — irrelevant for this
    # test since we never open a connection.  A distinctive token in the
    # secret (`SECRET-LEAK-CANARY`) lets us prove SecretStr masks it from
    # repr without false positives from the DB URL.
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://dbuser:dbpass@localhost/db")
    monkeypatch.setenv("JWT_SECRET_KEY", "SECRET-LEAK-CANARY-" + "z" * 32)
    monkeypatch.setenv("JWT_ACCESS_TOKEN_TTL_MINUTES", "30")
    s = Settings()  # type: ignore[call-arg]
    assert s.jwt_access_token_ttl_minutes == 30
    # SecretStr keeps the value out of __repr__; this guards against an
    # accidental switch back to plain str.
    assert "SECRET-LEAK-CANARY" not in repr(s)
    # But the underlying value is still accessible via get_secret_value().
    assert "SECRET-LEAK-CANARY" in s.jwt_secret_key.get_secret_value()


def test_user_role_enum_values() -> None:
    """The user-role enum's string values are stable.

    They're stored in the Postgres ``user_role`` ENUM type — changing them
    requires a migration, so this test exists to make accidental renames
    show up in CI rather than at runtime.
    """
    assert UserRole.ADMIN.value == "admin"
    assert UserRole.USER.value == "user"


def test_model_repr_is_safe() -> None:
    """Models' auto-generated repr handles a partially-built instance.

    A model that hasn't yet been flushed has `id=None`; the repr must not
    raise.  This guards against the next developer overriding `__repr__`
    in a way that explodes during pdb sessions.
    """
    t = Ticker(symbol="AAPL", name="Apple Inc.", exchange_id=1)
    # The exact format isn't important — only that it does not throw.
    repr(t)
    # And that the class names are reachable for the rest of the test
    # suite without import errors.
    assert Exchange.__name__ == "Exchange"
    assert Sector.__name__ == "Sector"
    assert Index.__name__ == "Index"
    assert TickerAlias.__name__ == "TickerAlias"
    assert User.__name__ == "User"
