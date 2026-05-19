"""Indicator registry and ``@indicator`` decorator.

Every indicator implementation registers itself by decorating its
compute function::

    @indicator(
        code="rsi_14",
        family="rsi_14",
        category="momentum",
        params={"window": 14},
        produces=["rsi_14"],
    )
    def rsi_14(df: pd.DataFrame) -> pd.DataFrame:
        ...

The decorator inserts an :class:`IndicatorSpec` into the module-level
registry.  The engine iterates the registry — there is no manual list
to keep in sync, and the catalog table is seeded by reading the same
registry, so the in-code and in-DB worldviews can never drift.

Why a decorator rather than subclassing :class:`DataSource`?  These are
pure functions with no per-instance state.  A decorator pattern keeps
the call-site noise low and lets mypy fully type-check the function
signature, which class inheritance hides behind ``self``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

# Compute function signature: takes an OHLCV DataFrame (DatetimeIndex,
# columns open/high/low/close/adj_close/volume) and returns a DataFrame
# with one column per produced ``indicator_code``.  Index is preserved
# verbatim from the input — rows where the indicator is undefined
# carry NaN values, which the snapshot writer skips at upsert time.
ComputeFn = Callable[[pd.DataFrame], pd.DataFrame]


@dataclass(frozen=True)
class IndicatorSpec:
    """Metadata for a single registered indicator function.

    Fields mirror the columns of ``indicators_catalog``; the catalog
    seed script reads these directly.
    """

    code: str
    family: str
    category: str  # trend / momentum / volume / volatility / support_resistance
    params: dict[str, Any]
    # The list of `indicator_code`s this function emits.  Single-component
    # indicators (RSI) have a single-element list matching `code`;
    # multi-component indicators (MACD, Bollinger, Stochastic) emit
    # several distinct codes from one function (avoids recomputing the
    # underlying EMAs three times for MACD).
    produces: list[str]
    # Component label per produced code (parallel to `produces`).  None
    # for single-component indicators.
    components: list[str | None] = field(default_factory=list)
    # Math-implementation version.  Bumped when an output-changing fix
    # is shipped so the rebuild job can reproduce snapshots cleanly.
    version: int = 1
    # The decorated callable.  Set by the decorator; not user-supplied.
    fn: ComputeFn | None = None


# Module-level registry.  Populated at import time by the decorator;
# read by the engine and the catalog seed script.
_REGISTRY: dict[str, IndicatorSpec] = {}


def indicator(
    *,
    code: str,
    family: str,
    category: str,
    params: dict[str, Any] | None = None,
    produces: list[str] | None = None,
    components: list[str | None] | None = None,
    version: int = 1,
) -> Callable[[ComputeFn], ComputeFn]:
    """Decorator that registers an indicator compute function.

    Parameters
    ----------
    code
        Primary indicator code.  For multi-component indicators this is
        the *first* component's code (e.g., ``"macd_12_26_9_line"``)
        and the full set is listed in ``produces``.  Used as the dict
        key in the registry — must be unique.
    family
        Logical grouping for UI display.  All MACD components share
        ``family = "macd_12_26_9"``.
    category
        One of ``"trend"`` / ``"momentum"`` / ``"volume"`` /
        ``"volatility"`` / ``"support_resistance"``.  Matches the plan's
        grouping.
    params
        Parameter dict (e.g., ``{"window": 14}``).  Captured verbatim
        into ``indicators_catalog.params_json``.
    produces
        Every ``indicator_code`` this function emits.  Defaults to
        ``[code]`` for single-component indicators.
    components
        Parallel list of component labels (``"line"``, ``"signal"``,
        ``"hist"``…) for the produced codes.  ``None`` entries indicate
        single-component output.
    version
        Math-implementation version.  Bump when a fix changes outputs.

    Returns
    -------
    Callable
        Decorator that registers the function and returns it untouched.
        Keeping the function reference unchanged lets unit tests call
        it directly (``rsi_14(df)``) without going through the registry.
    """
    if params is None:
        params = {}
    if produces is None:
        produces = [code]
    if components is None:
        components = [None] * len(produces)
    if len(components) != len(produces):  # pragma: no cover - dev-time bug
        raise ValueError(
            f"@indicator({code!r}): components length {len(components)} "
            f"does not match produces length {len(produces)}"
        )

    def decorator(fn: ComputeFn) -> ComputeFn:
        # The registry key is `code` (the primary code).  For multi-
        # component indicators we register the *whole spec* once under
        # the primary code; the catalog seed walks `produces` to emit
        # a catalog row per component.
        if code in _REGISTRY:  # pragma: no cover - dev-time bug
            raise RuntimeError(f"indicator {code!r} already registered")
        spec = IndicatorSpec(
            code=code,
            family=family,
            category=category,
            params=params,
            produces=list(produces),
            components=list(components),
            version=version,
            fn=fn,
        )
        _REGISTRY[code] = spec
        return fn

    return decorator


def all_specs() -> list[IndicatorSpec]:
    """Return every registered :class:`IndicatorSpec`.

    Result is stable-ordered by ``code`` so output across catalog seed
    runs, engine runs, and tests is reproducible.
    """
    return sorted(_REGISTRY.values(), key=lambda s: s.code)


def get(code: str) -> IndicatorSpec:
    """Look up a single spec by code.  Raises ``KeyError`` if missing."""
    return _REGISTRY[code]


__all__: list[str] = [
    "ComputeFn",
    "IndicatorSpec",
    "all_specs",
    "get",
    "indicator",
]
