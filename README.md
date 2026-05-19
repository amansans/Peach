# Peach

Multi-layer stock screening & analysis platform for S&P 500 / Nasdaq-100 / Dow Jones.

Peach composes four analytical layers into a daily pipeline:

| Layer | Question it answers | Phase |
|---|---|---|
| **Technicals** | *When* to act (entry/exit timing signals) | 2 |
| **Fundamentals** | *Which* companies are worth holding (quality metrics from EDGAR) | 5 |
| **Sector ranking** | Is this company good *relative to its industry peers*? | 6 |
| **Macro** | Does the *overall environment* support acting right now? | 10 |

The end product is a config-driven YAML rules engine that produces "buy" / "strong buy" candidates, a walk-forward backtest engine that validates rules historically (point-in-time correct, no survivorship bias), and an Anthropic-API-powered analyst agent that writes a thesis per candidate.

The full architectural plan, including phased build order and design decisions, lives in [`/root/.claude/plans/do-not-use-the-happy-dongarra.md`](file:///root/.claude/plans/do-not-use-the-happy-dongarra.md).

## Status

**Phase 0 — skeleton.** Database, migrations, reference tables, bootstrap scripts.

## Quick start

```bash
# Prereqs: docker, docker compose, uv (https://docs.astral.sh/uv/)

uv sync --all-extras                       # install deps into .venv
cp .env.example .env                       # edit JWT_SECRET_KEY etc.

make db.up                                 # start postgres + pgadmin
make migrate                               # apply alembic migrations
make seed                                  # populate exchanges, sectors, indices
make create-user username=admin email=admin@example.com role=admin
                                           # prompts for password
make test                                  # run smoke tests
```

After `make db.up`, pgadmin is available at <http://localhost:5050> (login `admin@peach.local` / `peach`).

## Repository layout

```
peach/         # the application package (config, db, ingestion, indicators, …)
config/        # YAML configuration: indicators, fundamentals, rules, universes
scripts/       # one-shot CLIs: bootstrap reference data, create users, backfills
alembic/       # database migrations
tests/         # unit + integration tests
```

Each Python subpackage carries a docstring explaining its role; start with `peach/__init__.py` for a guided tour.

## Tooling

- **Dependency management**: [`uv`](https://docs.astral.sh/uv/) (lockfile committed)
- **Lint + format**: [`ruff`](https://docs.astral.sh/ruff/)
- **Type check**: `mypy --strict`
- **Pre-commit**: `make install` then `uv run pre-commit install`
- **Tests**: `pytest`

## License

Proprietary — personal project, all rights reserved.
