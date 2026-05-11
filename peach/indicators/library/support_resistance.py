"""Support & resistance: Fibonacci retracement (60-day swing), Pivot Points.

Both indicators emit several level rows per bar.  Fibonacci's anchor
swing is configurable (60 bars by default per the plan); Pivot Points
are computed from yesterday's H/L/C and refresh each bar.
"""

from __future__ import annotations

import pandas as pd

from peach.indicators.registry import indicator

# ---------------------------------------------------------------------------
# Fibonacci retracement — 60-day swing anchor
# ---------------------------------------------------------------------------


@indicator(
    code="fib_60_236",
    family="fib_60",
    category="support_resistance",
    params={"lookback": 60, "levels": [0.236, 0.382, 0.5, 0.618]},
    produces=[
        "fib_60_236",
        "fib_60_382",
        "fib_60_500",
        "fib_60_618",
        "fib_60_anchor_high",
        "fib_60_anchor_low",
    ],
    components=["236", "382", "500", "618", "anchor_high", "anchor_low"],
)
def fib_60(df: pd.DataFrame) -> pd.DataFrame:
    """Fibonacci retracement levels from the rolling 60-bar swing.

    For each bar we compute:

    * ``anchor_high`` — highest high in the trailing 60 bars;
    * ``anchor_low``  — lowest low  in the trailing 60 bars;
    * four retracement levels: 23.6%, 38.2%, 50.0%, 61.8%.

    The four levels are stored as price values (not percentages),
    placed *within* the ``[anchor_low, anchor_high]`` range::

        level_p = anchor_low + (anchor_high - anchor_low) * p

    Directionality (whether the swing was up or down) is intentionally
    NOT encoded here — the rules engine and UI can derive it from the
    relative dates of the anchor high/low if needed.  This keeps the
    storage shape symmetric.

    Why 60 bars?  The plan calls it the default; ~3 trading months
    captures a meaningful pullback without being so long that the
    retracement levels stop moving with the market.
    """
    hh = df["high"].rolling(window=60).max()
    ll = df["low"].rolling(window=60).min()
    rng = hh - ll
    return pd.DataFrame(
        {
            "fib_60_236": ll + rng * 0.236,
            "fib_60_382": ll + rng * 0.382,
            "fib_60_500": ll + rng * 0.500,
            "fib_60_618": ll + rng * 0.618,
            "fib_60_anchor_high": hh,
            "fib_60_anchor_low": ll,
        }
    )


# ---------------------------------------------------------------------------
# Classic Pivot Points — daily, computed from yesterday's H/L/C
# ---------------------------------------------------------------------------


@indicator(
    code="pivot_p",
    family="pivot_classic",
    category="support_resistance",
    params={"method": "classic"},
    produces=[
        "pivot_p",
        "pivot_r1",
        "pivot_r2",
        "pivot_s1",
        "pivot_s2",
    ],
    components=["p", "r1", "r2", "s1", "s2"],
)
def pivot_classic(df: pd.DataFrame) -> pd.DataFrame:
    """Classic floor-trader pivot points, computed from yesterday's bar.

    Definitions::

        P  = (high_{t-1} + low_{t-1} + close_{t-1}) / 3
        R1 = 2P - low_{t-1}
        S1 = 2P - high_{t-1}
        R2 = P + (high_{t-1} - low_{t-1})
        S2 = P - (high_{t-1} - low_{t-1})

    The pivot for today is therefore *known at the open*.  First bar of
    the dataset has NaN (no prior bar to derive from).
    """
    prev_high = df["high"].shift(1)
    prev_low = df["low"].shift(1)
    prev_close = df["close"].shift(1)
    p = (prev_high + prev_low + prev_close) / 3
    rng = prev_high - prev_low
    r1 = 2 * p - prev_low
    s1 = 2 * p - prev_high
    r2 = p + rng
    s2 = p - rng
    return pd.DataFrame(
        {
            "pivot_p": p,
            "pivot_r1": r1,
            "pivot_r2": r2,
            "pivot_s1": s1,
            "pivot_s2": s2,
        }
    )
