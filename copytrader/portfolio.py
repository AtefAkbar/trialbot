"""Virtual (paper) portfolio. Honest accounting: fee + adverse slippage on every
simulated fill, weighted-average entry on adds, realized PnL on sells, JSON state
that survives restarts.

Positions are keyed by (wallet, asset): we copy each trader's stake in each
outcome token independently, scaled by a fixed `ratio` set at first entry so
later adds/trims by the trader are mirrored proportionally.
"""
import json
import os


def _k(wallet, asset):
    return f"{wallet}|{asset}"


class Portfolio:
    def __init__(self, cfg, broker, path=None):
        self.cfg = cfg
        self.broker = broker
        self.path = path or cfg.state_path
        self.cash = cfg.account_size
        self.realized_pnl = 0.0
        self.positions = {}        # key -> dict
        self.closed = []           # log of closed copies
        self.history = []          # [{t, equity, realized, unrealized}] equity trail
        self._load()

    # ---- queries -------------------------------------------------------------
    def has(self, wallet, asset):
        return _k(wallet, asset) in self.positions

    def get(self, wallet, asset):
        return self.positions.get(_k(wallet, asset))

    def _mark_price(self, p):
        return p["cur_price"] if p.get("cur_price", 0) > 0 else p["entry"]

    def market_notional(self, asset):
        """Current open exposure across all copies of this outcome token."""
        return sum(p["shares"] * self._mark_price(p)
                   for p in self.positions.values() if p["asset"] == asset)

    def open_notional(self):
        return sum(p["shares"] * self._mark_price(p) for p in self.positions.values())

    def equity(self):
        return self.cash + self.open_notional()

    def unrealized(self):
        return sum((self._mark_price(p) - p["entry"]) * p["shares"]
                   for p in self.positions.values())

    # ---- mutations -----------------------------------------------------------
    def open(self, wallet, asset, shares, price, ratio, sl, tp, meta):
        exec_px = self.broker.fill(+1, price)
        cost = shares * exec_px * (1.0 + self.cfg.fee)
        self.cash -= cost
        self.positions[_k(wallet, asset)] = {
            "wallet": wallet, "asset": asset, "shares": shares, "entry": exec_px,
            "ratio": ratio, "sl": sl, "tp": tp, "cur_price": price, **meta,
        }

    def set_shares(self, wallet, asset, target, price):
        """Buy or sell to reach `target` shares (mirrors trader add/trim)."""
        p = self.positions.get(_k(wallet, asset))
        if p is None:
            return
        delta = target - p["shares"]
        if abs(delta) < 1e-9:
            return
        if delta > 0:                                   # add: weighted-avg entry
            exec_px = self.broker.fill(+1, price)
            self.cash -= delta * exec_px * (1.0 + self.cfg.fee)
            new_shares = p["shares"] + delta
            p["entry"] = (p["entry"] * p["shares"] + exec_px * delta) / new_shares
            p["shares"] = new_shares
            p["sl"] = p["entry"] * (1.0 - self.cfg.stop_loss_pct)
            p["tp"] = p["entry"] * (1.0 + self.cfg.take_profit_pct)
        else:                                           # trim: realize partial PnL
            sell = min(-delta, p["shares"])
            exec_px = self.broker.fill(-1, price)
            self.cash += sell * exec_px * (1.0 - self.cfg.fee)
            self.realized_pnl += (exec_px - p["entry"]) * sell
            p["shares"] -= sell
            if p["shares"] < 1e-9:
                self.positions.pop(_k(wallet, asset), None)
        p["cur_price"] = price

    def close(self, wallet, asset, price, reason):
        p = self.positions.pop(_k(wallet, asset), None)
        if p is None:
            return
        exec_px = self.broker.fill(-1, price)
        self.cash += p["shares"] * exec_px * (1.0 - self.cfg.fee)
        pnl = (exec_px - p["entry"]) * p["shares"]
        self.realized_pnl += pnl
        self.closed.append({
            "wallet": wallet, "asset": asset, "title": p.get("title", ""),
            "exit": exec_px, "entry": p["entry"], "shares": p["shares"],
            "pnl": pnl, "reason": reason,
        })

    def mark(self, prices):
        """prices: {asset: price}. Updates cur_price for held positions."""
        for p in self.positions.values():
            px = prices.get(p["asset"])
            if px and px > 0:
                p["cur_price"] = px

    def record_equity(self, ts):
        """Append a point to the equity trail (capped) for the dashboard chart."""
        self.history.append({
            "t": ts, "equity": round(self.equity(), 2),
            "realized": round(self.realized_pnl, 2),
            "unrealized": round(self.unrealized(), 2),
        })
        if len(self.history) > 2000:
            self.history = self.history[-2000:]

    # ---- persistence ---------------------------------------------------------
    def summary(self):
        return {
            "cash": round(self.cash, 2),
            "open_notional": round(self.open_notional(), 2),
            "equity": round(self.equity(), 2),
            "unrealized": round(self.unrealized(), 2),
            "realized": round(self.realized_pnl, 2),
            "open_positions": len(self.positions),
            "closed_trades": len(self.closed),
        }

    def _load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                s = json.load(f)
            self.cash = s["cash"]
            self.realized_pnl = s["realized_pnl"]
            self.positions = s["positions"]
            self.closed = s["closed"]
            self.history = s.get("history", [])
        except Exception:
            pass        # corrupt/old state -> start fresh

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({
                "cash": self.cash, "realized_pnl": self.realized_pnl,
                "positions": self.positions, "closed": self.closed,
                "history": self.history,
            }, f, indent=2)
        os.replace(tmp, self.path)
