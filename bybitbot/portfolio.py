"""Virtual portfolio with honest futures accounting (longs AND shorts).

Balance is the realised account balance; equity = balance + unrealised PnL.
Each fill pays a taker fee; PnL on a short is (entry-exit)*qty. One position per
symbol, carrying the trailing-stop bookkeeping (peak, peak_r, risk_dist, adds).
State persists atomically to JSON and survives restarts.
"""
import json
import os
import time
from datetime import datetime, timezone


def _utc_day(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


class Portfolio:
    def __init__(self, cfg, broker, path=None):
        self.cfg = cfg
        self.broker = broker
        self.path = path or cfg.state_path
        self.balance = cfg.account_size
        self.start_equity = cfg.account_size
        self.realized_pnl = 0.0
        self.day_realized = 0.0
        self.day = _utc_day(time.time())
        self.positions = {}        # symbol -> dict
        self.closed = []           # closed-trade log
        self.history = []          # equity trail
        self._load()

    # ---- queries -------------------------------------------------------------
    def has(self, symbol):
        return symbol in self.positions

    def get(self, symbol):
        return self.positions.get(symbol)

    def _mark(self, p):
        return p["cur_price"] if p.get("cur_price", 0) > 0 else p["entry"]

    def pos_pnl(self, p):
        return (self._mark(p) - p["entry"]) * p["qty"] * p["side"]

    def symbol_notional(self, symbol):
        p = self.positions.get(symbol)
        return p["qty"] * self._mark(p) if p else 0.0

    def open_notional(self):
        return sum(p["qty"] * self._mark(p) for p in self.positions.values())

    def used_margin(self):
        return self.open_notional() / max(1.0, self.cfg.max_leverage)

    def unrealized(self):
        return sum(self.pos_pnl(p) for p in self.positions.values())

    def equity(self):
        return self.balance + self.unrealized()

    def free_cash(self):
        return max(0.0, self.equity() - self.used_margin())

    # ---- mutations -----------------------------------------------------------
    def _fee(self, qty, price):
        return qty * price * self.cfg.taker_fee

    def open(self, symbol, side, qty, price, stop, atr, risk_dist, meta=None):
        exec_px = self.broker.fill(side, price)
        self.broker.submit(symbol, side, qty, reduce_only=False)
        self.balance -= self._fee(qty, exec_px)
        self.positions[symbol] = {
            "symbol": symbol, "side": side, "qty": qty, "entry": exec_px,
            "stop": stop, "atr": atr, "risk_dist": risk_dist,
            "peak": exec_px, "peak_r": 0.0, "cur_price": price, "adds": 0,
            "opened_t": time.time(), **(meta or {}),
        }

    def pyramid_add(self, symbol, qty, price):
        p = self.positions.get(symbol)
        if p is None or qty <= 0:
            return
        side = p["side"]
        exec_px = self.broker.fill(side, price)
        self.broker.submit(symbol, side, qty, reduce_only=False)
        self.balance -= self._fee(qty, exec_px)
        new_qty = p["qty"] + qty
        p["entry"] = (p["entry"] * p["qty"] + exec_px * qty) / new_qty
        p["qty"] = new_qty
        p["adds"] = p.get("adds", 0) + 1

    def close(self, symbol, price, reason):
        p = self.positions.pop(symbol, None)
        if p is None:
            return
        side = p["side"]
        exec_px = self.broker.fill(-side, price)      # exit is the opposite side
        self.broker.submit(symbol, -side, p["qty"], reduce_only=True)
        gross = (exec_px - p["entry"]) * p["qty"] * side
        fee = self._fee(p["qty"], exec_px)
        net = gross - fee
        self.balance += net
        self.realized_pnl += net
        self._roll_day()
        self.day_realized += net
        self.closed.append({
            "symbol": symbol, "side": "long" if side > 0 else "short",
            "entry": p["entry"], "exit": exec_px, "qty": p["qty"],
            "pnl": net, "reason": reason, "adds": p.get("adds", 0),
            "t": time.time(),
        })

    def mark(self, prices):
        for p in self.positions.values():
            px = prices.get(p["symbol"])
            if px and px > 0:
                p["cur_price"] = px
                if p["side"] > 0:
                    p["peak"] = max(p["peak"], px)
                else:
                    p["peak"] = min(p["peak"], px)

    # ---- daily-loss circuit-breaker bookkeeping ------------------------------
    def _roll_day(self):
        today = _utc_day(time.time())
        if today != self.day:
            self.day = today
            self.day_realized = 0.0

    def day_loss_frac(self):
        self._roll_day()
        eq = self.equity() or 1.0
        return self.day_realized / eq

    # ---- equity trail --------------------------------------------------------
    def record_equity(self, ts):
        self.history.append({
            "t": ts, "equity": round(self.equity(), 2),
            "realized": round(self.realized_pnl, 2),
            "unrealized": round(self.unrealized(), 2),
        })
        if len(self.history) > 2000:
            self.history = self.history[-2000:]

    def summary(self):
        return {
            "balance": round(self.balance, 2),
            "equity": round(self.equity(), 2),
            "free_cash": round(self.free_cash(), 2),
            "open_notional": round(self.open_notional(), 2),
            "unrealized": round(self.unrealized(), 2),
            "realized": round(self.realized_pnl, 2),
            "open_positions": len(self.positions),
            "closed_trades": len(self.closed),
        }

    # ---- persistence ---------------------------------------------------------
    def _load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                s = json.load(f)
            self.balance = s["balance"]
            self.start_equity = s.get("start_equity", self.cfg.account_size)
            self.realized_pnl = s["realized_pnl"]
            self.day_realized = s.get("day_realized", 0.0)
            self.day = s.get("day", self.day)
            self.positions = s["positions"]
            self.closed = s["closed"]
            self.history = s.get("history", [])
        except Exception:
            pass        # corrupt/old state -> start fresh

    def save(self):
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({
                "balance": self.balance, "start_equity": self.start_equity,
                "realized_pnl": self.realized_pnl, "day_realized": self.day_realized,
                "day": self.day, "positions": self.positions,
                "closed": self.closed, "history": self.history,
            }, f, indent=2)
        os.replace(tmp, self.path)
