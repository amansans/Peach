"""Indicator layer — technical indicators for entry/exit timing.

Per the architectural plan's conceptual model, technicals answer the
*when* question.  This subpackage:

* Defines the registry / decorator (``peach.indicators.registry``) so
  indicator implementations are *discovered*, not enumerated.
* Hosts the indicator library, grouped by category:
    - :mod:`peach.indicators.library.trend`      — SMA / EMA / MACD / ADX
    - :mod:`peach.indicators.library.momentum`   — RSI / Stochastic / ROC
    - :mod:`peach.indicators.library.volume`     — OBV / Anchored VWAP / A/D
    - :mod:`peach.indicators.library.volatility` — Bollinger / ATR
    - :mod:`peach.indicators.library.support_resistance` — Fibonacci / Pivots
* Provides the engine that loads OHLCV history per ticker and runs the
  registered indicators (``peach.indicators.engine``).
* Provides the bulk-upsert writer to ``indicator_snapshots``
  (``peach.indicators.snapshot_writer``).

Indicator implementations are pure functions of an OHLCV ``DataFrame``
indexed by date.  They neither touch the DB nor know about other
indicators — composition happens at the engine level.  This separation
is what makes hand-checking ("did my RSI math match TA-Lib?") trivial.
"""

# Importing the library subpackage triggers @indicator decorator side
# effects that populate the registry.  Module-level "import for side
# effects" is intentional here; alternative would be a manual registry
# enumeration that bit-rots every time a new indicator is added.
from peach.indicators import library

__all__: list[str] = ["library"]
