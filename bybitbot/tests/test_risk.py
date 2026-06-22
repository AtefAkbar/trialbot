"""Risk sizing: the per-trade risk equals the configured fraction of equity, caps
bind, and profit scaling only ever raises risk above the floor while in profit."""
from bybitbot.config import Config
from bybitbot import risk


def test_risk_equals_fraction_of_equity():
    c = Config(mode="paper", account_size=1000.0, risk_per_trade=0.005,
               max_per_symbol=10, max_total_exposure=100, max_leverage=100, min_order_usd=1)
    entry, stop = 100.0, 98.0          # 1R = $2 per unit
    qty, notional, risk_usd = risk.size_trade(
        entry, stop, equity=1000, start_equity=1000, symbol_notional=0,
        total_notional=0, cash=1000, meta=None, cfg=c)
    # 0.5% of 1000 = $5 risk; $5 / $2 = 2.5 units
    assert abs(risk_usd - 5.0) < 1e-6
    assert abs(qty - 2.5) < 1e-6


def test_per_symbol_cap_binds():
    c = Config(mode="paper", account_size=1000.0, risk_per_trade=0.5,   # huge risk to force cap
               max_per_symbol=0.1, max_total_exposure=100, max_leverage=100, min_order_usd=1)
    entry, stop = 100.0, 99.0
    qty, notional, _ = risk.size_trade(entry, stop, 1000, 1000, 0, 0, 1e9, None, c)
    assert notional <= 0.1 * 1000 + 1e-6           # 10% of equity


def test_dust_rejected():
    c = Config(mode="paper", account_size=1000.0, risk_per_trade=0.005, min_order_usd=50)
    entry, stop = 100.0, 50.0          # 1R = $50 -> notional tiny
    qty, notional, _ = risk.size_trade(entry, stop, 1000, 1000, 0, 0, 1000, None, c)
    assert qty == 0.0


def test_scaling_only_in_profit():
    c = Config(mode="paper", risk_per_trade=0.005, risk_scale_max=2.0, scale_profit_ref=0.10)
    # at/under start equity -> floor
    assert risk.scaled_risk_frac(1000, 1000, c) == 0.005
    assert risk.scaled_risk_frac(900, 1000, c) == 0.005
    # +10% over start -> fully scaled to 2x floor
    assert abs(risk.scaled_risk_frac(1100, 1000, c) - 0.010) < 1e-9
    # +5% -> halfway
    assert abs(risk.scaled_risk_frac(1050, 1000, c) - 0.0075) < 1e-9


def test_pyramid_gate():
    c = Config(mode="paper", pyramid_enabled=True, pyramid_max_adds=2,
               breakeven_at_r=1.0, pyramid_trigger_r=1.0, max_total_exposure=100)
    pos = {"adds": 0, "peak_r": 0.5}
    assert risk.can_pyramid(pos, 1000, 0, c) is False         # not enough profit
    pos = {"adds": 0, "peak_r": 2.5}
    assert risk.can_pyramid(pos, 1000, 0, c) is True          # past first trigger
    pos = {"adds": 2, "peak_r": 9.0}
    assert risk.can_pyramid(pos, 1000, 0, c) is False         # add cap reached


def test_lot_step_rounding():
    c = Config(mode="paper", account_size=1000, risk_per_trade=0.005,
               max_per_symbol=10, max_total_exposure=100, max_leverage=100, min_order_usd=1)
    entry, stop = 100.0, 98.0
    meta = {"lot_step": 1.0, "min_qty": 1.0}      # whole units only
    qty, _, _ = risk.size_trade(entry, stop, 1000, 1000, 0, 0, 1000, meta, c)
    assert qty == 2.0                              # 2.5 rounded down to step 1.0
