# bybitbot — autonomous Bybit perpetual-futures bot

Small low-risk bets on a 5–15m timeframe with a **ratcheting trailing stop** that
tightens as profit grows, **pyramiding** into winners, and capital-based risk
management (per-trade risk, exposure caps, daily-loss / drawdown circuit breakers).

**Defaults to Bybit TESTNET.** Live trading is wired but OFF until you opt in.

## Run it

```bash
pip install -r ../requirements.txt          # requests, pandas, numpy

# 1) Paper sim against live MAINNET data — no account, no keys, nothing at risk
BYBIT_MODE=paper python -m bybitbot.run --once     # one cycle
BYBIT_MODE=paper python -m bybitbot.serve          # engine + dashboard at http://localhost:8787

# 2) Bybit TESTNET — real API + real order plumbing, fake money
#    Make testnet keys at https://testnet.bybit.com  (API → create key)
export BYBIT_MODE=testnet BYBIT_API_KEY=... BYBIT_API_SECRET=...
python -m bybitbot.serve

# Quick connectivity check (no orders):
BYBIT_MODE=paper python -m bybitbot.run --smoke
```

Dashboard password: set `PASSWORD=...` (defaults to `password123`).

## Going live (deliberate, your call)

Live order placement requires BOTH, set by you:

```bash
export BYBIT_MODE=live BYBIT_CONFIRM_LIVE=1 BYBIT_API_KEY=... BYBIT_API_SECRET=...
```

Without `BYBIT_CONFIRM_LIVE=1` the live broker refuses to start. Only do this
after the strategy has proven net-of-fee edge on backtest + testnet — see the
"fee wall" note below.

## ⚠️ Honest caveat

This repo's own backtests (`../altcoin_backtest/`) found that **5–15m crypto
scalping has no net edge after fees** — only 1h+ trend-following survived
out-of-sample. Validate edge before risking real money. The bot ships
conservative defaults and a testnet-first posture for exactly this reason.

## Key knobs (`config.py`, all env-overridable where marked)

| Knob | Default | Meaning |
|---|---|---|
| `RISK_PER_TRADE` | 0.005 | 0.5% equity risked per trade (the floor) |
| `max_concurrent_positions` | 6 | most positions held at once |
| `init_stop_atr` | 1.2 | initial stop distance in ATRs (tight) |
| `breakeven_at_r` | 1.0 | lock breakeven once +1R in profit |
| `trail_atr_far→near` | 2.5→0.8 | trail band tightens as profit grows |
| `pyramid_max_adds` | 2 | extra units stacked on a winner |
| `daily_loss_halt` | 0.02 | halt new entries at −2% day PnL |
| `max_drawdown_halt` | 0.15 | halt new entries at −15% from peak |
| `min_turnover_usd` | 20M | liquidity floor for the universe |

## Layout

`config` knobs · `bybit_api` V5 REST · `universe` symbol scanner · `strategy`
HMA+SMC signal · `trailing` ratchet stop · `risk` sizing+pyramiding · `broker`
paper/testnet/live · `portfolio` accounting+persistence · `engine` closed loop ·
`dashboard`+`serve` UI · `tests/` unit tests (`python -m pytest bybitbot/tests`).
