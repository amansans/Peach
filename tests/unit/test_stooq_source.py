"""Unit tests for the Stooq CSV parser.

Network is never touched — every test feeds the parser a string fixture
and asserts on the resulting ``ParsedOHLCV`` dataclasses.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from peach.ingestion.sources.stooq_source import parse_stooq_csv

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "stooq_aapl_sample.csv"


def test_parses_canonical_csv() -> None:
    rows = parse_stooq_csv(FIXTURE.read_text(), "AAPL")
    assert len(rows) == 5
    # First row matches the fixture line-for-line.
    first = rows[0]
    assert first.symbol == "AAPL"
    assert first.bar_date == date(2020, 1, 2)
    assert first.open == Decimal("74.06")
    assert first.close == Decimal("75.0875")
    # Stooq doesn't supply adj_close; the parser sets it equal to close.
    assert first.adj_close == first.close
    assert first.volume == Decimal("135480400")
    assert first.source == "stooq"


def test_no_data_marker_returns_empty_list() -> None:
    """Stooq's documented "No data" body must be silently swallowed.

    A returned empty list is the orchestrator's signal to fall back to
    yfinance — making this assertion explicit pins the contract.
    """
    assert parse_stooq_csv("No data", "ZZZZ") == []
    assert parse_stooq_csv("", "ZZZZ") == []


def test_blank_volume_row_is_dropped() -> None:
    """Rows with empty Volume (half-trading days) are skipped, not coerced.

    Inserting one would violate the ``ohlcv_daily.volume NOT NULL``
    constraint, so the parser pre-emptively drops them.
    """
    body = (
        "Date,Open,High,Low,Close,Volume\n"
        "2020-01-02,1,1,1,1,123\n"
        "2020-01-03,1,1,1,1,\n"  # blank volume
        "2020-01-06,1,1,1,1,456\n"
    )
    rows = parse_stooq_csv(body, "AAPL")
    assert {r.bar_date for r in rows} == {date(2020, 1, 2), date(2020, 1, 6)}


def test_malformed_row_skipped_not_raised() -> None:
    """A garbage row is logged-and-skipped, not raised.

    Test guards against a regression where a bad row in the middle of a
    5-year history aborts the whole symbol's ingest.
    """
    body = (
        "Date,Open,High,Low,Close,Volume\n"
        "2020-01-02,1,1,1,1,123\n"
        "GARBAGE-LINE,not,a,row,at,all\n"
        "2020-01-03,2,2,2,2,456\n"
    )
    rows = parse_stooq_csv(body, "AAPL")
    assert len(rows) == 2
