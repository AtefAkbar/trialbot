"""The closed loop.

Each cycle:
  1. (periodically) re-rank the leaderboard -> onboard/drop traders.
  2. poll tracked traders -> copy signals from position diffs.
  3. apply signals: OPEN/ADD copy entries (risk-sized), TRIM/CLOSE mirror exits.
  4. mark to market, then enforce independent stop-loss / take-profit.
  5. persist state, log a summary, sleep.

Positions copied from a trader who later drops off the leaderboard are still
managed (mirror-exit + SL/TP) until closed — dropping a trader only stops *new*
copies, the tracker keeps polling any wallet we still hold a copy from.
"""
import time
import logging

from . import pm_data
from .broker import PaperBroker
from .portfolio import Portfolio
from .tracker import Tracker
from .risk import size_copy, stop_take_levels

log = logging.getLogger("copytrader")


class Engine:
    def __init__(self, cfg, data=pm_data):
        self.cfg = cfg
        self.data = data
        self.broker = PaperBroker(cfg.slippage)
        assert not self.broker.live, "engine refuses a live broker"
        self.portfolio = Portfolio(cfg, self.broker)
        self.tracker = Tracker(cfg, data)
        self._last_rerank = 0.0
        self._price_cache = {}

    # ---- pricing -------------------------------------------------------------
    def _price(self, asset, fallback=0.0):
        if asset in self._price_cache:
            return self._price_cache[asset]
        mid = self.data.midpoint(asset)
        px = mid if (mid and mid > 0) else fallback
        self._price_cache[asset] = px
        return px

    # ---- one cycle -----------------------------------------------------------
    def cycle(self):
        self._price_cache = {}
        now = time.time()

        if not self.tracker.traders or (now - self._last_rerank) >= self.cfg.rerank_interval_s:
            added, removed = self.tracker.refresh_leaderboard()
            self._last_rerank = now
            if added or removed:
                log.info("leaderboard: +%d new, -%d dropped (tracking %d)",
                         len(added), len(removed), len(self.tracker.traders))

        # exits first, then largest entries first — so when mirroring big existing
        # books, the highest-conviction positions fill before the exposure cap.
        signals = self.tracker.poll()
        signals.sort(key=lambda s: (s.kind != "CLOSE",
                                    -(s.trader_size * (s.cur_price or s.avg_price or 0))))
        for s in signals:
            self._dispatch(s)

        self._manage()
        self.portfolio.record_equity(now)
        self.portfolio.save()
        s = self.portfolio.summary()
        log.info("equity=$%.2f cash=$%.2f open=%d exposure=$%.2f uPnL=$%.2f rPnL=$%.2f",
                 s["equity"], s["cash"], s["open_positions"],
                 s["open_notional"], s["unrealized"], s["realized"])

    # ---- signal handling -----------------------------------------------------
    def _dispatch(self, s):
        held = self.portfolio.has(s.wallet, s.asset)
        if s.kind == "OPEN" and not held:
            self._open(s)
        elif s.kind in ("OPEN", "ADD", "TRIM"):
            self._resize(s)            # mirror trader add/trim to keep our ratio
        elif s.kind == "CLOSE":
            self._close(s, "mirror_exit")

    def _open(self, s):
        if s.trader_size <= 0:
            return
        # cheap early-out once we're fully deployed — avoids pricing every one of
        # a trader's (possibly hundreds of) existing positions after the cap is hit.
        if self.portfolio.open_notional() >= self.cfg.max_total_exposure * self.cfg.account_size - 1e-9:
            return
        price = self._price(s.asset, s.cur_price or s.avg_price)
        notional, shares = size_copy(price, s.asset, self.portfolio, self.cfg)
        if shares <= 0:
            log.info("skip OPEN %s '%s' — no headroom/price", s.user_name, s.title[:40])
            return
        ratio = shares / s.trader_size
        sl, tp = stop_take_levels(price, self.cfg)
        self.portfolio.open(s.wallet, s.asset, shares, price, ratio, sl, tp, meta={
            "title": s.title, "outcome": s.outcome, "slug": s.slug,
            "user_name": s.user_name,
        })
        log.info("OPEN copy %s '%s' %s | %.0f sh @ %.3f ($%.2f)",
                 s.user_name, s.title[:40], s.outcome, shares, price, notional)

    def _resize(self, s):
        p = self.portfolio.get(s.wallet, s.asset)
        if p is None:
            return                     # we never held this copy; don't create on add
        price = self._price(s.asset, s.cur_price or p["entry"])
        if price <= 0:
            return
        target = p["ratio"] * s.trader_size
        # Trims always allowed; ADDS must respect the same risk caps as new entries —
        # otherwise a trader scaling hard into one market blows past max_per_market.
        if target > p["shares"]:
            cap = self.cfg
            market_cap_sh = cap.max_per_market * cap.account_size / price
            total_head = max(0.0, cap.max_total_exposure * cap.account_size
                             - self.portfolio.open_notional())
            add_head_sh = max(0.0, min(total_head, self.portfolio.cash)) / price
            target = min(target, market_cap_sh, p["shares"] + add_head_sh)
            target = max(target, p["shares"])      # never forced below current by caps
        self.portfolio.set_shares(s.wallet, s.asset, target, price)
        log.info("%s copy %s '%s' -> %.0f sh @ %.3f (cap %.0f)",
                 s.kind, s.user_name, s.title[:40], target, price,
                 self.cfg.max_per_market * self.cfg.account_size / price)

    def _close(self, s, reason):
        if not self.portfolio.has(s.wallet, s.asset):
            return
        price = self._price(s.asset, s.cur_price or s.avg_price)
        self.portfolio.close(s.wallet, s.asset, price, reason)
        log.info("CLOSE copy %s '%s' (%s) @ %.3f", s.user_name, s.title[:40], reason, price)

    # ---- mark + independent risk exits --------------------------------------
    def _manage(self):
        prices = {}
        for p in list(self.portfolio.positions.values()):
            prices[p["asset"]] = self._price(p["asset"], p.get("cur_price") or p["entry"])
        self.portfolio.mark(prices)

        for key, p in list(self.portfolio.positions.items()):
            px = p["cur_price"]
            if px <= 0:
                continue
            if px <= p["sl"]:
                self.portfolio.close(p["wallet"], p["asset"], px, "stop_loss")
                log.info("STOP-LOSS '%s' @ %.3f", p.get("title", "")[:40], px)
            elif px >= p["tp"]:
                self.portfolio.close(p["wallet"], p["asset"], px, "take_profit")
                log.info("TAKE-PROFIT '%s' @ %.3f", p.get("title", "")[:40], px)

    # ---- run loop ------------------------------------------------------------
    def run(self, once=False):
        log.info("copytrader starting — PAPER ONLY, account=$%.0f, risk/copy=%.1f%%",
                 self.cfg.account_size, self.cfg.risk_per_copy * 100)
        while True:
            try:
                self.cycle()
            except Exception as e:
                log.exception("cycle error: %s", e)
            if once:
                break
            time.sleep(self.cfg.poll_interval_s)
