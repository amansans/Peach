"""One-shot operational scripts.

These are NOT part of the regular request/response path of the application.
Each script is invoked manually (or by cron / Prefect) to perform a discrete
operation like seeding reference data, creating a user, or backfilling
historical prices.

Conventions
-----------
* Every script uses Typer so the CLI surface is uniform: `--help` works,
  flag types are validated, errors are user-friendly.
* Every script is idempotent — running it twice should not double-insert
  rows, raise unique-violation errors, or otherwise damage the database.
* Every script logs (via structlog) what it did, in JSON, so cron output
  is grep-able.
"""
