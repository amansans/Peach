"""Momentum indicators: RSI(14), Stochastic(14,3), ROC(12).

All inputs use ``adj_close`` (return-adjusted) so dividend distributions
don't generate spurious momentum signals.  Stochastic also reads
``high`` and ``low`` for its range calculation.
"""

from __future__ import annotations

import pandas as pd

from peach.indicators.registry import indicator

# ---------------------------------------------------------------------------
# RSI (14) — Wilder's smoothing
# ---------------------------------------------------------------------------


@indicator(
    code="rsi_14",
    family="rsi_14",
    category="momentum",
    params={"window": 14},
    produces=["rsi_14"],
)
def rsi_14(df: pd.DataFrame) -> pd.DataFrame:
    """Wilder's RSI(14).

    Definition::

        delta     = adj_close.diff()
        gain      = max(delta, 0)
        loss      = max(-delta, 0)
        avg_gain  = SMMA(gain, 14)
        avg_loss  = SMMA(loss, 14)
        RS        = avg_gain / avg_loss
        RSI       = 100 - 100 / (1 + RS)

    SMMA == Wilder smoothing == EMA with ``alpha = 1/N``.  Standard
    overbought/oversold thresholds are 70/30; the screener's
    ``buy_basic.yaml`` uses ``rsi_14 < 30``.
    """
    delta = df["adj_close"].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False).mean()
    # Guard against avg_loss == 0 on a straight-up streak: RSI → 100.
    rs = avg_gain / avg_loss.where(avg_loss != 0)
    rsi = 100 - 100 / (1 + rs)
    # Where avg_loss is exactly 0 (no down days in the window), RSI is
    # conventionally 100.  Fill the resulting NaN before returning.
    rsi = rsi.where(avg_loss != 0, 100.0)
    return pd.DataFrame({"rsi_14": rsi})


# ---------------------------------------------------------------------------
# Stochastic Oscillator (14, 3)
# ---------------------------------------------------------------------------


@indicator(
    code="stoch_14_3_k",
    family="stoch_14_3",
    category="momentum",
    params={"k_period": 14, "d_period": 3},
    produces=["stoch_14_3_k", "stoch_14_3_d"],
    components=["k", "d"],
)
def stoch_14_3(df: pd.DataFrame) -> pd.DataFrame:
    """Fast Stochastic %K and %D.

    Definitions::

        %K = 100 * (close - LL(14)) / (HH(14) - LL(14))
        %D = SMA(%K, 3)

    where ``HH(N)`` and ``LL(N)`` are the rolling N-bar highest-high
    and lowest-low respectively.
    """
    high_14 = df["high"].rolling(window=14).max()
    low_14 = df["low"].rolling(window=14).min()
    rng = high_14 - low_14
    # When HH == LL (flatline), %K is undefined; leave as NaN so the
    # writer skips that bar.
    k = 100 * (df["close"] - low_14) / rng.where(rng != 0)
    d = k.rolling(window=3).mean()
    return pd.DataFrame({"stoch_14_3_k": k, "stoch_14_3_d": d})


# ---------------------------------------------------------------------------
# Rate of change (12)
# ---------------------------------------------------------------------------


@indicator(
    code="roc_12",
    family="roc_12",
    category="momentum",
    params={"window": 12},
    produces=["roc_12"],
)
def roc_12(df: pd.DataFrame) -> pd.DataFrame:
    """Rate of change over 12 bars, expressed as a percentage.

    ::

        ROC = 100 * (adj_close_t - adj_close_{t-12}) / adj_close_{t-12}
    """
    base = df["adj_close"].shift(12)
    roc = 100 * (df["adj_close"] - base) / base.where(base != 0)
    return pd.DataFrame({"roc_12": roc})
