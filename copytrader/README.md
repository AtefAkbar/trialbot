# copytrader — Polymarket copy-trading bot (paper engine)

Copies the **top-10 Polymarket leaderboard traders (by PnL)**, sizes each copy
from your account size + a risk budget, and runs a closed loop that mirrors their
entries/exits and applies independent stop-loss / take-profit.

## ⚠️ Paper only — no money moves

This engine **simulates** fills against **real, live Polymarket prices** and
tracks a virtual portfolio. It never places a real order. The `LiveBroker` in
[`broker.py`](broker.py) is a deliberately disabled stub — wiring real USDC
orders is out of scope and requires you to supply your own key and explicitly
enable it yourself.

## Run

```bash
# from the project root (the dir that contains the copytrader/ folder)
python3 -m copytrader.run --traders   # print the live top-10, no engine
python3 -m copytrader.run --once      # one full cycle (smoke test)
python3 -m copytrader.run             # the closed loop, forever
```

Requires only `requests` (`pip install requests`).

## What the closed loop does each cycle

1. **Re-rank** the leaderboard once an hour — onboard new top-10 traders
   (baselined silently, so their *pre-existing* book is **not** back-copied),
   drop those who fall off.
2. **Poll** every tracked trader's `/positions` and **diff** vs the last
   snapshot → `OPEN / ADD / TRIM / CLOSE` copy signals.
3. **Copy entries** (risk-sized) and **mirror exits** (proportional to our
   fixed copy ratio). A copy from a trader who later drops off the board is
   still managed until closed.
4. **Mark to market** and enforce independent **stop-loss / take-profit**.
5. Persist `state.json`, log a summary, sleep.

## Configuration

All knobs live in [`config.py`](config.py): `account_size`, `risk_per_copy`,
`max_per_market`, `max_total_exposure`, `stop_loss_pct`, `take_profit_pct`,
`poll_interval_s`, `rerank_interval_s`, slippage/fee. Defaults: $10k virtual
account, 2% per copy, 10% per-market cap, 60% total-exposure cap.

## Tests

```bash
python3 -m copytrader.tests.test_diff      # snapshot-diff signal detection
python3 -m copytrader.tests.test_sizing    # fixed-fraction + caps math
python3 -m copytrader.tests.test_engine    # entry/add/mirror-exit/take-profit
```

## Data sources (free, read-only, no API key)

- Leaderboard: `https://data-api.polymarket.com/v1/leaderboard`
- Trader positions: `https://data-api.polymarket.com/positions`
- Live price: `https://clob.polymarket.com/midpoint`
