"""Project-wide pytest configuration.

Currently minimal — Phase 0 has no fixtures that need wide sharing.  The
file exists so future fixtures (DB session, FastAPI test client, sample
data loaders) have a single canonical home, and so pytest treats the
``tests/`` directory as a package root.
"""
