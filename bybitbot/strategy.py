"""Per-symbol signal: HMA trend + SMC structure, confirmed on a higher timeframe.

Emits, for the LATEST closed bar only (causal, no look-ahead):
  Signal(symbol, side, price, atr, score)
where side is +1 long / -1 short / 0 none, and score ranks candidates across the
universe so the engine fills the strongest setups first.

The score rewards: trend agreement across timeframes, a fresh structural break
(BOS/CHoCH) in the trade direction, and price sitting in the favourable half of
the swing range (discount for longs, premium for shorts).
"""
from dataclasses import dataclass

import pandas as pd

from .indicators import hma_trend, smc_structure, atr


@dataclass
class Signal:
    symbol: str
    side: int          # +1 long, -1 short, 0 none
    price: float
    atr: float
    score: float
    trend: int
    note: str = ""


def _frame(klines):
    """klines rows: [start_ms, o, h, l, c, v, turnover] -> OHLCV DataFrame."""
    df = pd.DataFrame(klines, columns=["t", "open", "high", "low", "close", "volume", "turnover"])
    df["dt"] = pd.to_datetime(df["t"], unit="ms", utc=True)
    return df.set_index("dt")[["open", "high", "low", "close", "volume"]]


def _trend_last(close, cfg):
    trend, age, _ = hma_trend(close, cfg.hma_len, cfg.trend_len)
    return int(trend.iloc[-1]), int(age.iloc[-1])


def evaluate(symbol, entry_klines, confirm_klines, cfg):
    """Return a Signal for the latest bar. side=0 when no actionable setup."""
    if len(entry_klines) < max(cfg.hma_len, cfg.swing_len) * 2 + 5:
        return Signal(symbol, 0, 0.0, 0.0, 0.0, 0, "insufficient_bars")

    df = _frame(entry_klines)
    price = float(df["close"].iloc[-1])

    trend, age = _trend_last(df["close"], cfg)
    if trend == 0:
        return Signal(symbol, 0, price, 0.0, 0.0, 0, "no_trend")

    # higher-timeframe confirmation
    conf_trend = trend
    if cfg.require_confirm_tf and confirm_klines and len(confirm_klines) >= cfg.hma_len * 2:
        conf_trend, _ = _trend_last(_frame(confirm_klines)["close"], cfg)
        if conf_trend != trend:
            return Signal(symbol, 0, price, 0.0, 0.0, trend, "tf_disagree")

    smc = smc_structure(df, cfg.swing_len)
    a = float(atr(df, cfg.atr_period).iloc[-1])
    if not (a > 0):
        return Signal(symbol, 0, price, 0.0, 0.0, trend, "no_atr")

    struct = int(smc["struct_trend"].iloc[-1])
    pd_zone = float(smc["pd_zone"].iloc[-1])           # -1 discount .. +1 premium
    bos = int(smc["bos"].iloc[-1])
    choch = int(smc["choch"].iloc[-1])
    recent_break = int(smc["bos"].iloc[-3:].abs().max() or smc["choch"].iloc[-3:].abs().max() or 0)

    side = trend
    # structure must not actively oppose the trade
    if struct != 0 and struct != side:
        return Signal(symbol, 0, price, a, 0.0, trend, "struct_oppose")

    # ---- strength score (higher = fill first) ----
    score = 1.0
    if conf_trend == side:
        score += 1.0                                    # multi-TF agreement
    if (bos == side) or (choch == side):
        score += 1.0                                    # fresh break this bar in our favour
    elif recent_break == 1:
        score += 0.5
    # favour entries from the cheap side of the range
    loc = -pd_zone if side > 0 else pd_zone             # >0 means favourable location
    score += max(-0.5, min(1.0, loc))
    # penalise stale trends (mean-reversion risk grows with age)
    score += max(-0.5, 0.5 - age / 100.0)
    # normalise ATR as % so volatile junk doesn't dominate purely by structure
    atr_pct = a / price if price else 0
    if atr_pct > 0.03:
        score -= 0.5

    return Signal(symbol, side, price, a, round(score, 3), trend,
                  ("long" if side > 0 else "short") + f" age={age}")
