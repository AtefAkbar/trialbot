"""Execution brokers — one interface, three modes.

PaperBroker   : pure local simulation (adverse slippage + taker fee). No account.
TestnetBroker : sends REAL orders to Bybit TESTNET (fake money). Proves the wire.
LiveBroker    : sends REAL orders with REAL money. Deliberately gated — it raises
                unless the user themselves set BYBIT_CONFIRM_LIVE=1 AND supplied
                API keys. Even then, the engine routes through the same fill()
                accounting so paper == testnet == live behaviour stays identical.

fill() returns the effective fill price; the portfolio does all PnL accounting.
side: +1 buy, -1 sell.
"""
import logging

log = logging.getLogger("bybitbot")


class PaperBroker:
    live = False
    mode = "paper"

    def __init__(self, cfg, api=None):
        self.cfg = cfg
        self.api = api

    def fill(self, side, price):
        """Adverse slippage: pay up to buy, get less to sell."""
        return price * (1.0 + self.cfg.slippage * side)

    # paper never touches the exchange
    def submit(self, symbol, side, qty, reduce_only=False):
        return {"simulated": True}

    def protect(self, symbol, stop_loss):
        return {"simulated": True}


class TestnetBroker(PaperBroker):
    """Mirrors PaperBroker accounting but also places a real testnet order so the
    full API path (auth, qty rounding, fills) is exercised against Bybit."""
    live = False
    mode = "testnet"

    def submit(self, symbol, side, qty, reduce_only=False):
        bside = "Buy" if side > 0 else "Sell"
        try:
            res = self.api.place_order(symbol, bside, qty, reduce_only=reduce_only)
            if isinstance(res, dict) and res.get("_error"):
                log.warning("testnet order rejected %s %s %s: %s", bside, qty, symbol, res["_error"])
            return res
        except Exception as e:
            log.warning("testnet order error %s %s: %s", bside, symbol, e)
            return {"_error": str(e)}

    def protect(self, symbol, stop_loss):
        try:
            return self.api.set_trading_stop(symbol, stop_loss)
        except Exception as e:
            log.debug("testnet protect error %s: %s", symbol, e)
            return {"_error": str(e)}


class LiveBroker(TestnetBroker):
    """REAL money. Gated behind explicit user opt-in; never enabled by default."""
    live = True
    mode = "live"

    def __init__(self, cfg, api=None):
        if not (cfg.confirm_live and cfg.api_key and cfg.api_secret):
            raise RuntimeError(
                "LiveBroker is disabled. To trade real money you must set "
                "BYBIT_CONFIRM_LIVE=1 AND provide BYBIT_API_KEY/BYBIT_API_SECRET "
                "yourself. This is an intentional safety gate."
            )
        super().__init__(cfg, api)
        log.warning("LIVE BROKER ENABLED — real orders, real money.")


def make_broker(cfg, api):
    if cfg.mode == "live":
        return LiveBroker(cfg, api)
    if cfg.mode == "testnet":
        return TestnetBroker(cfg, api)
    return PaperBroker(cfg, api)
