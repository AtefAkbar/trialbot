"""Vendored, self-contained indicator library (HMA trend, SMC swing structure, ATR).

Distilled from the backtest suite's Pine-script ports and inlined here so the
bybitbot package is fully self-contained — it does NOT depend on the untracked
altcoin_backtest/ folder, which means it deploys cleanly from a fresh clone.

All causal: a signal at bar t uses only data <= t (no look-ahead).
"""
import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# 1. HMA TREND  (ChartPrime)
# ----------------------------------------------------------------------------
def _wma(s, n):
    w = np.arange(1, n + 1, dtype=float)
    return s.rolling(n).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)


def hma(close, length):
    half = max(1, int(length / 2))
    sq = max(1, int(np.sqrt(length)))
    return _wma(2 * _wma(close, half) - _wma(close, length), sq)


def hma_trend(close, length=50, trend_len=3):
    """Returns (trend[+1/-1], trend_age_bars, hma_series).
    Trend flips up when HMA has risen trend_len bars in a row, down when fallen."""
    h = hma(close, length)
    rising = h.diff() > 0
    falling = h.diff() < 0
    up = rising.rolling(trend_len).sum() == trend_len
    dn = falling.rolling(trend_len).sum() == trend_len
    trend = pd.Series(np.nan, index=close.index)
    trend[up] = 1
    trend[dn] = -1
    trend = trend.ffill().fillna(0)
    flip = trend != trend.shift()
    grp = flip.cumsum()
    age = trend.groupby(grp).cumcount() + 1
    return trend, age, h


# ----------------------------------------------------------------------------
# 2. SMC SWING STRUCTURE  (LuxAlgo essence)
# ----------------------------------------------------------------------------
def swing_pivots(df, length=20):
    """Confirmed swing highs/lows. A pivot at bar i is confirmed `length` bars later.
    Returns arrays of confirmed pivot prices aligned to the confirmation bar (causal)."""
    high = df["high"].values
    low = df["low"].values
    n = len(df)
    piv_hi = np.full(n, np.nan)
    piv_lo = np.full(n, np.nan)
    for i in range(2 * length, n):
        c = i - length  # candidate center
        if high[c] == high[c - length:i + 1].max():
            piv_hi[i] = high[c]
        if low[c] == low[c - length:i + 1].min():
            piv_lo[i] = low[c]
    return piv_hi, piv_lo


def smc_structure(df, length=20):
    """Break-of-structure / change-of-character state machine + premium/discount.
    Returns DataFrame with:
      struct_trend (+1/-1) : structural bias
      choch (+1/-1/0)      : reversal break on this bar
      bos   (+1/-1/0)      : continuation break on this bar
      last_hi, last_lo     : current swing range
      pd_zone (-1..+1)     : where close sits in swing range (-1 discount, +1 premium)
    """
    close = df["close"].values
    n = len(df)
    piv_hi, piv_lo = swing_pivots(df, length)

    last_hi = np.full(n, np.nan)
    last_lo = np.full(n, np.nan)
    struct = np.zeros(n)
    choch = np.zeros(n)
    bos = np.zeros(n)

    cur_hi = np.nan
    cur_lo = np.nan
    hi_crossed = False
    lo_crossed = False
    bias = 0
    for i in range(n):
        if not np.isnan(piv_hi[i]):
            cur_hi = piv_hi[i]; hi_crossed = False
        if not np.isnan(piv_lo[i]):
            cur_lo = piv_lo[i]; lo_crossed = False
        if not np.isnan(cur_hi) and close[i] > cur_hi and not hi_crossed:
            hi_crossed = True
            if bias == -1:
                choch[i] = 1
            else:
                bos[i] = 1
            bias = 1
        if not np.isnan(cur_lo) and close[i] < cur_lo and not lo_crossed:
            lo_crossed = True
            if bias == 1:
                choch[i] = -1
            else:
                bos[i] = -1
            bias = -1
        struct[i] = bias
        last_hi[i] = cur_hi
        last_lo[i] = cur_lo

    rng = last_hi - last_lo
    mid = (last_hi + last_lo) / 2.0
    with np.errstate(invalid="ignore", divide="ignore"):
        pd_zone = np.where(rng > 0, (close - mid) / (rng / 2.0), 0.0)
    pd_zone = np.clip(pd_zone, -1.5, 1.5)
    return pd.DataFrame({
        "struct_trend": struct, "choch": choch, "bos": bos,
        "last_hi": last_hi, "last_lo": last_lo, "pd_zone": pd_zone,
    }, index=df.index)


# ----------------------------------------------------------------------------
# 3. ATR
# ----------------------------------------------------------------------------
def atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()
