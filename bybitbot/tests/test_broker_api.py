"""Broker gating + Bybit V5 request signing."""
import hmac
import hashlib
import pytest

from bybitbot.config import Config
from bybitbot.broker import make_broker, LiveBroker, PaperBroker, TestnetBroker
from bybitbot.bybit_api import BybitAPI


def test_paper_broker_selected_by_default():
    b = make_broker(Config(mode="paper"), api=None)
    assert isinstance(b, PaperBroker) and not b.live


def test_testnet_broker_selected():
    b = make_broker(Config(mode="testnet"), api=None)
    assert isinstance(b, TestnetBroker) and not b.live


def test_live_broker_gated_without_confirm():
    cfg = Config(mode="live", api_key="k", api_secret="s")  # confirm_live defaults False
    with pytest.raises(RuntimeError):
        make_broker(cfg, api=None)


def test_live_broker_gated_without_keys():
    cfg = Config(mode="live")
    cfg.confirm_live = True                                  # confirmed but no keys
    with pytest.raises(RuntimeError):
        LiveBroker(cfg, api=None)


def test_live_broker_enabled_with_confirm_and_keys():
    cfg = Config(mode="live", api_key="k", api_secret="s")
    cfg.confirm_live = True
    b = LiveBroker(cfg, api=object())
    assert b.live is True


def test_paper_fill_applies_adverse_slippage():
    cfg = Config(mode="paper", slippage=0.01)
    b = PaperBroker(cfg)
    assert b.fill(+1, 100.0) == pytest.approx(101.0)        # pay up to buy
    assert b.fill(-1, 100.0) == pytest.approx(99.0)         # get less to sell


def test_v5_signature_matches_reference():
    cfg = Config(mode="testnet", api_key="APIKEY", api_secret="SECRET", recv_window=5000)
    api = BybitAPI(cfg)
    ts = "1700000000000"
    payload = "category=linear&symbol=BTCUSDT"
    got = api._sign(ts, payload)
    pre = f"{ts}{cfg.api_key}{cfg.recv_window}{payload}"
    want = hmac.new(b"SECRET", pre.encode(), hashlib.sha256).hexdigest()
    assert got == want and len(got) == 64


def test_klines_oldest_first():
    """klines() must flip Bybit's newest-first list to oldest-first floats."""
    cfg = Config(mode="testnet")

    class FakeAPI(BybitAPI):
        def _get_public(self, path, params=None, tries=4):
            # Bybit returns newest-first
            return {"list": [
                ["1002", "2", "2", "2", "2", "2", "2"],
                ["1001", "1", "1", "1", "1", "1", "1"],
            ]}

    out = FakeAPI(cfg).klines("BTCUSDT", "5", 2)
    assert out[0][0] == 1001 and out[1][0] == 1002          # oldest first
    assert isinstance(out[0][1], float)
