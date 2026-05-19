"""Peach — multi-layer stock screening and analysis platform.

The package is structured as a set of cohesive sub-packages, each owning a
single layer of the pipeline:

    peach.config        — environment-driven runtime configuration
    peach.db            — SQLAlchemy base, session, and ORM models
    peach.ingestion     — data source adapters + ingestion orchestrator
    peach.indicators    — technical indicators (entry/exit timing)
    peach.fundamentals  — EDGAR-sourced fundamentals (company quality)
    peach.sector_ranking — peer-relative quality
    peach.screener      — config-driven YAML rules engine
    peach.backtest      — walk-forward backtest engine
    peach.macro         — macro/regime overlay (Phase 10)
    peach.agents        — Anthropic-API agentic analyst (Phase 11)
    peach.auth          — auth / users / JWT
    peach.api           — FastAPI app exposing the layers above to UIs
    peach.scheduling    — daily EOD orchestration (cron then Prefect)
    peach.observability — structured logging + data-quality checks
    peach.utils         — small generic helpers (dates, retries)

Each layer is independently importable and depends only on lower layers.
This keeps the dependency graph acyclic and makes unit testing tractable.
"""

# `__version__` is read by tooling (pyproject metadata is the canonical
# source; this is a programmatic mirror for `peach.__version__` lookups).
__version__ = "0.0.1"
