"""Concrete data-source adapters.

Each module here implements one external source.  Sources are pure
parsers — they fetch data and emit ``Parsed*`` records from
:mod:`peach.ingestion.base`.  Writing to the database is the
orchestrator's responsibility, not theirs.

Sources implemented in Phase 1
------------------------------
* :mod:`peach.ingestion.sources.stooq_source` — primary OHLCV via Stooq.
* :mod:`peach.ingestion.sources.yfinance_source` — OHLCV fallback for
  Stooq-missing rows.
* :mod:`peach.ingestion.sources.wikipedia_membership` — current SP500 /
  NDX / DJI constituents scraped from Wikipedia article tables.
* :mod:`peach.ingestion.sources.issuer_csv_membership` — current
  constituents from iShares IVV / DIA and Invesco QQQ daily holdings.

Deferred
--------
Wikipedia *revision-history* parsing for SP500 / DJI back-fill is a
separate one-shot scraper (will land alongside the first backtest that
genuinely needs deep history).
"""
