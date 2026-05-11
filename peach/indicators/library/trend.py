"""Trend indicators: SMA(50/200) + cross signal, EMA(12/26), MACD, ADX.

All functions accept a single ``DataFrame`` argument with at least the
columns ``open``, ``high``, ``low``, ``close``, ``adj_close``, ``volume``
indexed by a DatetimeIndex (or any sortable date type) and return a
``DataFrame`` whose columns are the ``produces`` list declared on the
``@indicator`` decorator.

A note on which close to use
----------------------------
Indicators that compose return calculations (RSI, ROC, the ratios that
feed MACD) should ideally use a TOTAL-RETURN-adjusted close —
``adj_close`` here.  Indicators that respond to absolute price levels
(support/resistance, the price axis on a Bollinger chart) use the raw
``close``.  We split per-indicator in the implementations below.
"""

from __future__ import annotations

import pandas as pd

from peach.indicators.registry import indicator

# ---------------------------------------------------------------------------
# Simple moving averages + golden/death cross signal
# ---------------------------------------------------------------------------


@indicator(
    code="sma_50",
    family="sma_50_200",
    category="trend",
    params={"window": 50},
    produces=["sma_50"],
)
def sma_50(df: pd.DataFrame) -> pd.DataFrame:
    """50-day simple moving average of ``adj_close``.

    NaN for the first 49 bars (no full window yet); subsequent bars
    have a defined value.  The engine drops NaN rows before upserting,
    so the resulting snapshot table simply has fewer rows for those
    early dates — a left-join from ``ohlcv_daily`` recovers them.
    """
    return pd.DataFrame({"sma_50": df["adj_close"].rolling(window=50).mean()})


@indicator(
    code="sma_200",
    family="sma_50_200",
    category="trend",
    params={"window": 200},
    produces=["sma_200"],
)
def sma_200(df: pd.DataFrame) -> pd.DataFrame:
    """200-day simple moving average of ``adj_close``."""
    return pd.DataFrame({"sma_200": df["adj_close"].rolling(window=200).mean()})


@indicator(
    code="cross_sma_50_200",
    family="sma_50_200",
    category="trend",
    params={"fast": 50, "slow": 200},
    produces=["cross_sma_50_200"],
)
def cross_sma_50_200(df: pd.DataFrame) -> pd.DataFrame:
    """Golden / death cross signal between SMA-50 and SMA-200.

    Returns ``+1`` on a *golden cross day* (the bar on which the 50-day
    closes above the 200-day for the first time after being below),
    ``-1`` on a *death cross day* (the symmetric event), and ``0``
    otherwise.

    The signal is stored as a numeric so the screener can write rules
    like ``cross_sma_50_200 = 1``.  We *don't* store a forward-filled
    "currently above/below" state — Phase 3 rule expressions can
    cheaply derive that from the underlying SMAs themselves.
    """
    fast = df["adj_close"].rolling(window=50).mean()
    slow = df["adj_close"].rolling(window=200).mean()
    # Crossover detection: today fast>=slow AND yesterday fast<slow.
    above_today = fast >= slow
    above_yesterday = fast.shift(1) >= slow.shift(1)
    # Where today differs from yesterday AND fast is now above → +1.
    golden = (above_today & ~above_yesterday).astype(int)
    death = (~above_today & above_yesterday).astype(int) * -1
    cross = golden + death
    # The first 200 bars have NaN in `slow`; force the signal to NaN
    # there so the engine doesn't insert spurious zero rows.
    cross = cross.where(slow.notna())
    return pd.DataFrame({"cross_sma_50_200": cross})


# ---------------------------------------------------------------------------
# Exponential moving averages
# ---------------------------------------------------------------------------


@indicator(
    code="ema_12",
    family="ema_12_26",
    category="trend",
    params={"window": 12},
    produces=["ema_12"],
)
def ema_12(df: pd.DataFrame) -> pd.DataFrame:
    """12-period EMA of ``adj_close``.  Used directly and feeds MACD.

    Pandas' ``.ewm(span=N).mean()`` uses the canonical
    ``alpha = 2 / (N + 1)`` weighting; ``adjust=False`` matches the
    recursive form that most charting tools use.
    """
    return pd.DataFrame({"ema_12": df["adj_close"].ewm(span=12, adjust=False).mean()})


@indicator(
    code="ema_26",
    family="ema_12_26",
    category="trend",
    params={"window": 26},
    produces=["ema_26"],
)
def ema_26(df: pd.DataFrame) -> pd.DataFrame:
    """26-period EMA of ``adj_close``."""
    return pd.DataFrame({"ema_26": df["adj_close"].ewm(span=26, adjust=False).mean()})


# ---------------------------------------------------------------------------
# MACD (12, 26, 9)
# ---------------------------------------------------------------------------


@indicator(
    code="macd_12_26_9_line",
    family="macd_12_26_9",
    category="trend",
    params={"fast": 12, "slow": 26, "signal": 9},
    produces=["macd_12_26_9_line", "macd_12_26_9_signal", "macd_12_26_9_hist"],
    components=["line", "signal", "hist"],
)
def macd_12_26_9(df: pd.DataFrame) -> pd.DataFrame:
    """MACD(12, 26, 9) — line, signal, and histogram.

    Definition::

        line   = EMA12(adj_close) - EMA26(adj_close)
        signal = EMA9(line)
        hist   = line - signal

    Emitting all three from one function avoids recomputing the two
    underlying EMAs three separate times.
    """
    ema_fast = df["adj_close"].ewm(span=12, adjust=False).mean()
    ema_slow = df["adj_close"].ewm(span=26, adjust=False).mean()
    line = ema_fast - ema_slow
    signal = line.ewm(span=9, adjust=False).mean()
    hist = line - signal
    return pd.DataFrame(
        {
            "macd_12_26_9_line": line,
            "macd_12_26_9_signal": signal,
            "macd_12_26_9_hist": hist,
        }
    )


# ---------------------------------------------------------------------------
# ADX (14) with +DI / -DI
# ---------------------------------------------------------------------------


def _wilder_smooth(series: pd.Series, window: int) -> pd.Series:
    """Wilder's smoothing — an EMA with alpha = 1/window.

    Standard ADX literature uses this rather than a plain SMA / EMA.
    ``ewm(alpha=1/window, adjust=False)`` matches the recursive form
    used by every charting tool I've seen.
    """
    return series.ewm(alpha=1 / window, adjust=False).mean()


@indicator(
    code="adx_14",
    family="adx_14",
    category="trend",
    params={"window": 14},
    produces=["adx_14", "di_plus_14", "di_minus_14"],
    components=[None, "plus_di", "minus_di"],
)
def adx_14(df: pd.DataFrame) -> pd.DataFrame:
    """ADX(14) with +DI and -DI.

    Definitions (Wilder 1978)::

        +DM   = high_t - high_{t-1}                 if positive and > down move, else 0
        -DM   = low_{t-1} - low_t                   if positive and > up move,   else 0
        TR    = max(high - low,
                    |high - close_{t-1}|,
                    |low  - close_{t-1}|)
        +DI   = 100 * SMMA(+DM, 14) / SMMA(TR, 14)
        -DI   = 100 * SMMA(-DM, 14) / SMMA(TR, 14)
        DX    = 100 * |+DI - -DI| / (+DI + -DI)
        ADX   = SMMA(DX, 14)

    ADX > 25 is conventionally interpreted as "trending"; +DI > -DI
    means the trend is up.  We store all three so the rules engine can
    write expressions like ``adx_14 > 25 AND di_plus_14 > di_minus_14``.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = ((up_move > down_move) & (up_move > 0)).astype(float) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)).astype(float) * down_move

    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    plus_di = 100 * _wilder_smooth(plus_dm.fillna(0), 14) / _wilder_smooth(tr.fillna(0), 14)
    minus_di = 100 * _wilder_smooth(minus_dm.fillna(0), 14) / _wilder_smooth(tr.fillna(0), 14)
    # |+DI - -DI| / (+DI + -DI); guard against divide-by-zero when both
    # are zero on the very first bars.
    di_sum = plus_di + minus_di
    dx = 100 * (plus_di - minus_di).abs() / di_sum.where(di_sum != 0)
    adx = _wilder_smooth(dx, 14)
    return pd.DataFrame(
        {
            "adx_14": adx,
            "di_plus_14": plus_di,
            "di_minus_14": minus_di,
        }
    )
