"""Tests for the TSX/Canadian-listings additions.

Covers the small but load-bearing pieces:

* Stooq URL builder picks the right ``.us`` / ``.ca`` suffix and strips
  the ``.TO`` storage convention before forming the URL.
* Wikipedia parser appends ``.TO`` to TSX-listed symbols so the
  ``tickers.symbol`` unique constraint isn't blown up by US vs CA
  collisions (e.g., NYSE-listed RY vs TSX-listed RY).
* iShares Canada parser (XIU fixture) behaves the same as the US
  iShares parser but appends ``.TO`` to every emitted symbol.
"""

from __future__ import annotations

from pathlib import Path

from peach.ingestion.sources.issuer_csv_membership import (
    ISSUER_URLS,
    parse_ishares_csv,
)
from peach.ingestion.sources.stooq_source import _build_url
from peach.ingestion.sources.wikipedia_membership import (
    WIKIPEDIA_URLS,
    parse_constituent_table,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


# ---------------------------------------------------------------------------
# Stooq URL suffix
# ---------------------------------------------------------------------------


def test_stooq_url_default_us_suffix() -> None:
    """No ``country_code`` argument keeps the legacy ``.us`` behavior."""
    assert _build_url("AAPL") == "https://stooq.com/q/d/l/?s=aapl.us&i=d"


def test_stooq_url_canada_suffix_strips_to() -> None:
    """A Canadian ticker stored as ``RY.TO`` produces the URL ``ry.ca``.

    The Stooq URL form is the bare TSX ticker plus ``.ca``; the
    ``.TO`` suffix is our internal storage convention and must NOT
    leak into the URL.
    """
    assert _build_url("RY.TO", country_code="CA") == "https://stooq.com/q/d/l/?s=ry.ca&i=d"


def test_stooq_url_dot_in_symbol_becomes_hyphen() -> None:
    """BRK.B → brk-b.us — preserves Stooq's class-share convention."""
    assert _build_url("BRK.B") == "https://stooq.com/q/d/l/?s=brk-b.us&i=d"


# ---------------------------------------------------------------------------
# Wikipedia: TSX rows get .TO appended
# ---------------------------------------------------------------------------


def test_wikipedia_tsx60_appends_to_suffix() -> None:
    html = (FIXTURES / "wikipedia_tsx60_sample.html").read_text()
    rows = parse_constituent_table(html, "TSX60")
    symbols = {r.ticker_symbol for r in rows}
    assert symbols == {"RY.TO", "SHOP.TO", "CNR.TO"}
    assert all(r.index_code == "TSX60" for r in rows)


def test_wikipedia_sp500_does_not_append_to() -> None:
    """Sanity: the US path is untouched by the TSX change."""
    html = (FIXTURES / "wikipedia_sp500_sample.html").read_text()
    rows = parse_constituent_table(html, "SP500")
    symbols = {r.ticker_symbol for r in rows}
    # AAPL must stay AAPL, NOT AAPL.TO.
    assert "AAPL" in symbols
    assert "AAPL.TO" not in symbols


# ---------------------------------------------------------------------------
# iShares Canada (XIU)
# ---------------------------------------------------------------------------


def test_ishares_xiu_appends_to_and_drops_cash() -> None:
    csv_text = (FIXTURES / "ishares_xiu_sample.csv").read_text()
    rows = parse_ishares_csv(csv_text, "TSX60", "ishares_xiu", country_code="CA")
    symbols = {r.ticker_symbol for r in rows}
    assert symbols == {"RY.TO", "SHOP.TO", "CNR.TO"}  # CAD cash row dropped
    assert all(r.source == "ishares_xiu" for r in rows)


def test_ishares_us_branch_untouched_by_country_arg() -> None:
    """Passing ``country_code='US'`` keeps the existing US semantics."""
    csv_text = (FIXTURES / "ishares_ivv_sample.csv").read_text()
    rows = parse_ishares_csv(csv_text, "SP500", "ishares_ivv", country_code="US")
    symbols = {r.ticker_symbol for r in rows}
    assert "AAPL" in symbols
    assert "AAPL.TO" not in symbols


# ---------------------------------------------------------------------------
# ISSUER_URLS contract
# ---------------------------------------------------------------------------


def test_issuer_urls_cover_all_five_indices() -> None:
    """The orchestrator depends on the issuer URL table covering every
    index named in ``daily_eod.TRACKED_INDICES``.  This is a contract
    test — if either side changes, this catches the drift.
    """
    from peach.scheduling.daily_eod import TRACKED_INDICES

    assert set(ISSUER_URLS.keys()) == set(TRACKED_INDICES)
    assert set(WIKIPEDIA_URLS.keys()) == set(TRACKED_INDICES)
    # Every entry must carry its country code so the parser can decide
    # whether to append `.TO`.
    for code, (_, _, country) in ISSUER_URLS.items():
        assert country in {"US", "CA"}, code
