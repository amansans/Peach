# ---------------------------------------------------------------------------
# Peach — developer-facing task runner.
#
# Targets are the *contracted* developer workflow.  If a developer needs to
# do something more than once, it belongs as a target here so the canonical
# form is captured and discoverable.  `make help` lists everything.
#
# Why Make?  Three reasons: it's already installed everywhere, the syntax
# accommodates simple shell pipelines without ceremony, and the target list
# doubles as documentation.
# ---------------------------------------------------------------------------

# `.DEFAULT_GOAL` controls what runs when you just type `make` with no target.
.DEFAULT_GOAL := help

# `.PHONY` tells Make these targets don't produce a file by that name — without
# this, `make test` would no-op if a file called `test` ever appeared in the
# repo root.
.PHONY: help install sync lock fmt lint type test test-cov \
        db.up db.down db.logs db.shell \
        migrate migrate-create \
        seed create-user \
        clean

# ---------------------------------------------------------------------------
# help — list every target with its summary comment (the line beginning `## `
# immediately above the target).  Auto-generated so this stays in sync.
# ---------------------------------------------------------------------------
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make \033[36m<target>\033[0m\n\nTargets:\n"} \
		/^[a-zA-Z_.-]+:.*##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ===========================================================================
# Dependency management (uv)
# ===========================================================================

install: sync ## Alias for `sync` — install everything from uv.lock

sync: ## Sync dependencies from uv.lock into .venv (creates .venv if needed)
	uv sync --all-extras

lock: ## Regenerate uv.lock after editing pyproject.toml
	uv lock

# ===========================================================================
# Code quality
# ===========================================================================

fmt: ## Format the codebase with ruff
	uv run ruff format peach scripts tests

lint: ## Lint the codebase with ruff (auto-fix what's safe)
	uv run ruff check peach scripts tests --fix

type: ## Run mypy in strict mode over the peach package
	uv run mypy peach

test: ## Run the test suite
	uv run pytest

test-cov: ## Run tests with coverage report
	uv run pytest --cov=peach --cov-report=term-missing

# ===========================================================================
# Database (local docker-compose)
# ===========================================================================

db.up: ## Bring up postgres + pgadmin in the background
	docker compose up -d

db.down: ## Stop and remove the postgres + pgadmin containers
	docker compose down

db.logs: ## Tail postgres logs
	docker compose logs -f postgres

db.shell: ## Open a psql shell in the running postgres container
	docker compose exec postgres psql -U peach -d peach

# ===========================================================================
# Alembic migrations
# ===========================================================================

migrate: ## Apply all pending migrations (alembic upgrade head)
	uv run alembic upgrade head

# Usage: `make migrate-create msg="add foo column"`
# Why -- in the awk-built help row: Make's variable assignment via `msg=` is
# documented in the comment to the right of the target rather than in a
# separate `help` section.
migrate-create: ## Create a new auto-generated migration; pass msg="..."
	uv run alembic revision --autogenerate -m "$(msg)"

# ===========================================================================
# One-shot scripts
# ===========================================================================

seed: ## Seed reference tables (exchanges, GICS sectors, indices)
	uv run python -m scripts.bootstrap_universe

create-user: ## Create an admin user — pass username= and email=
	uv run python -m scripts.create_user --username "$(username)" --email "$(email)"

# ===========================================================================
# Ingestion (Phase 1)
# ===========================================================================

backfill: ## Backfill OHLCV history.  Pass years=5 (default) or only-symbol=AAPL.
	uv run python -m scripts.backfill_prices --years $(or $(years),5) \
		$(if $(only-symbol),--only-symbol $(only-symbol),)

daily-eod: ## Run the daily EOD pipeline (membership refresh + price update)
	uv run python -m peach.scheduling.daily_eod $(if $(backfill-days),--backfill-days $(backfill-days),)

# ===========================================================================
# Housekeeping
# ===========================================================================

clean: ## Remove build, cache, and coverage artifacts (keeps .venv)
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +
