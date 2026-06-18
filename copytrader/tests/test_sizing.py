"""Fixed-fraction sizing with per-market, total-exposure and cash caps."""
import os
from copytrader.config import Config
from copytrader.broker import PaperBroker
from copytrader.portfolio import Portfolio
from copytrader.risk import size_copy, stop_take_levels

TMP = "/tmp/ct_sizing_test_state.json"


def _portfolio(cfg):
    if os.path.exists(TMP):
        os.remove(TMP)
    return Portfolio(cfg, PaperBroker(0.0), path=TMP)


def test_base_fraction():
    cfg = Config(account_size=10_000, risk_per_copy=0.02)
    pf = _portfolio(cfg)
    notional, shares = size_copy(0.5, "A", pf, cfg)
    assert abs(notional - 200) < 1e-6        # 2% of 10k
    assert abs(shares - 400) < 1e-6          # 200 / 0.5


def test_per_market_cap():
    cfg = Config(account_size=10_000, risk_per_copy=0.02, max_per_market=0.03)
    pf = _portfolio(cfg)
    # already hold $250 of market A (cap is 3% = $300) -> only $50 headroom left
    pf.open("0xW", "A", 500, 0.5, ratio=1.0, sl=0.25, tp=1.0, meta={})
    notional, _ = size_copy(0.5, "A", pf, cfg)
    assert abs(notional - 50) < 1e-6


def test_total_exposure_cap():
    cfg = Config(account_size=10_000, risk_per_copy=0.50, max_total_exposure=0.10)
    pf = _portfolio(cfg)
    notional, _ = size_copy(0.5, "A", pf, cfg)
    assert abs(notional - 1000) < 1e-6       # capped to 10% total, not 50% desired


def test_below_min_order_skipped():
    # desired = 0.5% of $100 = $0.50, below the $1 venue minimum -> skip
    cfg = Config(account_size=100, risk_per_copy=0.005, min_order_usd=1.0)
    pf = _portfolio(cfg)
    assert size_copy(0.5, "A", pf, cfg) == (0.0, 0.0)


def test_zero_price_and_levels():
    cfg = Config()
    pf = _portfolio(cfg)
    assert size_copy(0.0, "A", pf, cfg) == (0.0, 0.0)
    sl, tp = stop_take_levels(0.5, Config(stop_loss_pct=0.5, take_profit_pct=1.0))
    assert abs(sl - 0.25) < 1e-9 and abs(tp - 1.0) < 1e-9


if __name__ == "__main__":
    test_base_fraction()
    test_per_market_cap()
    test_total_exposure_cap()
    test_below_min_order_skipped()
    test_zero_price_and_levels()
    print("test_sizing OK")
