"""Unit tests for Wikipedia + issuer-CSV membership parsers."""

from __future__ import annotations

from pathlib import Path

from peach.ingestion.sources.issuer_csv_membership import (
    parse_invesco_csv,
    parse_ishares_csv,
)
from peach.ingestion.sources.wikipedia_membership import parse_constituent_table

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


# ---------------------------------------------------------------------------
# Wikipedia
# ---------------------------------------------------------------------------


def test_wikipedia_constituent_table_parses_canonical_html() -> None:
    html = (FIXTURES / "wikipedia_sp500_sample.html").read_text()
    rows = parse_constituent_table(html, "SP500")
    symbols = {r.ticker_symbol for r in rows}
    assert symbols == {"AAPL", "MSFT", "BRK.B"}
    # Every row stamps the requested index_code and the Wikipedia source.
    assert all(r.index_code == "SP500" for r in rows)
    assert all(r.source == "wikipedia" for r in rows)
    # Current-constituent rows have an open-ended period.
    assert all(r.valid_to is None for r in rows)


def test_wikipedia_with_no_constituent_table_returns_empty() -> None:
    """A page lacking a `wikitable` with a Symbol/Ticker column yields []."""
    html = "<html><body><p>Nothing useful here.</p></body></html>"
    assert parse_constituent_table(html, "SP500") == []


def test_wikipedia_footnote_marker_stripped_from_symbol() -> None:
    """Wikipedia sometimes annotates a constituent symbol with a footnote
    like ``GOOGL[a]``.  The parser must keep only the symbol portion.
    """
    html = """
    <html><body><table class="wikitable">
      <tr><th>Symbol</th><th>Security</th></tr>
      <tr><td>GOOGL[a]</td><td>Alphabet Inc. (Class A)</td></tr>
    </table></body></html>
    """
    rows = parse_constituent_table(html, "SP500")
    assert {r.ticker_symbol for r in rows} == {"GOOGL"}


# ---------------------------------------------------------------------------
# iShares
# ---------------------------------------------------------------------------


def test_ishares_csv_skips_metadata_and_cash() -> None:
    csv_text = (FIXTURES / "ishares_ivv_sample.csv").read_text()
    rows = parse_ishares_csv(csv_text, "SP500", "ishares_ivv")
    # USD cash row is dropped; the three equity rows survive.
    assert {r.ticker_symbol for r in rows} == {"AAPL", "MSFT", "NVDA"}
    assert all(r.source == "ishares_ivv" for r in rows)
    assert all(r.index_code == "SP500" for r in rows)


# ---------------------------------------------------------------------------
# Invesco
# ---------------------------------------------------------------------------


def test_invesco_csv_parses_common_and_class_a() -> None:
    csv_text = (FIXTURES / "invesco_qqq_sample.csv").read_text()
    rows = parse_invesco_csv(csv_text, "NDX", "invesco_qqq")
    # All four fixture rows are accepted share classes.
    assert {r.ticker_symbol for r in rows} == {"AAPL", "MSFT", "NVDA", "META"}
    assert all(r.source == "invesco_qqq" for r in rows)
    assert all(r.index_code == "NDX" for r in rows)


def test_invesco_csv_drops_unaccepted_share_classes() -> None:
    """Filter must reject preferred / warrant / non-equity rows."""
    csv_text = (
        "Fund Ticker,Holding Ticker,Class of Shares,Name\n"
        "QQQ,AAPL,COMMON,APPLE INC\n"
        "QQQ,XYZP,PREFERRED,SOME PREFERRED SHARE\n"
    )
    rows = parse_invesco_csv(csv_text, "NDX", "invesco_qqq")
    assert {r.ticker_symbol for r in rows} == {"AAPL"}
