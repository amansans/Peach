"""Database engine + session factory.

A single Engine is created lazily at first use and kept alive for the
process lifetime.  Session usage in application code goes through one of
two paths:

1.  ``with session_scope() as session: ...`` — the canonical pattern for
    scripts, background jobs, and CLI commands.  Commits on success, rolls
    back on exception, always closes.

2.  FastAPI dependency ``get_db()`` (defined in `peach.api.deps`) — wraps
    the same machinery in a generator that FastAPI auto-closes after each
    request.

Why one engine, many sessions?
------------------------------
SQLAlchemy's Engine maintains a connection pool.  Creating multiple engines
fragments that pool and confuses idle-connection accounting on the Postgres
side.  Conversely, sessions are cheap, short-lived objects that wrap a
single unit-of-work.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from peach.config.settings import get_settings


# ---------------------------------------------------------------------------
# Engine factory
# ---------------------------------------------------------------------------
# `lru_cache` makes this a singleton.  We do NOT import the engine at module
# top level because:
#   - importing this module should be side-effect-free (no DB connection)
#   - tests can monkeypatch the settings before the first call
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return the process-wide SQLAlchemy Engine.

    Pool settings (`pool_size=5`, `max_overflow=5`) are conservative — this
    is a low-traffic, single-VM deployment.  With 2-5 users and a nightly
    EOD job, we will never legitimately need more than a handful of
    concurrent connections.  Postgres' default `max_connections=100` gives
    us plenty of headroom.

    Returns
    -------
    sqlalchemy.Engine
        Lazily-constructed singleton.
    """
    settings = get_settings()
    return create_engine(
        settings.database_url,
        # `future=True` is redundant in SQLAlchemy 2.x (always-on) but kept
        # explicit to communicate intent.
        future=True,
        # `pool_pre_ping=True` issues a cheap `SELECT 1` before handing out
        # a pooled connection.  Adds ~1ms per checkout but avoids the
        # classic "stale connection after DB restart" failure mode.
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        # `echo=False` — turn this on locally if you need to see every
        # generated SQL statement.  Production stays quiet; the structlog
        # logger captures what we care about.
        echo=False,
    )


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
# `sessionmaker(...)` returns a configured class whose instances are
# Sessions bound to our engine.  By convention we call it `SessionLocal`
# (matches FastAPI tutorial conventions and is widely searchable).
# `expire_on_commit=False` keeps ORM attribute access valid after commit;
# without it, accessing `obj.id` post-commit triggers an implicit refresh
# query, which is surprising and slow in batch jobs.
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of ORM operations.

    Usage
    -----
        with session_scope() as session:
            session.add(some_model)
            # commit happens automatically on context exit if no exception

    Behavior
    --------
    * Commits the transaction if the block exits without exception.
    * Rolls back if any exception escapes the block, then re-raises.
    * Always closes the session (returning the connection to the pool).

    Yields
    ------
    sqlalchemy.orm.Session
        A fresh session.  Do NOT share across threads or async tasks.
    """
    session = _session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        # Rolling back here means the caller never has to remember to clean
        # up after a failure.  The exception is re-raised so the caller's
        # own error handling still runs.
        session.rollback()
        raise
    finally:
        session.close()


__all__: list[str] = ["get_engine", "session_scope"]
