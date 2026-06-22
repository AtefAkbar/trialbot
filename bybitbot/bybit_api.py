"""Bybit V5 REST client.

Public market data needs no auth. Private endpoints are signed with
HMAC-SHA256 over (timestamp + api_key + recv_window + payload), per Bybit V5.

Read-only by default. The only state-changing calls — place_order and
set_trading_stop — are used by the Live/Testnet brokers, never here directly.

Reference: https://bybit-exchange.github.io/docs/v5/intro
"""
import time
import hmac
import json
import hashlib
import logging
from urllib.parse import urlencode

import requests

log = logging.getLogger("bybitbot")

# Bybit kline shape: [start, open, high, low, close, volume, turnover] (strings)


class BybitAPI:
    def __init__(self, cfg, session=None):
        self.cfg = cfg
        self.base = cfg.base_url
        self.s = session or requests.Session()
        self.s.headers.update({"User-Agent": "bybitbot/1.0"})

    # ---- low-level transport -------------------------------------------------
    def _get_public(self, path, params=None, tries=4):
        for i in range(tries):
            try:
                r = self.s.get(self.base + path, params=params or {}, timeout=20)
                if r.status_code == 200:
                    body = r.json()
                    if body.get("retCode") == 0:
                        return body["result"]
                    log.warning("bybit %s retCode=%s %s", path, body.get("retCode"), body.get("retMsg"))
                time.sleep(0.6 * (i + 1))
            except Exception as e:
                log.debug("public %s error: %s", path, e)
                time.sleep(0.6 * (i + 1))
        raise RuntimeError(f"bybit public failed: {path} {params}")

    def _sign(self, ts, payload):
        """V5 signature: HMAC_SHA256(secret, ts + api_key + recv_window + payload)."""
        pre = f"{ts}{self.cfg.api_key}{self.cfg.recv_window}{payload}"
        return hmac.new(self.cfg.api_secret.encode(), pre.encode(), hashlib.sha256).hexdigest()

    def _signed(self, method, path, params=None, tries=3):
        if not (self.cfg.api_key and self.cfg.api_secret):
            raise RuntimeError("signed request needs BYBIT_API_KEY / BYBIT_API_SECRET")
        params = params or {}
        for i in range(tries):
            ts = str(int(time.time() * 1000))
            if method == "GET":
                payload = urlencode(sorted(params.items()))
                sign = self._sign(ts, payload)
                url = self.base + path + ("?" + payload if payload else "")
                body = None
            else:
                payload = json.dumps(params, separators=(",", ":"))
                sign = self._sign(ts, payload)
                url = self.base + path
                body = payload
            headers = {
                "X-BAPI-API-KEY": self.cfg.api_key,
                "X-BAPI-TIMESTAMP": ts,
                "X-BAPI-RECV-WINDOW": str(self.cfg.recv_window),
                "X-BAPI-SIGN": sign,
                "Content-Type": "application/json",
            }
            try:
                if method == "GET":
                    r = self.s.get(url, headers=headers, timeout=20)
                else:
                    r = self.s.post(url, headers=headers, data=body, timeout=20)
                resp = r.json()
                if resp.get("retCode") == 0:
                    return resp.get("result", {})
                log.warning("bybit signed %s retCode=%s %s", path, resp.get("retCode"), resp.get("retMsg"))
                # non-retryable business errors (e.g. insufficient balance) bubble up
                return {"_error": resp.get("retMsg"), "_code": resp.get("retCode")}
            except Exception as e:
                log.debug("signed %s error: %s", path, e)
                time.sleep(0.5 * (i + 1))
        raise RuntimeError(f"bybit signed failed: {path}")

    # ---- public market data --------------------------------------------------
    def instruments(self):
        """All tradable linear instruments. Returns list of dicts (symbol, lot/tick filters)."""
        res = self._get_public("/v5/market/instruments-info", {"category": self.cfg.category, "limit": 1000})
        return res.get("list", [])

    def tickers(self):
        """24h ticker snapshot for the whole category: last price + turnover (liquidity)."""
        res = self._get_public("/v5/market/tickers", {"category": self.cfg.category})
        return res.get("list", [])

    def klines(self, symbol, interval, limit=200):
        """Recent OHLCV. Returns rows OLDEST-first as
        [start_ms, open, high, low, close, volume, turnover] floats."""
        res = self._get_public("/v5/market/kline", {
            "category": self.cfg.category, "symbol": symbol,
            "interval": interval, "limit": limit,
        })
        rows = res.get("list", [])
        out = []
        for r in reversed(rows):           # Bybit returns newest-first; flip to oldest-first
            out.append([int(r[0])] + [float(x) for x in r[1:7]])
        return out

    def last_price(self, symbol):
        res = self._get_public("/v5/market/tickers", {"category": self.cfg.category, "symbol": symbol})
        lst = res.get("list", [])
        return float(lst[0]["lastPrice"]) if lst else 0.0

    # ---- private (signed) ----------------------------------------------------
    def wallet_balance(self, coin="USDT"):
        res = self._signed("GET", "/v5/account/wallet-balance",
                            {"accountType": "UNIFIED", "coin": coin})
        try:
            return float(res["list"][0]["coin"][0]["walletBalance"])
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    def positions(self, settle_coin="USDT"):
        res = self._signed("GET", "/v5/position/list",
                           {"category": self.cfg.category, "settleCoin": settle_coin})
        return res.get("list", []) if isinstance(res, dict) else []

    def place_order(self, symbol, side, qty, reduce_only=False, order_type="Market"):
        """side: 'Buy'|'Sell'. Market order by default. Returns the signed-call result."""
        return self._signed("POST", "/v5/order/create", {
            "category": self.cfg.category, "symbol": symbol, "side": side,
            "orderType": order_type, "qty": str(qty),
            "reduceOnly": reduce_only, "timeInForce": "IOC",
        })

    def set_trading_stop(self, symbol, stop_loss):
        """Server-side stop as a safety net for live: if our process dies, the
        exchange still protects the position."""
        return self._signed("POST", "/v5/position/trading-stop", {
            "category": self.cfg.category, "symbol": symbol,
            "stopLoss": str(stop_loss), "positionIdx": 0,
        })
