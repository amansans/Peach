"""Scheduling layer — orchestrates the daily end-of-day refresh.

Two interfaces:

* :mod:`peach.scheduling.daily_eod` — the v1 cron entry point.  Runs all
  Phase-1 ingestion steps in dependency order: membership → prices →
  data-quality.

* ``peach.scheduling.flows`` (Phase 8, not yet created) — the Prefect
  conversion of ``daily_eod``.  Same logical pipeline, packaged as a
  Prefect ``@flow`` so its run history is browsable in the Prefect UI.
"""
