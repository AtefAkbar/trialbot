"""Trailing-stop ratchet: the core safety property is that the stop NEVER loosens
and that it tightens as profit grows."""
from bybitbot.config import Config
from bybitbot import trailing


def cfg():
    return Config(mode="paper")


def test_initial_stop_long_below_entry():
    c = cfg()
    s = trailing.initial_stop(100.0, +1, 2.0, c)
    assert s < 100.0
    assert abs(s - (100.0 - c.init_stop_atr * 2.0)) < 1e-9


def test_initial_stop_short_above_entry():
    c = cfg()
    s = trailing.initial_stop(100.0, -1, 2.0, c)
    assert s > 100.0


def test_stop_holds_before_breakeven():
    c = cfg()
    entry, atr = 100.0, 2.0
    stop0 = trailing.initial_stop(entry, +1, atr, c)
    rd = trailing.risk_per_unit(entry, stop0, +1)
    # tiny favourable move (< 1R): stop must not move
    new = trailing.next_stop(entry, +1, atr, peak=100.5, cur_stop=stop0, risk_dist=rd, cfg=c)
    assert new == stop0


def test_breakeven_locks_after_1R():
    c = cfg()
    entry, atr = 100.0, 2.0
    stop0 = trailing.initial_stop(entry, +1, atr, c)
    rd = trailing.risk_per_unit(entry, stop0, +1)
    peak = entry + 1.2 * rd                      # > 1R in profit
    new = trailing.next_stop(entry, +1, atr, peak, stop0, rd, c)
    assert new >= entry - 1e-9                    # at least breakeven


def test_ratchet_never_loosens_long():
    c = cfg()
    entry, atr = 100.0, 2.0
    stop = trailing.initial_stop(entry, +1, atr, c)
    rd = trailing.risk_per_unit(entry, stop, +1)
    peak = entry
    prev = stop
    for px in [100.5, 102, 104, 103, 106, 105, 110, 108]:   # includes pullbacks
        peak = max(peak, px)
        stop = trailing.next_stop(entry, +1, atr, peak, stop, rd, c)
        assert stop >= prev - 1e-12                # monotonic non-decreasing
        prev = stop


def test_ratchet_never_loosens_short():
    c = cfg()
    entry, atr = 100.0, 2.0
    stop = trailing.initial_stop(entry, -1, atr, c)
    rd = trailing.risk_per_unit(entry, stop, -1)
    peak = entry
    prev = stop
    for px in [99.5, 98, 96, 97, 94, 95, 90, 92]:
        peak = min(peak, px)
        stop = trailing.next_stop(entry, -1, atr, peak, stop, rd, c)
        assert stop <= prev + 1e-12                # monotonic non-increasing
        prev = stop


def test_band_tightens_with_profit():
    c = cfg()
    far = trailing._trail_band_atr(c.breakeven_at_r + 0.01, c)
    near = trailing._trail_band_atr(c.trail_tighten_r + 5, c)
    assert far > near                              # deeper profit => tighter band


def test_stop_hit_detection():
    assert trailing.stop_hit(+1, 99.0, 99.5) is True
    assert trailing.stop_hit(+1, 100.0, 99.5) is False
    assert trailing.stop_hit(-1, 101.0, 100.5) is True
    assert trailing.stop_hit(-1, 100.0, 100.5) is False
