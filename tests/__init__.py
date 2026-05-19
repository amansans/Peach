"""Test suite root.

Layout
------
* tests/unit/        — pure-Python unit tests (no DB, no network).
* tests/integration/ — tests that require a running Postgres.  Marked with
                       ``@pytest.mark.integration`` so CI can selectively
                       skip them when a DB is not available.
* tests/fixtures/    — committed sample data (CSVs, JSON snapshots) that
                       tests can use without hitting external services.
"""
