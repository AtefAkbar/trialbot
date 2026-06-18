"""Tracks the watched traders and turns position-snapshot diffs into copy signals.

Primary copy signal = diff of each trader's /positions snapshot between polls.
One call per trader captures OPEN / ADD / TRIM / CLOSE in one shot, which is
more robust than reconstructing intent from the raw trade feed.

When a trader is newly onboarded (first sight, or re-rank), we take a SILENT
baseline snapshot and do NOT copy their pre-existing book — we only copy trades
they make *after* we start following them.
"""
import time
from dataclasses import dataclass


@dataclass
class CopySignal:
    kind: str            # OPEN | ADD | TRIM | CLOSE
    wallet: str
    user_name: str
    asset: str           # outcome token id
    condition_id: str
    outcome: str
    title: str
    slug: str
    trader_size: float   # trader's share count AFTER the change
    size_delta: float    # signed change in trader shares since last snapshot
    avg_price: float     # trader's average entry price
    cur_price: float     # market price reported with the position (may be 0)

    def key(self):
        return (self.wallet, self.asset)


class Tracker:
    def __init__(self, cfg, data):
        self.cfg = cfg
        self.data = data
        self.traders = {}      # wallet -> user_name
        self.snaps = {}        # wallet -> {asset: position-dict}

    # ---- snapshot helpers ----------------------------------------------------
    def _tradeable(self, p):
        """Is this position in a market still open for trading? Uses only fields
        already in the /positions response (no extra calls): resolved markets are
        redeemable and pinned to curPrice 0/1; expired ones have a past endDate."""
        if p.get("redeemable"):
            return False
        cur = float(p.get("curPrice") or 0.0)
        if cur <= 0.0 or cur >= 1.0:          # price pinned to resolution -> untradeable
            return False
        end = (p.get("endDate") or "")[:10]    # "YYYY-MM-DD"; lexicographic compare OK
        if end and end < time.strftime("%Y-%m-%d", time.gmtime()):
            return False
        return True

    def _snapshot(self, wallet):
        out = {}
        for p in self.data.positions(wallet):
            size = float(p.get("size") or 0.0)
            if size < self.cfg.min_position_size:
                continue
            if self.cfg.active_markets_only and not self._tradeable(p):
                continue
            out[p["asset"]] = {
                "size": size,
                "avgPrice": float(p.get("avgPrice") or 0.0),
                "curPrice": float(p.get("curPrice") or 0.0),
                "outcome": p.get("outcome", ""),
                "conditionId": p.get("conditionId", ""),
                "title": p.get("title", ""),
                "slug": p.get("slug", ""),
            }
        return out

    # ---- leaderboard management ---------------------------------------------
    def refresh_leaderboard(self):
        """Re-rank top-N. Onboard newcomers (silent baseline) and drop dropouts.
        Returns (added_wallets, removed_wallets)."""
        top = self.data.top_traders(
            self.cfg.top_n, self.cfg.leaderboard_category, self.cfg.leaderboard_metric)
        new_set = {t["wallet"]: t["user_name"] for t in top}

        added = [w for w in new_set if w not in self.traders]
        removed = [w for w in self.traders if w not in new_set]

        for w in added:
            # copy_existing_on_start: seed an EMPTY baseline so the next poll diffs
            # empty -> their current book and emits OPEN signals for all holdings.
            # Otherwise baseline their book silently (only copy trades made later).
            self.snaps[w] = {} if self.cfg.copy_existing_on_start else self._snapshot(w)
        for w in removed:                        # stop tracking; open copies still
            self.snaps.pop(w, None)              # managed by the portfolio/engine

        self.traders = new_set
        return added, removed

    # ---- the per-cycle diff --------------------------------------------------
    def poll(self):
        """Snapshot every tracked trader, diff vs last snapshot, emit signals."""
        signals = []
        for wallet, name in self.traders.items():
            old = self.snaps.get(wallet, {})
            new = self._snapshot(wallet)
            assets = set(old) | set(new)
            for a in assets:
                o = old.get(a)
                n = new.get(a)
                if n and not o:
                    signals.append(self._sig("OPEN", wallet, name, a, n, n["size"], n["size"]))
                elif o and not n:
                    # disappeared from the book -> fully closed (trader size now 0)
                    signals.append(self._sig("CLOSE", wallet, name, a, o, 0.0, -o["size"]))
                elif o and n:
                    d = n["size"] - o["size"]
                    if d > 1e-9:
                        signals.append(self._sig("ADD", wallet, name, a, n, n["size"], d))
                    elif d < -1e-9:
                        kind = "CLOSE" if n["size"] < self.cfg.min_position_size else "TRIM"
                        signals.append(self._sig(kind, wallet, name, a, n, n["size"], d))
            self.snaps[wallet] = new
        return signals

    def _sig(self, kind, wallet, name, asset, pos, trader_size, size_delta):
        return CopySignal(
            kind=kind, wallet=wallet, user_name=name, asset=asset,
            condition_id=pos["conditionId"], outcome=pos["outcome"],
            title=pos["title"], slug=pos["slug"],
            trader_size=trader_size, size_delta=size_delta,
            avg_price=pos["avgPrice"], cur_price=pos["curPrice"],
        )
