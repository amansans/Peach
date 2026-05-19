"""Volume indicators: OBV, Anchored VWAP (52-week low/high), A/D Line.

About Anchored VWAP
-------------------
True intraday VWAP requires tick-level volume/price data that no free
EOD source provides.  Per the architectural plan, we substitute
*Anchored VWAP*: a cumulative volume-weighted average price starting
from a chosen anchor bar.

The plan picks two natural anchors for every ticker:

* the 52-week low (the "this much higher than the bottom" benchmark);
* the 52-week high (the "this much above the recent peak" benchmark).

Each emits its own indicator code.  The UI should display the chosen
anchor explicitly (the indicator label includes "from 52-wk low/high")
so users aren't misled into thinking they're seeing institutional
intraday VWAP.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from peach.indicators.registry import indicator

# ---------------------------------------------------------------------------
# OBV — On-Balance Volume
# ---------------------------------------------------------------------------


@indicator(
    code="obv",
    family="obv",
    category="volume",
    params={},
    produces=["obv"],
)
def obv(df: pd.DataFrame) -> pd.DataFrame:
    """On-Balance Volume.

    ::

        OBV_t = OBV_{t-1} + sign(close_t - close_{t-1}) * volume_t

    Initial bar starts at 0.  OBV is cumulative — values can reach the
    high 10^12 range for large mega-cap names, which is why
    ``indicator_snapshots.value`` is ``NUMERIC(28, 12)``.
    """
    direction = np.sign(df["close"].diff().fillna(0))
    signed = direction * df["volume"]
    return pd.DataFrame({"obv": signed.cumsum()})


# ---------------------------------------------------------------------------
# A/D Line — Accumulation / Distribution
# ---------------------------------------------------------------------------


@indicator(
    code="ad_line",
    family="ad_line",
    category="volume",
    params={},
    produces=["ad_line"],
)
def ad_line(df: pd.DataFrame) -> pd.DataFrame:
    """Chaikin Accumulation/Distribution Line.

    ::

        MFM = ((close - low) - (high - close)) / (high - low)
        MFV = MFM * volume
        AD  = cumsum(MFV)

    Where ``high == low`` (flat bar), ``MFM`` is conventionally 0.
    """
    rng = df["high"] - df["low"]
    mfm = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / rng.where(rng != 0)
    mfm = mfm.fillna(0)  # Flat bars contribute zero volume flow.
    mfv = mfm * df["volume"]
    return pd.DataFrame({"ad_line": mfv.cumsum()})


# ---------------------------------------------------------------------------
# Anchored VWAP — anchored to the 52-week low and 52-week high
# ---------------------------------------------------------------------------


def _anchored_vwap(df: pd.DataFrame, anchor_dates: pd.Series) -> pd.Series:
    """Cumulative VWAP recomputed from each bar's ``anchor_date``.

    Implementation
    --------------
    For every row, we know the anchor date that row "belongs to" (i.e.,
    the most recent 52-week low or high *as of* that row).  When that
    anchor date changes from one bar to the next, the cumulative sums
    must restart.  Groupby-on-anchor handles this naturally.

    Returns a Series aligned to ``df.index``.
    """
    # Typical price for VWAP is (high + low + close) / 3.
    typical = (df["high"] + df["low"] + df["close"]) / 3
    tpv = typical * df["volume"]

    # Pair each row with its anchor date and group.  Within each group
    # the cumulative volume-weighted average resets to the anchor bar.
    groups = anchor_dates
    cum_tpv = tpv.groupby(groups).cumsum()
    cum_vol = df["volume"].groupby(groups).cumsum()
    return cum_tpv / cum_vol.where(cum_vol != 0)


@indicator(
    code="avwap_low_252",
    family="avwap_anchored",
    category="volume",
    params={"window": 252, "anchor": "low"},
    produces=["avwap_low_252"],
    components=["from_52w_low"],
)
def avwap_low_252(df: pd.DataFrame) -> pd.DataFrame:
    """Anchored VWAP from the rolling 252-bar (≈ 52-week) low.

    For each row, the anchor is the date on which the lowest low in
    the *trailing* 252 bars occurred.  When a new low is set, the
    anchor moves and the cumulative sums restart from that new bar.
    """
    # `argmin` on a rolling window returns the OFFSET within the
    # window; convert to an index date for the groupby.
    rolling_low_idx = (
        df["low"]
        .rolling(window=252)
        .apply(
            lambda w: float(int(w.values.argmin())) - (len(w) - 1),
            raw=False,
        )
    )
    # The offset is negative (oldest bar is -(window-1)); add the
    # absolute integer index to get the actual position.
    pos = np.arange(len(df)) + rolling_low_idx.fillna(0).astype(int)
    pos = pos.clip(lower=0, upper=len(df) - 1)
    anchor_dates = pd.Series(df.index.values[pos], index=df.index)
    # Mask out the warmup period where the rolling window is short of
    # 252 bars.
    valid = rolling_low_idx.notna()
    out = _anchored_vwap(df, anchor_dates)
    return pd.DataFrame({"avwap_low_252": out.where(valid)})


@indicator(
    code="avwap_high_252",
    family="avwap_anchored",
    category="volume",
    params={"window": 252, "anchor": "high"},
    produces=["avwap_high_252"],
    components=["from_52w_high"],
)
def avwap_high_252(df: pd.DataFrame) -> pd.DataFrame:
    """Anchored VWAP from the rolling 252-bar (≈ 52-week) high.

    Mirror of :func:`avwap_low_252` but anchored to the most recent
    rolling high.
    """
    rolling_high_idx = (
        df["high"]
        .rolling(window=252)
        .apply(
            lambda w: float(int(w.values.argmax())) - (len(w) - 1),
            raw=False,
        )
    )
    pos = np.arange(len(df)) + rolling_high_idx.fillna(0).astype(int)
    pos = pos.clip(lower=0, upper=len(df) - 1)
    anchor_dates = pd.Series(df.index.values[pos], index=df.index)
    valid = rolling_high_idx.notna()
    out = _anchored_vwap(df, anchor_dates)
    return pd.DataFrame({"avwap_high_252": out.where(valid)})
