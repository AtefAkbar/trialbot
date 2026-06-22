"""The closed loop.

Each cycle:
  1. refresh the tradable universe (periodically).
  2. mark open positions, ratchet their trailing stops, exit on stop/trend-flip,
     pyramid into winners.
  3. evaluate circuit breakers (daily-loss / max-drawdown / pause).
  4. if there's room, scan the universe, rank setups, open the strongest.
  5. persist state, log a summary, sleep.

Mode-agnostic: paper/testnet/live differ only in the broker. The trailing-stop
and risk logic are identical across modes so what you forward-test is what runs.
"""
import time
import logging

from .bybit_api import BybitAPI
from .universe import Universe
from .broker import make_broker
from .portfolio import Portfolio
from . import strategy, trailing, risk
from .control import CONTROL

log = logging.getLogger("bybitbot")


class Engine:
    def __init__(self, cfg, api=None, control=CONTROL):
        self.cfg = cfg
        self.api = api or BybitAPI(cfg)
        self.broker = make_broker(cfg, self.api)
        self.universe = Universe(cfg, self.api)
        self.portfolio = Portfolio(cfg, self.broker)
        self.control = control
        self.scanner = []          # last scan ranking, surfaced to the dashboard
        self.halt_reason = ""

    # ---- pricing -------------------------------------------------------------
    def _price(self, symbol, fallback=0.0):
        try:
            px = self.api.last_price(symbol)
            return px if px > 0 else fallback
        except Exception:
            return fallback

    # ---- one cycle -----------------------------------------------------------
    def cycle(self):
        now = time.time()
        self.universe.refresh()

        if self.control.take_flatten():
            self._flatten_all()

        self._manage()
        self._check_breakers()

        if self._can_enter():
            self._scan_and_enter()

        self.portfolio.record_equity(now)
        self.portfolio.save()
        s = self.portfolio.summary()
        log.info("[%s] equity=$%.2f bal=$%.2f open=%d exposure=$%.2f uPnL=$%.2f rPnL=$%.2f %s",
                 self.cfg.mode, s["equity"], s["balance"], s["open_positions"],
                 s["open_notional"], s["unrealized"], s["realized"],
                 ("HALT:" + self.halt_reason) if self.halt_reason else "")

    # ---- manage open book ----------------------------------------------------
    def _manage(self):
        if not self.portfolio.positions:
            return
        prices = {sym: self._price(sym, p.get("cur_price") or p["entry"])
                  for sym, p in list(self.portfolio.positions.items())}
        self.portfolio.mark(prices)

        for sym, p in list(self.portfolio.positions.items()):
            px = p["cur_price"]
            if px <= 0:
                continue
            side = p["side"]
            # ratchet the trailing stop and refresh the position's R progress
            new_stop = trailing.next_stop(p["entry"], side, p["atr"], p["peak"],
                                          p["stop"], p["risk_dist"], self.cfg)
            p["stop"] = new_stop
            p["peak_r"] = trailing.r_multiple(p["entry"], p["peak"], p["risk_dist"], side)

            if trailing.stop_hit(side, px, new_stop):
                self.portfolio.close(sym, px, "trailing_stop")
                self.broker.protect(sym, new_stop)   # no-op for paper
                log.info("EXIT %s %s @ %.6f (trailing_stop, %.2fR peak)",
                         sym, "long" if side > 0 else "short", px, p["peak_r"])
                continue

            # trend-flip exit: bail if the entry-TF trend turns against us
            if self._trend_against(sym, side):
                self.portfolio.close(sym, px, "trend_flip")
                log.info("EXIT %s @ %.6f (trend_flip)", sym, px)
                continue

            # pyramid into a running winner, risk permitting
            if risk.can_pyramid(p, self.portfolio.equity(), self.portfolio.open_notional(), self.cfg):
                self._pyramid(sym, p, px)

    def _trend_against(self, symbol, side):
        try:
            kl = self.api.klines(symbol, self.cfg.tf_entry, self.cfg.kline_limit)
            sig = strategy.evaluate(symbol, kl, None, self.cfg)
            return sig.trend != 0 and sig.trend != side
        except Exception:
            return False

    def _pyramid(self, symbol, p, price):
        base_risk = self.cfg.risk_per_trade * self.portfolio.equity() * self.cfg.pyramid_add_frac
        add_qty = base_risk / p["risk_dist"] if p["risk_dist"] > 0 else 0
        meta = self.universe.meta(symbol)
        if meta and meta.get("lot_step"):
            step = meta["lot_step"]
            add_qty = int(add_qty / step) * step
        if add_qty <= 0:
            return
        self.portfolio.pyramid_add(symbol, add_qty, price)
        log.info("PYRAMID %s +%.6f @ %.6f (add #%d)", symbol, add_qty, price, p.get("adds", 0))

    def _flatten_all(self):
        for sym in list(self.portfolio.positions.keys()):
            px = self._price(sym, self.portfolio.positions[sym].get("cur_price"))
            self.portfolio.close(sym, px, "flatten")
        log.info("FLATTEN — closed all positions on user request")

    # ---- circuit breakers ----------------------------------------------------
    def _check_breakers(self):
        eq = self.portfolio.equity()
        peak = max([h["equity"] for h in self.portfolio.history] + [self.portfolio.start_equity, eq])
        dd = (eq / peak - 1.0) if peak > 0 else 0.0
        reasons = []
        if self.portfolio.day_loss_frac() <= -self.cfg.daily_loss_halt:
            reasons.append("daily_loss")
        if dd <= -self.cfg.max_drawdown_halt:
            reasons.append("max_drawdown")
        if self.control.snapshot()["paused"]:
            reasons.append("paused")
        self.halt_reason = ",".join(reasons)

    def _can_enter(self):
        if self.halt_reason:
            return False
        return len(self.portfolio.positions) < self.cfg.max_concurrent_positions

    # ---- scan + enter --------------------------------------------------------
    def _scan_and_enter(self):
        cands = []
        for row in self.universe.symbols():
            sym = row["symbol"]
            if self.portfolio.has(sym) or self.control.is_blocked(sym):
                continue
            try:
                entry_kl = self.api.klines(sym, self.cfg.tf_entry, self.cfg.kline_limit)
                # cheap pre-filter: only pull the confirm TF when entry shows a trend
                pre = strategy.evaluate(sym, entry_kl, None, self.cfg)
                if pre.side == 0 and pre.note in ("no_trend", "insufficient_bars"):
                    continue
                conf_kl = (self.api.klines(sym, self.cfg.tf_confirm, self.cfg.kline_limit)
                           if self.cfg.require_confirm_tf else None)
                sig = strategy.evaluate(sym, entry_kl, conf_kl, self.cfg)
                if sig.side != 0:
                    cands.append(sig)
                time.sleep(0.05)       # be polite to the API
            except Exception as e:
                log.debug("scan %s failed: %s", sym, e)

        cands.sort(key=lambda s: s.score, reverse=True)
        self.scanner = [{"symbol": s.symbol, "side": s.side, "score": s.score,
                         "price": s.price, "note": s.note} for s in cands[:20]]

        slots = self.cfg.max_concurrent_positions - len(self.portfolio.positions)
        for sig in cands:
            if slots <= 0:
                break
            if self._open(sig):
                slots -= 1

    def _open(self, sig):
        entry = sig.price
        stop = trailing.initial_stop(entry, sig.side, sig.atr, self.cfg)
        risk_dist = trailing.risk_per_unit(entry, stop, sig.side)
        meta = self.universe.meta(sig.symbol)
        qty, notional, risk_usd = risk.size_trade(
            entry, stop, self.portfolio.equity(), self.portfolio.start_equity,
            self.portfolio.symbol_notional(sig.symbol), self.portfolio.open_notional(),
            self.portfolio.free_cash(), meta, self.cfg)
        if qty <= 0:
            return False
        self.portfolio.open(sig.symbol, sig.side, qty, entry, stop, sig.atr, risk_dist,
                            meta={"score": sig.score})
        self.broker.protect(sig.symbol, stop)        # server-side safety net (live/testnet)
        log.info("OPEN %s %s %.6f @ %.6f stop=%.6f risk=$%.2f score=%.2f",
                 sig.symbol, "long" if sig.side > 0 else "short", qty, entry, stop,
                 risk_usd, sig.score)
        return True

    # ---- run loop ------------------------------------------------------------
    def run(self, once=False):
        log.info("bybitbot starting — mode=%s account=$%.0f risk/trade=%.2f%% max_pos=%d",
                 self.cfg.mode, self.cfg.account_size, self.cfg.risk_per_trade * 100,
                 self.cfg.max_concurrent_positions)
        while True:
            try:
                self.cycle()
            except Exception as e:
                log.exception("cycle error: %s", e)
            if once:
                break
            time.sleep(self.cfg.poll_interval_s)
