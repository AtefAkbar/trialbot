"""Trading universe: which symbols the bot is allowed to scan this cycle.

Enumerates every linear USDT perpetual, keeps only liquid ones (24h turnover
floor), applies any whitelist/blocklist, and ranks by turnover so the most
liquid names are scanned first under the per-cycle cap. Cached and refreshed
periodically to avoid hammering the API.
"""
import time
import logging

log = logging.getLogger("bybitbot")


class Universe:
    def __init__(self, cfg, api):
        self.cfg = cfg
        self.api = api
        self._symbols = []          # ranked list of {symbol, turnover, last, lot_step, min_qty, tick}
        self._last_refresh = 0.0

    def _instrument_filters(self):
        """symbol -> (qty_step, min_qty, tick_size) from instruments-info."""
        out = {}
        for it in self.api.instruments():
            if it.get("quoteCoin") != "USDT" or it.get("status") != "Trading":
                continue
            lot = it.get("lotSizeFilter", {})
            price = it.get("priceFilter", {})
            out[it["symbol"]] = (
                float(lot.get("qtyStep", lot.get("minOrderQty", 0)) or 0),
                float(lot.get("minOrderQty", 0) or 0),
                float(price.get("tickSize", 0) or 0),
            )
        return out

    def refresh(self, force=False):
        now = time.time()
        if not force and self._symbols and (now - self._last_refresh) < self.cfg.universe_refresh_s:
            return self._symbols

        wl = set(self.cfg.symbol_whitelist)
        bl = set(self.cfg.symbol_blocklist)
        try:
            filters = self._instrument_filters()
            rows = []
            for t in self.api.tickers():
                sym = t.get("symbol", "")
                if not sym.endswith("USDT") or sym in bl or sym not in filters:
                    continue
                if wl and sym not in wl:
                    continue
                turnover = float(t.get("turnover24h", 0) or 0)
                if not wl and turnover < self.cfg.min_turnover_usd:
                    continue
                step, min_qty, tick = filters[sym]
                rows.append({
                    "symbol": sym, "turnover": turnover,
                    "last": float(t.get("lastPrice", 0) or 0),
                    "lot_step": step, "min_qty": min_qty, "tick": tick,
                })
            rows.sort(key=lambda r: r["turnover"], reverse=True)
            self._symbols = rows[: self.cfg.max_universe]
            self._last_refresh = now
            log.info("universe: %d liquid symbols (scanning top %d)",
                     len(rows), len(self._symbols))
        except Exception as e:
            log.warning("universe refresh failed (%s); keeping %d cached", e, len(self._symbols))
        return self._symbols

    def symbols(self):
        return self.refresh()

    def meta(self, symbol):
        for r in self._symbols:
            if r["symbol"] == symbol:
                return r
        return None
