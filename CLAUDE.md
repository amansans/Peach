# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

Peach is a multi-layer stock screening platform for the SP500 + Nasdaq-100 + Dow Jones + S&P/TSX 60 + S&P/TSX Composite universe (~750 tickers). The architectural plan — including phased build order, design rationale, indicator inventory, and hosting tiers — lives at `/root/.claude/plans/do-not-use-the-happy-dongarra.md`. **Read that plan before making non-trivial changes.**

**Status:**
- **Phase 0 complete** — skeleton, reference schema, bootstrap scripts.
- **Phase 1 complete** — point-in-time `index_memberships`, `ohlcv_daily` (composite PK + BRIN), `corporate_actions`; Stooq + yfinance OHLCV ingestion; Wikipedia + issuer-CSV membership scraping; daily-EOD orchestrator and 5-year backfill script.
- **Phase 2 complete** — `indicators_catalog` + `indicator_snapshots` (composite PK + cross-section index); registry-driven indicator engine; all 15 plan-defined technicals (18 specs / 35 distinct codes: SMA-50/200 + golden-cross, EMA-12/26, MACD, ADX, RSI-14, Stochastic-14/3, ROC-12, OBV, Anchored VWAP from 52w low/high, A/D Line, Bollinger-20/2, ATR-14, Fibonacci-60, Pivot Points); indicators recompute wired into `daily_eod`.
- Phases 3–13 are still ahead.

## Common commands

All workflows go through the Makefile (`make help` lists every target). Targets internally use `uv run`, so a working `.venv` (created by `make sync`) is the only prerequisite besides Docker.

```bash
make sync                                  # install deps from uv.lock into .venv
make db.up                                 # start local postgres + pgadmin
make migrate                               # alembic upgrade head
make seed                                  # populate exchanges + GICS sectors + indices (idempotent)
make create-user username=admin email=a@b.com    # bcrypt-hash + insert/update user (prompts for password)
make daily-eod                             # phase 1+2: refresh memberships + ingest prices + recompute indicators
make backfill years=5                      # phase 1: pull 5y OHLCV history for current constituents
make seed-indicators                       # phase 2: seed indicators_catalog from the in-code registry

make fmt                                   # ruff format
make lint                                  # ruff check --fix
make type                                  # mypy --strict on peach/
make test                                  # full pytest run
make test-cov                              # tests + coverage report

uv run pytest tests/unit/test_smoke.py::test_settings_rejects_short_jwt_secret -v
                                           # single-test invocation pattern
```

Migrations: edit ORM models in `peach/db/models/`, then `make migrate-create msg="..."` for autogenerate. Alembic reads `DATABASE_URL` from pydantic-settings — `alembic.ini` is intentionally blank.

## Architecture — the load-bearing ideas

**Four-layer pipeline, composed in this order.** Technicals (entry/exit timing) → Fundamentals (company quality) → Sector ranking (peer-relative quality) → Macro (regime overlay). Each layer is its own subpackage under `peach/` and depends only on lower layers — the dependency graph is intentionally acyclic.

**API-first.** `peach.api` (FastAPI, Phase 4) is the single source of truth. UIs (Streamlit now, Next.js later) call it; nothing else touches the DB directly. The eventual UI swap is a rewrite of the UI, not the platform.

**Two invariants are wired into the schema from day one and cannot be retrofitted:**
1. *Point-in-time index membership* — `index_memberships(valid_from, valid_to)` (Phase 1) is the defense against survivorship bias. Backtests that "buy AAPL on 2010-01-01" must check that AAPL was in the index on that date.
2. *Point-in-time fundamentals* — `fundamentals_facts(reported_at)` (Phase 5, raw EDGAR XBRL) records *when* each value was published. Derived metrics (FCF, ROIC, EV/EBITDA, …) materialize into `fundamentals_metrics`. Never read fundamentals without an as-of date.

**Indicator codes encode parameters AND components.** One row per `(ticker, bar_date, indicator_code)`. Multi-component indicators expand: `macd_12_26_9_line` / `_signal` / `_hist`, `bb_20_2_upper` / `_mid` / `_lower`, `stoch_14_3_k` / `_d`, `pivot_p` / `_r1` / `_r2` / `_s1` / `_s2`, etc. The `indicators_catalog` table tells the UI which codes group together. VWAP is *Anchored VWAP* (52-week low/high anchors) since true VWAP needs intraday data; never mix the two concepts.

**Custom rules engine, ~200 LOC, YAML-driven.** Phase 3 builds a small AST evaluator with operators like `crossed_above`, `within_last_n`, `between`. Don't reach for `json-rules-engine` or similar — they don't handle time-series operators cleanly.

**Cron + Python for v1; migrate to Prefect 3 only when retries/observability hurt.** Airflow is explicitly rejected.

**Multi-user (2–5 trusted users) with shared data.** Auth is gatekeeping, not per-user data scoping. Rule sets, screener runs, agent verdicts are global. `triggered_by_user_id` columns on expensive runs (backtests, agent verdicts) track attribution but don't filter visibility.

**Anthropic models (Phase 11):** default `claude-sonnet-4-6` for routine verdicts; reserve `claude-opus-4-7` for explicit deep-dive requests. Use prompt caching on system prompt + tool descriptions.

## Ingestion architecture (Phase 1)

**Parser / writer split is load-bearing.** Source modules under `peach/ingestion/sources/` are pure parsers — they fetch data via `peach.ingestion.http` and emit typed `ParsedOHLCV` / `ParsedMembership` / `ParsedCorporateAction` dataclasses from `peach.ingestion.base`. The DB is touched only by `peach/ingestion/writers.py`. This makes parsers unit-testable with committed fixtures (`tests/fixtures/`) and lets the orchestrator compose multiple sources without each carrying a DB opinion.

**The orchestrator owns source-priority policy.** `peach.ingestion.orchestrator` decides Stooq-first-then-yfinance for prices, and issuer-CSV-first-then-Wikipedia for membership. Source modules don't know about each other.

**Writers are idempotent.** `upsert_ohlcv_rows` uses `INSERT ... ON CONFLICT (ticker_id, bar_date) DO UPDATE` so re-running an ingest is safe. `sync_current_memberships` reconciles a fresh constituent list against open-ended membership periods: ticker in old∩new → no-op; ticker only in new → insert open-ended period; ticker only in old → close existing period at today. Never rewrite a `valid_from` — that destroys history.

**Stooq's `close` doubles as `adj_close` in Phase 1.** Stooq is split-adjusted but not dividend-adjusted. Phase 5 EDGAR ingestion will recompute true dividend-adjusted closes from `corporate_actions`. yfinance fallback writes its true `Adj Close` directly.

**Network-fetching functions get `@network_retry`** from `peach.ingestion.base`. Source-level code catches `httpx.HTTPError` and re-raises as `NetworkError` so the tenacity-driven retry sees a uniform signal. 4xx responses do NOT retry (a 404 is "wrong URL", not "flaky server").

**Source attribution is queryable.** Every OHLCV row and membership row carries a `source` column with stable string values (`stooq`, `yfinance_gapfill`, `wikipedia`, `ishares_ivv`, `invesco_qqq`, `ishares_dia`, `ishares_xiu`, `ishares_xic`). `SELECT source, count(*) FROM ohlcv_daily GROUP BY source` audits provenance at any time.

**Canadian (TSX) listings live alongside US.** `exchanges.country_code` (`US` / `CA`) is the canonical hook for the US-vs-Canadian-stocks filter — the screener joins `tickers → exchanges → country_code` to scope a run. TSX-listed symbols are stored with a `.TO` suffix (e.g., `RY.TO`) so they never collide with same-named US tickers under the unique `tickers.symbol` constraint. Each index also has its own `country_code`, which the orchestrator reads to:
- pick the default listing exchange (`XNAS` for US indices, `XTSE` for TSX) when creating new ticker stubs;
- pick the Stooq URL suffix (`.us` vs `.ca`) when fetching prices.
The yfinance fallback reads the symbol verbatim — Yahoo's API already expects the `.TO` suffix.

**Deferred to its own one-shot scraper**: Wikipedia *revision-history* parsing for SP500/DJI/TSX deep history. The current Wikipedia source reads only the live constituent table. The schema (`valid_from`/`valid_to`) is forward-compatible — historical rows can be backfilled later without rework.

## Indicator architecture (Phase 2)

**Registry-driven.** Every indicator implementation is a pure function decorated with `@indicator(...)` from `peach.indicators.registry`. Import-time side effects populate a module-level dict; the engine iterates it, and `scripts/seed_indicators.py` reads the same dict to reconcile `indicators_catalog`. There is no manual enumeration anywhere — adding a new indicator is a single file edit.

**Spec count ≠ indicator count.** The plan promises 15 user-facing indicators; the registry holds 18 specs because SMA-50/SMA-200/cross_sma_50_200 are split into three decorators (and EMA-12/EMA-26 into two, and Anchored VWAP into low/high). The combined `produces` lists fan out into 35 distinct `indicator_code`s — the unit of storage in `indicator_snapshots`. The `test_every_registered_indicator_runs_on_synthetic_data` test pins both numbers.

**Storage shape is long-form, one row per (ticker, bar, code).** Multi-component indicators (MACD: line/signal/hist; Bollinger: mid/upper/lower/width; ADX: adx/+DI/-DI; Stochastic: %K/%D; Fibonacci: 6 levels; Pivots: P/R1/R2/S1/S2) explode into one row each. The `indicators_catalog.family` column groups them for UI plotting; storage stays uniformly tabular for fast aggregates.

**NaN warmup bars are not stored.** Indicators are undefined for their first N bars (SMA-200's first 199). The writer drops NaN rows before upsert — querying "missing values" is a left join from `ohlcv_daily`, not a NULL scan. This keeps the snapshot table compact.

**Wilder's smoothing == `ewm(alpha=1/N, adjust=False)`.** Used by RSI, ADX, and ATR. Do NOT substitute `rolling(N).mean()` — the difference compounds and won't match charting tools.

**Population stddev for Bollinger.** `rolling(window=20).std(ddof=0)` matches every charting tool I've checked; pandas' default `ddof=1` (sample stddev) produces subtly different bands.

**Decimal precision is preserved end-to-end.** `indicator_snapshots.value` is `NUMERIC(28, 12)` so cumulative indicators (OBV can hit ~10^13 for mega-caps) and ratios both fit. The writer routes floats through `Decimal(str(...))` to dodge the pandas→numpy→psycopg float-binding precision loss.

**Indicator math vs price-axis indicators.** Return-sensitive indicators (RSI, ROC, MACD, the moving averages that feed crosses) read `adj_close`. Price-level indicators (Pivots, ADX's true range, Stochastic's high/low range) read raw `high`/`low`/`close`. This split is intentional — keep it when adding new indicators.

**Anchored VWAP is not intraday VWAP.** The 52-week-low and 52-week-high anchors are the EOD substitute; surface the chosen anchor in UI labels so users aren't misled. True intraday VWAP requires data we don't ingest.

**Engine fans out per-ticker.** `run_for_all_tickers()` loops over tickers serially with per-ticker failure isolation. Parallelism, if ever needed, happens at the ticker loop — not inside indicators.

## Coding conventions (these are non-default)

- **Heavy docstrings + WHY comments.** Per-project preference: every public function/class/module gets a docstring covering purpose, inputs, outputs, side effects, and gotchas. Inline comments explain *why*, never *what*. Don't comment the obvious. See examples throughout `peach/db/base.py` and `scripts/bootstrap_universe.py`.
- **`uv` is the package manager** — `pyproject.toml` + `uv.lock` are the source of truth. Never `pip install`; always `uv add` or edit `pyproject.toml` and `uv lock`.
- **mypy --strict** on the `peach/` package. Type hints required on every function signature. `alembic/versions/*` is excluded.
- **No `Base.metadata.create_all()`** in application code. Schema changes go through Alembic migrations only.
- **No direct `os.environ` access.** Read config via `peach.config.settings.get_settings()` so values are pydantic-validated at startup.
- **Models must be re-exported from `peach/db/models/__init__.py`** so Alembic autogenerate sees them. There's a `test_all_models_registered_with_metadata` smoke test that pins this invariant — don't bypass it.
- **Constraint names rely on `NAMING_CONVENTION` in `peach/db/base.py`.** When adding a `CheckConstraint` or similar, pass only the suffix (e.g., `name="level_range"`) — the convention prepends `ck_<table>_`. Doubling the prefix in the migration produces `ck_sectors_ck_sectors_level_range`.
- **Postgres ENUMs** use `postgresql.ENUM(..., create_type=False)` plus an explicit `.create()` call in migrations. `sa.Enum` does not suppress `CREATE TYPE` in offline (`--sql`) mode and produces duplicate DDL.

## Safety rails

- `peach.config.settings.SafetyMode` defaults to `paper`. `live` is intentionally unimplemented — flipping it should not produce a working real-money code path until ≥3 months of paper trading with positive expectancy.
- The migration's downgrade path must drop the `user_role` ENUM after dropping the `users` table; orphaned ENUM types break re-upgrades. The Phase 0 migration handles this correctly — preserve the pattern for any future enum-bearing tables.

## Free data sources (committed to v1)

| Type | Source |
|---|---|
| OHLCV daily | **Stooq** primary, **yfinance** fallback. Don't mix sources within a single ticker's history. |
| Fundamentals | **SEC EDGAR** XBRL `companyfacts` API. Free, authoritative, point-in-time correct. Send `EDGAR_USER_AGENT` per SEC fair-use policy. Do NOT use yfinance fundamentals. |
| Index membership | **Wikipedia revision history** (SP500/DJI) + **iShares IVV / Invesco QQQ / iShares DIA** issuer CSVs. |
| Macro (Phase 10) | **FRED** via `fredapi`. Series include DGS10, T10Y2Y, VIXCLS, BAMLH0A0HYM2. |

## Known gotchas

- `.github/workflows/ci.yaml` and `cd.yaml` are **stale** — they reference the removed `requirements.txt` and Python 3.10, while the project is on 3.12 with `uv`. They will fail until rewritten (probably bundled with a Phase 1 change so CI catches ingestion bugs).
- The system Python is 3.11 in some sandboxes; `uv sync` downloads 3.12 itself, so don't try to run `python -m ...` outside of `uv run`.
- Docker daemon may be unavailable in sandboxed environments. As a fallback, a local Postgres 16 cluster (`pg_ctlcluster 16 main start`) on `127.0.0.1:5432` works identically — just point `DATABASE_URL` at it.

## Maintaining this file

Update CLAUDE.md whenever a phase lands or a non-obvious convention changes. The plan file at `/root/.claude/plans/do-not-use-the-happy-dongarra.md` stays the long-form record; this file is the operating manual.
