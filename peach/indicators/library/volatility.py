"""Volatility indicators: Bollinger Bands(20, 2), ATR(14)."""

from __future__ import annotations

import pandas as pd

from peach.indicators.registry import indicator

# ---------------------------------------------------------------------------
# Bollinger Bands (20, 2)
# ---------------------------------------------------------------------------


@indicator(
    code="bb_20_2_mid",
    family="bb_20_2",
    category="volatility",
    params={"window": 20, "num_std": 2},
    produces=[
        "bb_20_2_mid",
        "bb_20_2_upper",
        "bb_20_2_lower",
        "bb_20_2_width",
    ],
    components=["mid", "upper", "lower", "width"],
)
def bb_20_2(df: pd.DataFrame) -> pd.DataFrame:
    """Bollinger Bands(20, 2) — middle / upper / lower / width.

    ::

        mid   = SMA(adj_close, 20)
        sigma = STDDEV(adj_close, 20, ddof=0)
        upper = mid + 2 * sigma
        lower = mid - 2 * sigma
        width = (upper - lower) / mid    # the band-width % indicator

    ``ddof=0`` (population variance) matches the convention used by
    every charting tool I've checked; ``pandas.rolling().std()`` defaults
    to ``ddof=1`` (sample variance) which would produce subtly
    different numbers.
    """
    base = df["adj_close"]
    mid = base.rolling(window=20).mean()
    sigma = base.rolling(window=20).std(ddof=0)
    upper = mid + 2 * sigma
    lower = mid - 2 * sigma
    width = (upper - lower) / mid.where(mid != 0)
    return pd.DataFrame(
        {
            "bb_20_2_mid": mid,
            "bb_20_2_upper": upper,
            "bb_20_2_lower": lower,
            "bb_20_2_width": width,
        }
    )


# ---------------------------------------------------------------------------
# ATR (14) — Wilder smoothing of true range
# ---------------------------------------------------------------------------


@indicator(
    code="atr_14",
    family="atr_14",
    category="volatility",
    params={"window": 14},
    produces=["atr_14"],
)
def atr_14(df: pd.DataFrame) -> pd.DataFrame:
    """Average True Range over 14 bars (Wilder smoothing).

    True range per bar::

        TR = max(high - low,
                 |high - close_{t-1}|,
                 |low  - close_{t-1}|)

    ATR = SMMA(TR, 14) — same Wilder smoothing as ADX/RSI.
    """
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    return pd.DataFrame({"atr_14": atr})
