"""Ingestion building blocks: ``ParsedRow`` types, ``DataSource`` ABC, retry policy.

Every concrete source in :mod:`peach.ingestion.sources` produces typed
records of one of these shapes.  Keeping the parser→writer interface
explicit and typed makes it trivial to:

1.  Unit-test parsers against committed fixtures (no DB, no network).
2.  Swap sources without touching the writer.
3.  Have mypy enforce that a new source produces a valid row shape.

Why dataclasses, not pydantic
-----------------------------
These are internal data-transfer objects between parsing and writing —
no JSON serialisation, no env-file loading, no third-party schema needs
them.  Dataclasses are zero-cost and play more nicely with mypy strict.
"""

from __future__ import annotations

import abc
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

# ---------------------------------------------------------------------------
# Parsed-row dataclasses — the contract between parsers and writers
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ParsedOHLCV:
    """A single daily bar emitted by a price source.

    All fields are required.  Sources that natively lack ``adj_close``
    (Stooq) should set it equal to ``close`` — Phase 5+ corporate-action
    ingestion recomputes the true adjusted value.
    """

    symbol: str
    bar_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adj_close: Decimal
    volume: Decimal
    # Name of the source that produced this row (`stooq`, `yfinance`,
    # `yfinance_gapfill`).  Writer copies this verbatim into
    # ``ohlcv_daily.source`` so origin is recoverable from a query.
    source: str


@dataclass(frozen=True, slots=True)
class ParsedMembership:
    """A single (index, ticker, period) membership record.

    For sources that emit only the *current* constituents (Wikipedia
    article HTML, issuer holdings CSVs), ``valid_to`` is left ``None`` —
    the writer treats this as "still a member as of today".  Sources that
    parse historical revision data set ``valid_to`` explicitly.
    """

    index_code: str
    ticker_symbol: str
    valid_from: date
    valid_to: date | None
    source: str


@dataclass(frozen=True, slots=True)
class ParsedCorporateAction:
    """A single corporate-action event.  Not used until Phase 2 indicators
    need accurate split adjustment, but defining the shape here keeps the
    interface complete.
    """

    symbol: str
    action_date: date
    kind: str  # one of: "split", "dividend", "spinoff"
    ratio: Decimal
    cash_amount: Decimal | None
    source: str


# ---------------------------------------------------------------------------
# DataSource ABC
# ---------------------------------------------------------------------------


class DataSource(abc.ABC):
    """Abstract base for any external-data adapter.

    Concrete subclasses live in :mod:`peach.ingestion.sources` and each
    typically implement *one* of the ``fetch_*`` shapes below.  An
    implementation that doesn't make sense for a given source simply
    raises :class:`NotImplementedError` — there is no `Protocol` because
    these methods are intrinsically polymorphic in their return type.
    """

    #: Human-readable label used in logs and the `source` columns of the
    #: tables that store rows from this adapter.  Must be stable across
    #: releases — changing it makes historical rows look like they came
    #: from a different vendor.
    NAME: str = ""

    @abc.abstractmethod
    def __init__(self) -> None:  # pragma: no cover - interface only
        ...

    def fetch_ohlcv(self, symbol: str, start: date, end: date) -> Iterable[ParsedOHLCV]:
        """Yield bars for ``symbol`` in the inclusive ``[start, end]`` window."""
        raise NotImplementedError

    def fetch_current_members(self, index_code: str) -> Iterable[ParsedMembership]:
        """Yield current-as-of-today members of ``index_code``."""
        raise NotImplementedError

    def fetch_corporate_actions(
        self, symbol: str, start: date, end: date
    ) -> Iterable[ParsedCorporateAction]:
        """Yield split/dividend/spinoff actions in the window."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Shared retry policy
# ---------------------------------------------------------------------------
#
# Every outbound network call is wrapped by this decorator (or an
# equivalent tenacity invocation) so transient network blips never abort
# a 530-ticker batch.  Parameters:
#
# * ``stop_after_attempt(5)`` — retry up to 5 times.  At a default
#   ~2s base with exponential backoff this is roughly a 1-minute envelope.
# * ``wait_random_exponential(min=1, max=30)`` — jittered backoff so a
#   batch of concurrent requests doesn't synchronously retry into the same
#   transient outage.
# * ``retry_if_exception_type((NetworkError,))`` — only retry on errors
#   we know are transient.  Schema errors, 4xx responses, and parser
#   exceptions raise immediately.
#
# Sources adopt the decorator like::
#
#     @network_retry
#     def _fetch(...) -> bytes:
#         ...
#


class NetworkError(Exception):
    """Marker exception for network-layer failures that should be retried.

    Sources should catch httpx exceptions, log them with structlog, and
    re-raise as ``NetworkError`` so the retry decorator picks them up
    while leaving non-network exceptions (e.g., bad CSV format) to
    propagate untouched.
    """


def network_retry[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """Decorator: retry transient network failures with jittered backoff.

    Wraps tenacity so callers don't have to know its argument shape.
    The decorated function should raise :class:`NetworkError` on
    retriable failures; any other exception bypasses retry.

    The ``ParamSpec`` typing means decorated functions keep their precise
    parameter list as seen by mypy / IDE completion.
    """
    decorated: Callable[P, R] = retry(
        stop=stop_after_attempt(5),
        wait=wait_random_exponential(min=1, max=30),
        retry=retry_if_exception_type(NetworkError),
        reraise=True,
    )(func)
    return decorated


__all__: list[str] = [
    "DataSource",
    "NetworkError",
    "ParsedCorporateAction",
    "ParsedMembership",
    "ParsedOHLCV",
    "network_retry",
]
