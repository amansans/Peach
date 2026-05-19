"""Ingestion layer — pulls data from external sources into Postgres.

Two responsibility split
------------------------
* :mod:`peach.ingestion.sources` — one module per *source*.  Each module
  fetches raw data (HTTP / CSV / HTML) and normalises it into typed
  ``ParsedRow`` dataclasses defined in :mod:`peach.ingestion.base`.
  Sources are pure functions of network input: they do NOT touch the
  database.

* :mod:`peach.ingestion.writers` — converts ``ParsedRow`` instances into
  database rows.  Idempotent upserts so re-running an ingest never
  double-counts.

Why the split?  It makes the sources trivially unit-testable with
committed fixtures — no DB or network at test time — and lets the
orchestrator compose multiple sources without each one having a database
opinion of its own.
"""
