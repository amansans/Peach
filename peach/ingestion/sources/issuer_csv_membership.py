"""Issuer-ETF daily-holdings membership loader.

This is the most reliable source of *current* constituents.  Each issuer
publishes a CSV containing every holding their ETF has on close of the
prior trading day.  We use:

* **iShares IVV** for SP500       — ``https://www.ishares.com/.../IVV/...``
* **Invesco  QQQ** for Nasdaq-100 — ``https://www.invesco.com/.../qqq/...``
* **iShares DIA** for DJI         — ``https://www.ishares.com/.../DIA/...``

Why issuer CSVs rather than (only) Wikipedia
--------------------------------------------
* Issuer CSVs are *machine-published* — no HTML-shape fragility.
* They update *daily* — Wikipedia lags by hours to days.
* They include cash + derivative rows we filter out, but those are
  flagged in a consistent column.

The two issuers use slightly different CSV shapes:

* **iShares** prepends 4-6 metadata header rows (fund name, "Fund Holdings
  as of", inception date, shares outstanding, blank line) before the real
  header row.  Equity holdings have ``Asset Class = "Equity"``; cash and
  derivatives have other values.
* **Invesco** has no metadata preamble — the header row is the first
  line.  Equity-only filter is on ``Class of Shares`` (we keep COMMON
  and CLASS A through CLASS C).

Both parsers normalise to ``ParsedMembership`` records.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import date

import structlog

from peach.db.base import utcnow
from peach.ingestion.base import DataSource, ParsedMembership
from peach.ingestion.http import fetch_bytes

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# iShares (IVV, DIA)
# ---------------------------------------------------------------------------


def _find_header_row(lines: list[str]) -> int:
    """Return the index of the first line in ``lines`` that looks like the
    iShares CSV header — i.e., contains ``Ticker`` as a quoted column.

    The metadata preamble is variable in length across iShares funds
    (between 4 and 7 lines), so we scan rather than fixed-offset.
    """
    for idx, line in enumerate(lines):
        if '"Ticker"' in line:
            return idx
    raise ValueError("iShares CSV: header row containing 'Ticker' not found")


def parse_ishares_csv(
    content: str,
    index_code: str,
    source_name: str,
    country_code: str = "US",
) -> list[ParsedMembership]:
    """Parse an iShares daily-holdings CSV.

    Parameters
    ----------
    content
        Raw CSV text.
    index_code
        Peach index code for the resulting rows (``SP500`` / ``DJI`` /
        ``TSX60`` / ``TSXC``).
    source_name
        Source-attribution string — distinct values per fund so we can
        audit which ETF a row came from.
    country_code
        Listing country of the fund.  ``"CA"`` means the symbols in the
        CSV are TSX tickers and need a ``.TO`` suffix appended so they
        don't collide with same-named US tickers in our DB.

    Returns
    -------
    list[ParsedMembership]
        One row per ``Asset Class = "Equity"`` holding.  Cash and
        derivative rows are dropped.
    """
    # iShares CSVs are CRLF; split on universal newline and find the real
    # header line.  We can't use pandas.read_csv with skiprows because
    # the preamble line count varies across funds.
    lines = content.splitlines()
    header_idx = _find_header_row(lines)
    body = "\n".join(lines[header_idx:])

    today = utcnow().date()
    rows: list[ParsedMembership] = []
    reader = csv.DictReader(io.StringIO(body))
    add_tsx_suffix = country_code.upper() == "CA"

    for raw in reader:
        if not raw.get("Ticker"):
            continue
        # Only keep equity holdings — cash, futures, swaps, FX exposures
        # are not index constituents in the screening sense.
        if raw.get("Asset Class", "").strip().lower() != "equity":
            continue
        symbol = raw["Ticker"].strip()
        if not symbol:
            continue
        if add_tsx_suffix and not symbol.upper().endswith(".TO"):
            symbol = f"{symbol}.TO"
        rows.append(
            ParsedMembership(
                index_code=index_code,
                ticker_symbol=symbol,
                valid_from=today,
                valid_to=None,
                source=source_name,
            )
        )

    log.info(
        "issuer.ishares.parse_complete",
        index_code=index_code,
        source=source_name,
        constituents=len(rows),
    )
    return rows


# ---------------------------------------------------------------------------
# Invesco (QQQ)
# ---------------------------------------------------------------------------


def parse_invesco_csv(content: str, index_code: str, source_name: str) -> list[ParsedMembership]:
    """Parse an Invesco daily-holdings CSV (QQQ).

    Invesco's CSV header is the first line and the equity filter is on
    ``Class of Shares`` (``COMMON`` / ``CLASS A`` / etc).  Everything
    that isn't an equity-share class is dropped.
    """
    today = utcnow().date()
    rows: list[ParsedMembership] = []
    reader = csv.DictReader(io.StringIO(content))

    # Whitelist of share-class values we accept as "the equity tracking
    # of the company".  Invesco occasionally lists multiple classes when
    # a holding has more than one (e.g., GOOG vs GOOGL); both are valid
    # NDX constituents so we keep both.
    accepted_share_classes = {"COMMON", "CLASS A", "CLASS B", "CLASS C"}

    for raw in reader:
        symbol = (raw.get("Holding Ticker") or "").strip()
        if not symbol:
            continue
        share_class = (raw.get("Class of Shares") or "").strip().upper()
        if share_class and share_class not in accepted_share_classes:
            continue
        rows.append(
            ParsedMembership(
                index_code=index_code,
                ticker_symbol=symbol,
                valid_from=today,
                valid_to=None,
                source=source_name,
            )
        )

    log.info(
        "issuer.invesco.parse_complete",
        index_code=index_code,
        source=source_name,
        constituents=len(rows),
    )
    return rows


# ---------------------------------------------------------------------------
# Source class
# ---------------------------------------------------------------------------
#
# A single class fronts all three issuer CSVs because the orchestrator
# only ever needs to ask "give me the current members of SP500/NDX/DJI";
# the issuer choice is an implementation detail.
# ---------------------------------------------------------------------------


# URLs centralised so they're greppable and mockable.  These are the
# canonical published locations as of the project start; if issuers
# change URLs, this dict is the only place to update.
#
# Canadian funds (XIU = TSX 60, XIC = TSX Composite) live on
# ``blackrock.com/ca`` rather than ``ishares.com/us``; the CSV format is
# identical to the US iShares funds (same metadata preamble + Asset Class
# column), so :func:`parse_ishares_csv` handles both.
ISSUER_URLS: dict[str, tuple[str, str, str]] = {
    # index_code -> (url, source_name, country_code)
    "SP500": (
        "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf/"
        "1467271812596.ajax?fileType=csv&fileName=IVV_holdings&dataType=fund",
        "ishares_ivv",
        "US",
    ),
    "DJI": (
        "https://www.ishares.com/us/products/239725/ishares-dow-jones-industrial-average-etf/"
        "1467271812596.ajax?fileType=csv&fileName=DIA_holdings&dataType=fund",
        "ishares_dia",
        "US",
    ),
    "NDX": (
        "https://www.invesco.com/us/financial-products/etfs/holdings/main/holdings/0?"
        "audienceType=Investor&action=download&ticker=QQQ",
        "invesco_qqq",
        "US",
    ),
    "TSX60": (
        "https://www.blackrock.com/ca/investors/en/products/239832/"
        "ishares-sp-tsx-60-index-etf/1432522418301.ajax?"
        "fileType=csv&fileName=XIU_holdings&dataType=fund",
        "ishares_xiu",
        "CA",
    ),
    "TSXC": (
        "https://www.blackrock.com/ca/investors/en/products/239833/"
        "ishares-sp-tsx-capped-composite-index-etf/1432522418301.ajax?"
        "fileType=csv&fileName=XIC_holdings&dataType=fund",
        "ishares_xic",
        "CA",
    ),
}


class IssuerCsvMembershipSource(DataSource):
    """Issuer-ETF daily-holdings adapter."""

    NAME = "issuer_csv"

    def __init__(self) -> None:
        """No state to initialise."""

    def fetch_current_members(self, index_code: str) -> Iterable[ParsedMembership]:
        """Fetch the current constituents of ``index_code`` from its
        issuer ETF's daily holdings CSV.

        Routes to the iShares or Invesco parser based on the source-name
        prefix.  KeyError on unknown index_code so we fail fast on a
        typo rather than silently return nothing.
        """
        url, source_name, country_code = ISSUER_URLS[index_code]
        log.info(
            "issuer.fetch",
            index_code=index_code,
            url=url,
            source=source_name,
            country=country_code,
        )
        # iShares serves charset-Latin1 with a UTF-8 BOM occasionally;
        # decode bytes ourselves so we control the encoding policy.
        body_bytes = fetch_bytes(url)
        content = body_bytes.decode("utf-8-sig", errors="replace")

        if source_name.startswith("ishares"):
            return parse_ishares_csv(content, index_code, source_name, country_code)
        elif source_name.startswith("invesco"):
            # Invesco's only entry (QQQ) is US-listed; if a CA Invesco
            # fund ever shows up we'll thread country_code through here
            # the same way the iShares branch does.
            return parse_invesco_csv(content, index_code, source_name)
        else:  # pragma: no cover - exhaustive guard
            raise ValueError(f"Unknown issuer source: {source_name}")


# ---------------------------------------------------------------------------
# Helpers used by tests / scripts to render dates in the source_name suffix.
# ---------------------------------------------------------------------------


def todays_date() -> date:
    """Return today's date in UTC.

    Hoisted out of inline ``date.today()`` calls so tests can monkeypatch
    a deterministic value.
    """
    return utcnow().date()


__all__: list[str] = [
    "ISSUER_URLS",
    "IssuerCsvMembershipSource",
    "parse_invesco_csv",
    "parse_ishares_csv",
    "todays_date",
]
