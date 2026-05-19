"""Database layer — SQLAlchemy declarative base, session factory, and models.

Anything that touches the database goes through this package.  The rules:

* `peach.db.base` declares the `Base` class that every ORM model inherits
  from, plus a shared `TimestampMixin` carrying `created_at` / `updated_at`.

* `peach.db.session` owns the engine and `SessionLocal` factory.  Application
  code obtains a session via the `session_scope()` context manager or, in
  the API, via the FastAPI dependency declared in `peach.api.deps`.

* `peach.db.models.*` defines the ORM models — one module per aggregate.

* `peach.db.repositories.*` (added per phase) holds the small query helpers
  that wrap raw SQLAlchemy queries.  Keeping them in their own modules means
  the models stay declarative and queries stay greppable.

Schema changes go through Alembic — no `Base.metadata.create_all()` in
application code.  See `alembic/` for migration scripts.
"""
