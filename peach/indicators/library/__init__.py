"""Indicator implementations grouped by category.

Importing this package triggers the ``@indicator`` decorator on every
implementation, populating the module-level registry in
:mod:`peach.indicators.registry`.  Adding a new indicator is a single
file edit — no registration boilerplate elsewhere.

Categories follow the plan exactly:

* :mod:`peach.indicators.library.trend`              — SMA / EMA / MACD / ADX
* :mod:`peach.indicators.library.momentum`           — RSI / Stochastic / ROC
* :mod:`peach.indicators.library.volume`             — OBV / Anchored VWAP / A/D
* :mod:`peach.indicators.library.volatility`         — Bollinger / ATR
* :mod:`peach.indicators.library.support_resistance` — Fibonacci / Pivots
"""

# Side-effect imports — the @indicator decorator registers each
# implementation at import time.  Module ordering matches the plan's
# grouping order.
from peach.indicators.library import (  # noqa: F401
    momentum,
    support_resistance,
    trend,
    volatility,
    volume,
)
