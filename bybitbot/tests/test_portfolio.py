"""Portfolio accounting: long/short PnL signs, fees, and the daily-loss tracker."""
from bybitbot.config import Config
from bybitbot.broker import PaperBroker
from bybitbot.portfolio import Portfolio


def _pf(tmp_path):
    c = Config(mode="paper", account_size=1000.0, taker_fee=0.0, slippage=0.0,
               state_path=str(tmp_path / "s.json"))
    return Portfolio(c, PaperBroker(c)), c


def test_long_profit(tmp_path):
    pf, c = _pf(tmp_path)
    pf.open("BTCUSDT", +1, qty=1.0, price=100.0, stop=98.0, atr=2.0, risk_dist=2.0)
    pf.mark({"BTCUSDT": 110.0})
    assert abs(pf.unrealized() - 10.0) < 1e-9
    pf.close("BTCUSDT", 110.0, "trailing_stop")
    assert abs(pf.realized_pnl - 10.0) < 1e-9
    assert abs(pf.equity() - 1010.0) < 1e-9


def test_short_profit(tmp_path):
    pf, c = _pf(tmp_path)
    pf.open("ETHUSDT", -1, qty=1.0, price=100.0, stop=102.0, atr=2.0, risk_dist=2.0)
    pf.mark({"ETHUSDT": 90.0})                      # price falls -> short gains
    assert abs(pf.unrealized() - 10.0) < 1e-9
    pf.close("ETHUSDT", 90.0, "trailing_stop")
    assert abs(pf.realized_pnl - 10.0) < 1e-9


def test_short_loss(tmp_path):
    pf, c = _pf(tmp_path)
    pf.open("ETHUSDT", -1, qty=1.0, price=100.0, stop=102.0, atr=2.0, risk_dist=2.0)
    pf.close("ETHUSDT", 105.0, "stop")             # price rose -> short loses
    assert abs(pf.realized_pnl + 5.0) < 1e-9


def test_fee_charged(tmp_path):
    c = Config(mode="paper", account_size=1000.0, taker_fee=0.001, slippage=0.0,
               state_path=str(tmp_path / "s.json"))
    pf = Portfolio(c, PaperBroker(c))
    pf.open("BTCUSDT", +1, qty=1.0, price=100.0, stop=98.0, atr=2.0, risk_dist=2.0)
    assert abs(pf.balance - (1000.0 - 0.1)) < 1e-9   # entry fee 0.1% of $100
    pf.close("BTCUSDT", 100.0, "x")
    # round-trip: two fees, no price move
    assert pf.realized_pnl < 0


def test_peak_tracks_favourable(tmp_path):
    pf, c = _pf(tmp_path)
    pf.open("BTCUSDT", +1, qty=1.0, price=100.0, stop=98.0, atr=2.0, risk_dist=2.0)
    pf.mark({"BTCUSDT": 105.0})
    pf.mark({"BTCUSDT": 103.0})                     # pullback
    assert pf.positions["BTCUSDT"]["peak"] == 105.0


def test_day_loss_frac(tmp_path):
    pf, c = _pf(tmp_path)
    pf.open("BTCUSDT", +1, qty=10.0, price=100.0, stop=98.0, atr=2.0, risk_dist=2.0)
    pf.close("BTCUSDT", 98.0, "stop")              # -$20 on equity ~ -2%
    assert pf.day_loss_frac() < 0


def test_persistence_roundtrip(tmp_path):
    pf, c = _pf(tmp_path)
    pf.open("BTCUSDT", +1, qty=1.0, price=100.0, stop=98.0, atr=2.0, risk_dist=2.0)
    pf.save()
    pf2 = Portfolio(c, PaperBroker(c))
    assert pf2.has("BTCUSDT")
    assert abs(pf2.balance - pf.balance) < 1e-9
