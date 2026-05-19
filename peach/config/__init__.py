"""Runtime configuration package.

Importing `peach.config.settings.get_settings()` is the canonical way to read
any environment-driven configuration value.  Direct `os.environ` access is
discouraged — settings go through pydantic validation so typos and missing
required values fail at process start rather than mid-flight.
"""
