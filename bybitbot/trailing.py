"""The ratcheting trailing stop — the heart of the strategy.

Behaviour the user asked for:
  * small initial stop  -> losers are cut quickly,
  * once a trade is +1R in profit, lock breakeven so a winner can't become a loser,
  * beyond that, trail behind the best price by an ATR band that TIGHTENS as
    profit grows (wide early to let it breathe, tight late to bank gains),
  * the stop only ever ratchets toward profit — it can never loosen.

All pure functions over primitives so they're trivially unit-tested. `side` is
+1 for long, -1 for short. Prices are absolute; ATR is in price units.
"""


def initial_stop(entry, side, atr, cfg):
    """Tight initial protective stop placed init_stop_atr*ATR away from entry."""
    return entry - side * cfg.init_stop_atr * atr


def risk_per_unit(entry, stop, side):
    """Absolute price risk per unit between entry and the (initial) stop = 1R."""
    return abs(entry - stop)


def r_multiple(entry, peak, risk_dist, side):
    """How many R of favourable excursion the position has reached at `peak`."""
    if risk_dist <= 0:
        return 0.0
    return (peak - entry) * side / risk_dist


def _trail_band_atr(r, cfg):
    """ATR multiple for the trail band at profit level `r` (in R).
    Linearly tightens from trail_atr_far (at breakeven_at_r) to trail_atr_near
    (at trail_tighten_r), then stays near."""
    lo_r, hi_r = cfg.breakeven_at_r, cfg.trail_tighten_r
    far, near = cfg.trail_atr_far, cfg.trail_atr_near
    if r <= lo_r:
        return far
    if r >= hi_r or hi_r <= lo_r:
        return near
    frac = (r - lo_r) / (hi_r - lo_r)
    return far + (near - far) * frac


def next_stop(entry, side, atr, peak, cur_stop, risk_dist, cfg):
    """Return the new stop after this bar. Ratchets toward profit, never away.

    entry      : weighted-avg entry price
    side       : +1 long / -1 short
    atr        : current ATR (price units)
    peak       : best favourable price reached so far (max for long, min for short)
    cur_stop   : the stop currently in force
    risk_dist  : 1R in price units (from the initial stop)
    """
    r = r_multiple(entry, peak, risk_dist, side)

    if r < cfg.breakeven_at_r:
        candidate = cur_stop                      # still in the initial-stop regime
    elif r < cfg.breakeven_at_r + 1e-9:
        candidate = entry                         # exactly at breakeven trigger
    else:
        band = _trail_band_atr(r, cfg) * atr
        trail = peak - side * band
        breakeven = entry
        # never give back more than breakeven once we're past the trigger
        candidate = max(trail, breakeven) if side > 0 else min(trail, breakeven)

    # ratchet: a long stop only rises, a short stop only falls
    if side > 0:
        return max(cur_stop, candidate)
    return min(cur_stop, candidate)


def stop_hit(side, price, stop):
    """True once price trades through the stop (long: at/below; short: at/above)."""
    return price <= stop if side > 0 else price >= stop
