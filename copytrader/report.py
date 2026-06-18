"""Performance summary for the paper copy-trader.

Reads state.json and prints a check-in: equity, P&L, drawdown, win rate, and
per-trader attribution (which of the followed traders is actually making money).

  python3 -m copytrader.report
"""
import os
import sys
import json
import time
from collections import defaultdict

from .config import Config


def _mark(p):
    return p["cur_price"] if p.get("cur_price", 0) > 0 else p["entry"]


def load(path):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def build(cfg):
    s = load(cfg.state_path)
    if s is None:
        return None
    base = cfg.account_size
    positions = list(s.get("positions", {}).values())
    closed = s.get("closed", [])
    history = s.get("history", [])

    exposure = sum(p["shares"] * _mark(p) for p in positions)
    unrealized = sum((_mark(p) - p["entry"]) * p["shares"] for p in positions)
    realized = s.get("realized_pnl", 0.0)
    cash = s.get("cash", base)
    equity = cash + exposure
    total = realized + unrealized

    # max drawdown off the equity trail
    peak = -1e9
    mdd = 0.0
    for h in history:
        peak = max(peak, h["equity"])
        if peak > 0:
            mdd = min(mdd, h["equity"] / peak - 1.0)

    # closed-trade stats
    wins = [c for c in closed if c["pnl"] > 0]
    losses = [c for c in closed if c["pnl"] <= 0]
    win_rate = len(wins) / len(closed) if closed else 0.0
    avg_win = sum(c["pnl"] for c in wins) / len(wins) if wins else 0.0
    avg_loss = sum(c["pnl"] for c in losses) / len(losses) if losses else 0.0

    # per-trader attribution (open positions, by name)
    by_trader = defaultdict(lambda: {"n": 0, "value": 0.0, "upnl": 0.0})
    for p in positions:
        t = by_trader[p.get("user_name", p["wallet"][:8])]
        t["n"] += 1
        t["value"] += p["shares"] * _mark(p)
        t["upnl"] += (_mark(p) - p["entry"]) * p["shares"]

    return dict(base=base, equity=equity, cash=cash, exposure=exposure,
                realized=realized, unrealized=unrealized, total=total,
                ret_pct=total / base * 100 if base else 0.0, mdd=mdd * 100,
                n_open=len(positions), n_closed=len(closed), win_rate=win_rate,
                avg_win=avg_win, avg_loss=avg_loss, points=len(history),
                by_trader=dict(by_trader))


def render(r, cfg):
    if r is None:
        return "No state.json yet — is the engine running? (python3 -m copytrader.run)"
    L = []
    L.append("=" * 56)
    L.append(f" POLYMARKET COPY-TRADER — PAPER CHECK-IN  {time.strftime('%Y-%m-%d %H:%M')}")
    L.append("=" * 56)
    L.append(f" Account base   : ${r['base']:,.2f}")
    L.append(f" Equity         : ${r['equity']:,.2f}   ({r['ret_pct']:+.2f}%)")
    L.append(f" Total P&L      : ${r['total']:+,.2f}   (realized ${r['realized']:+,.2f}"
             f" / unrealized ${r['unrealized']:+,.2f})")
    L.append(f" Cash / Exposure: ${r['cash']:,.2f} / ${r['exposure']:,.2f}"
             f"  ({r['exposure']/r['base']*100:.0f}% deployed)")
    L.append(f" Max drawdown   : {r['mdd']:.2f}%   ({r['points']} equity points)")
    L.append(f" Open / Closed  : {r['n_open']} open, {r['n_closed']} closed")
    if r['n_closed']:
        L.append(f" Win rate       : {r['win_rate']*100:.0f}%   "
                 f"avg win ${r['avg_win']:+.2f} / avg loss ${r['avg_loss']:+.2f}")
    L.append("-" * 56)
    L.append(" PER-TRADER (open positions, by unrealized P&L)")
    rows = sorted(r["by_trader"].items(), key=lambda kv: kv[1]["upnl"], reverse=True)
    for name, t in rows:
        L.append(f"   {name:<18} {t['n']:>2} pos  ${t['value']:>6.2f}  uPnL ${t['upnl']:>+6.2f}")
    L.append("=" * 56)
    return "\n".join(L)


def main():
    cfg = Config()
    if "--state" in sys.argv:
        cfg.state_path = sys.argv[sys.argv.index("--state") + 1]
    print(render(build(cfg), cfg))


if __name__ == "__main__":
    main()
