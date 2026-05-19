"""Unit tests for the indicator library.

Each test runs a pure function against a small, hand-built OHLCV
DataFrame and asserts on a value we know analytically.  No DB, no
network.  Where reasonable we cross-check against a textbook formula
applied by hand; for indicators with no closed form (ADX, OBV's later
bars) we test invariants rather than exact values.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from peach.indicators.library.momentum import roc_12, rsi_14, stoch_14_3
from peach.indicators.library.support_resistance import fib_60, pivot_classic
from peach.indicators.library.trend import (
    adx_14,
    cross_sma_50_200,
    ema_12,
    macd_12_26_9,
    sma_50,
    sma_200,
)
from peach.indicators.library.volatility import atr_14, bb_20_2
from peach.indicators.library.volume import ad_line, obv
from peach.indicators.registry import all_specs

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _flat_ohlcv(n: int, price: float = 100.0) -> pd.DataFrame:
    """A flat OHLCV series at a single price.  Useful for testing
    indicators against a degenerate input where most outputs are
    analytically known (e.g., RSI of a flat series).
    """
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "adj_close": price,
            "volume": 1_000_000,
        },
        index=idx,
    )


def _linear_ohlcv(n: int, start: float = 100.0, step: float = 1.0) -> pd.DataFrame:
    """A strictly-increasing OHLCV series.  RSI on this series is exactly
    100 (no down bars after the first); SMA equals the centered point;
    ROC, MACD all reduce to closed forms.
    """
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    closes = pd.Series([start + i * step for i in range(n)], index=idx)
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes + 0.5,
            "low": closes - 0.5,
            "close": closes,
            "adj_close": closes,
            "volume": 1_000_000,
        },
        index=idx,
    )


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------


def test_sma_50_matches_pandas_rolling_mean() -> None:
    df = _linear_ohlcv(60)
    out = sma_50(df)["sma_50"]
    # First 49 bars undefined.
    assert out.iloc[:49].isna().all()
    # On bar 50 (index 49), the SMA equals the average of the first 50
    # closes — for a 1-step linear series starting at 100 that's
    # (100 + 149) / 2 = 124.5.
    assert math.isclose(out.iloc[49], 124.5, abs_tol=1e-9)


def test_sma_200_undefined_until_bar_200() -> None:
    df = _linear_ohlcv(250)
    out = sma_200(df)["sma_200"]
    assert out.iloc[:199].isna().all()
    assert out.iloc[199] == pytest.approx(199.5)  # mean(100..299)


def test_cross_sma_signals_golden_then_quiet() -> None:
    """A series that starts below trend then breaks above produces
    exactly one +1 bar (the cross) and zeros after."""
    # Build a series where SMA-50 crosses above SMA-200 exactly once.
    # Construction: first 200 days at price 100, then a sharp rally.
    n = 260
    closes = np.concatenate([np.full(200, 100.0), np.linspace(100, 200, n - 200)])
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    s = pd.Series(closes, index=idx)
    df = pd.DataFrame({"open": s, "high": s, "low": s, "close": s, "adj_close": s, "volume": 1})
    out = cross_sma_50_200(df)["cross_sma_50_200"].dropna()
    n_golden = int((out == 1).sum())
    n_death = int((out == -1).sum())
    assert n_golden == 1
    assert n_death == 0


# ---------------------------------------------------------------------------
# Momentum
# ---------------------------------------------------------------------------


def test_rsi_flat_series_undefined_then_100_or_nan() -> None:
    """On a flat series both avg_gain and avg_loss are zero — RSI is
    conventionally 100 (we filled NaN to 100 when avg_loss == 0)."""
    df = _flat_ohlcv(30)
    out = rsi_14(df)["rsi_14"]
    # First bar's delta is NaN, but ewm propagates so RSI is defined
    # from bar 2 onwards.  Every defined value should be the "no losses"
    # convention of 100.
    defined = out.iloc[1:]
    assert (defined == 100.0).all()


def test_rsi_strictly_rising_series_is_100() -> None:
    df = _linear_ohlcv(30)
    out = rsi_14(df)["rsi_14"]
    # Bar 1 onwards: every delta is +1, avg_loss is 0 → RSI 100.
    assert (out.iloc[1:] == 100.0).all()


def test_roc_12_step_function() -> None:
    df = _linear_ohlcv(20, start=100, step=1)
    out = roc_12(df)["roc_12"]
    # ROC at bar 12 = (112 - 100) / 100 * 100 = 12.0
    assert out.iloc[12] == pytest.approx(12.0)


def test_stochastic_k_in_range_0_100() -> None:
    """%K is bounded to [0, 100] by construction."""
    rng = np.random.default_rng(seed=42)
    n = 50
    closes = pd.Series(
        100 + rng.normal(size=n).cumsum(), index=pd.date_range("2026-01-01", periods=n, freq="B")
    )
    df = pd.DataFrame(
        {
            "open": closes,
            "high": closes + 1,
            "low": closes - 1,
            "close": closes,
            "adj_close": closes,
            "volume": 1,
        }
    )
    out = stoch_14_3(df)["stoch_14_3_k"].dropna()
    assert (out >= 0).all()
    assert (out <= 100).all()


# ---------------------------------------------------------------------------
# Volume
# ---------------------------------------------------------------------------


def test_obv_strictly_rising_equals_cumulative_volume() -> None:
    df = _linear_ohlcv(10)
    out = obv(df)["obv"]
    # Every bar after the first has a positive close-diff, so OBV is
    # +volume each bar → cumulative volume from bar 1 onwards.
    # Bar 0 contributes 0 (no prior close).
    assert out.iloc[0] == 0
    assert out.iloc[-1] == 1_000_000 * 9


def test_ad_line_zero_for_flat_bars() -> None:
    """When high == low, the money flow multiplier is set to 0,
    so AD line stays at 0."""
    df = _flat_ohlcv(10)
    out = ad_line(df)["ad_line"]
    assert (out == 0).all()


# ---------------------------------------------------------------------------
# Volatility
# ---------------------------------------------------------------------------


def test_bb_20_2_flat_series_has_zero_width() -> None:
    df = _flat_ohlcv(30)
    out = bb_20_2(df)
    # On a flat series sigma is 0 → upper == lower == mid.
    width = out["bb_20_2_width"].iloc[19:]
    assert (width == 0).all()


def test_atr_14_flat_series_is_zero() -> None:
    df = _flat_ohlcv(30)
    out = atr_14(df)["atr_14"]
    # Every bar has high == low and close unchanged → TR is 0
    # everywhere → ATR is 0.
    assert (out == 0).all()


# ---------------------------------------------------------------------------
# Support / resistance
# ---------------------------------------------------------------------------


def test_fib_60_levels_inside_anchor_range() -> None:
    """Each Fibonacci level must lie between anchor_low and anchor_high."""
    df = _linear_ohlcv(80)
    out = fib_60(df).dropna()
    for col in ["fib_60_236", "fib_60_382", "fib_60_500", "fib_60_618"]:
        assert (out[col] >= out["fib_60_anchor_low"]).all()
        assert (out[col] <= out["fib_60_anchor_high"]).all()


def test_pivot_classic_is_average_of_prior_hlc() -> None:
    df = _linear_ohlcv(5)
    out = pivot_classic(df)["pivot_p"]
    # Pivot for bar i uses bar i-1's H, L, C.  For our linear series,
    # bar 0 prices are 100 (close), 100.5 (high), 99.5 (low).
    # P(bar=1) = (100.5 + 99.5 + 100) / 3 = 100.
    assert out.iloc[1] == pytest.approx(100.0)
    assert math.isnan(out.iloc[0])


# ---------------------------------------------------------------------------
# MACD + ADX + EMA — invariants only (closed forms are messy)
# ---------------------------------------------------------------------------


def test_macd_components_are_aligned() -> None:
    df = _linear_ohlcv(50)
    out = macd_12_26_9(df)
    # By definition `hist = line - signal`.
    assert (
        (out["macd_12_26_9_hist"] - (out["macd_12_26_9_line"] - out["macd_12_26_9_signal"])).abs()
        < 1e-9
    ).all()


def test_ema_12_first_bar_equals_first_close() -> None:
    """With ``adjust=False``, the first EMA bar equals the first close."""
    df = _linear_ohlcv(5)
    out = ema_12(df)["ema_12"]
    assert out.iloc[0] == pytest.approx(df["adj_close"].iloc[0])


def test_adx_14_runs_without_nan_explosion() -> None:
    """ADX has no clean closed form on a small dataset, but it must
    not produce a Series that is *all* NaN — at least the last few
    bars should have finite values once enough warmup has accumulated.
    """
    rng = np.random.default_rng(seed=7)
    n = 60
    closes = pd.Series(
        100 + rng.normal(size=n).cumsum(), index=pd.date_range("2026-01-01", periods=n, freq="B")
    )
    df = pd.DataFrame(
        {
            "open": closes,
            "high": closes + 1,
            "low": closes - 1,
            "close": closes,
            "adj_close": closes,
            "volume": 1,
        }
    )
    out = adx_14(df)["adx_14"].dropna()
    assert len(out) > 0


# ---------------------------------------------------------------------------
# Registry contract
# ---------------------------------------------------------------------------


def test_every_registered_indicator_runs_on_synthetic_data() -> None:
    """Sanity: import-time registration produces every indicator and each
    one runs without raising on a 300-bar synthetic series.

    Spec count vs indicator count
    -----------------------------
    The plan promises 15 user-facing indicators.  Internally we register
    18 compute functions because some user-facing indicators are split:

      * "50/200-day MA + golden/death cross" → 3 specs
        (``sma_50``, ``sma_200``, ``cross_sma_50_200``)
      * "EMA 12/26"                          → 2 specs (``ema_12``, ``ema_26``)
      * "Anchored VWAP (52w low + 52w high)" → 2 specs

    Total produced codes: 35.  This counts every column the engine
    writes — multi-component indicators (MACD: 3, Bollinger: 4, ADX: 3,
    Stochastic: 2, Fibonacci: 6, Pivots: 5) inflate this number well
    above the spec count.
    """
    df = _linear_ohlcv(300)
    specs = all_specs()
    assert len(specs) == 18
    produced_codes = {c for s in specs for c in s.produces}
    assert len(produced_codes) == 35
    for spec in specs:
        assert spec.fn is not None
        out = spec.fn(df)
        assert set(out.columns) == set(spec.produces)
