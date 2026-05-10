"""Environment-driven application configuration.

Single source of truth for every runtime setting that varies between
environments (local dev, Oracle Always-Free, Lightsail, CI).  Settings are
defined as a pydantic `BaseSettings` subclass; pydantic-settings populates
the fields from environment variables and, as a fallback, the `.env` file
in the project root.

Why this matters
----------------
1.  *Fail fast.*  If a required env var is missing or malformed, the process
    aborts at startup with a clear `ValidationError`, not silently at the
    first request that needs the value.

2.  *Single import boundary.*  Every module reads config via
    `get_settings()`; nothing reaches into `os.environ` directly.  This makes
    overriding settings in tests trivial (monkeypatch the cache) and keeps
    the env-var surface auditable.

3.  *Typed access.*  `settings.jwt_access_token_ttl_minutes` returns an
    `int`, not a `str` — pydantic coerces and validates at load time.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class SafetyMode(StrEnum):
    """Whether the screener / paper-trading pipeline can route real orders.

    `PAPER` is the only legal value for v1.  `LIVE` is included so that the
    type itself documents the future state space, but no code path that
    branches on `LIVE` is implemented — attempting to flip it produces a
    clear runtime error in `peach.paper_trading.runner` (Phase 9).
    """

    PAPER = "paper"
    LIVE = "live"


class LogLevel(StrEnum):
    """The standard library logging levels, redeclared as an enum so that
    pydantic validates env-var input rather than accepting arbitrary strings.
    """

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    """Top-level application settings.

    Field names are snake_case; env-var names are auto-derived as
    SCREAMING_SNAKE_CASE by the `case_sensitive=False` setting below.
    """

    # ----------------------------------------------------------------------
    # pydantic-settings configuration
    # ----------------------------------------------------------------------
    # `env_file=".env"` makes pydantic-settings read variables from `.env` in
    # the current working directory if they are not already present in the
    # process environment.  This matches the convention in `.env.example`.
    #
    # `extra="ignore"` means env vars we don't recognise are silently
    # ignored rather than triggering a ValidationError — important because
    # shells inject countless unrelated variables (PATH, HOME, LC_*).
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ----------------------------------------------------------------------
    # Database
    # ----------------------------------------------------------------------
    # The full SQLAlchemy-style URL.  Using psycopg 3 driver scheme
    # (`postgresql+psycopg`) — *not* `postgresql+psycopg2`, which is the v2
    # driver and behaves differently around async support.
    database_url: Annotated[
        str,
        Field(
            description="SQLAlchemy database URL for the primary Postgres instance.",
            examples=["postgresql+psycopg://peach:peach@localhost:5432/peach"],
        ),
    ]

    # ----------------------------------------------------------------------
    # JWT signing (used from Phase 4 onwards)
    # ----------------------------------------------------------------------
    # `SecretStr` prevents the value from leaking into logs / exception
    # tracebacks; access the raw value via `.get_secret_value()` when issuing
    # tokens.  The minimum length check guards against the obvious mistake
    # of leaving the placeholder from `.env.example`.
    jwt_secret_key: Annotated[
        SecretStr,
        Field(
            min_length=32,
            description="Secret used to sign access + refresh JWTs.  ≥32 chars.",
        ),
    ]

    # 15 minutes is short enough that a leaked access token has limited
    # damage potential; refresh tokens (longer-lived) handle UX.
    jwt_access_token_ttl_minutes: Annotated[
        int,
        Field(default=15, ge=1, le=24 * 60),
    ] = 15

    # 7 days strikes the balance: users don't re-auth every day, but a stolen
    # refresh token's window of usefulness is bounded.  When session
    # revocation is added (Phase 4+), shortening this gets even cheaper.
    jwt_refresh_token_ttl_days: Annotated[
        int,
        Field(default=7, ge=1, le=90),
    ] = 7

    # ----------------------------------------------------------------------
    # Data source credentials
    # ----------------------------------------------------------------------
    # SEC EDGAR requires identification in the User-Agent header.  Their
    # fair-use policy: https://www.sec.gov/os/accessing-edgar-data
    # If we omit or fake this, EDGAR may rate-limit or block us at the IP
    # level — and we have no recourse, since their policy is public.
    edgar_user_agent: Annotated[
        str,
        Field(
            default="Peach-Screener admin@example.com",
            description="User-Agent header to send on all EDGAR requests.",
        ),
    ] = "Peach-Screener admin@example.com"

    # FRED is free but requires an API key (one-time signup, no rate-limit
    # surprises).  Optional until Phase 10 (macro layer).
    fred_api_key: Annotated[
        SecretStr | None,
        Field(default=None, description="FRED API key.  Optional until Phase 10."),
    ] = None

    # Anthropic key — required only once Phase 11 (agents) lands.
    anthropic_api_key: Annotated[
        SecretStr | None,
        Field(default=None, description="Anthropic API key.  Optional until Phase 11."),
    ] = None

    # ----------------------------------------------------------------------
    # Application behavior
    # ----------------------------------------------------------------------
    safety_mode: Annotated[
        SafetyMode,
        Field(
            default=SafetyMode.PAPER,
            description="Whether the pipeline simulates fills (paper) or routes real orders (live, NOT supported in v1).",
        ),
    ] = SafetyMode.PAPER

    log_level: Annotated[
        LogLevel,
        Field(default=LogLevel.INFO, description="Root logger level."),
    ] = LogLevel.INFO


# ---------------------------------------------------------------------------
# Module-level accessor
# ---------------------------------------------------------------------------
# `lru_cache` ensures `.env` is read and validated exactly once per process,
# even when imported from many places.  Calling `get_settings.cache_clear()`
# in a test fixture allows monkeypatching env vars between test cases.
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide singleton Settings instance.

    Returns
    -------
    Settings
        A validated, immutable-ish snapshot of configuration.  The instance
        is cached for the lifetime of the process; to force a re-read after
        mutating env vars in tests, call ``get_settings.cache_clear()``.

    Raises
    ------
    pydantic.ValidationError
        If any required field is missing or any field's value fails
        validation (e.g. JWT secret shorter than 32 chars).
    """
    return Settings()  # type: ignore[call-arg]
