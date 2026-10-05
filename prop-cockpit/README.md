# Prop Firm Risk Cockpit

A standalone risk-management cockpit for a prop-firm challenge account. Enforces
position sizing, drawdown, and journaling discipline — it does **not** generate
trade signals.

Built with Vite + React + Tailwind. All state (settings + trade journal) is
saved to the browser's `localStorage`, so it works as a real deployed app (the
old `window.storage` claude.ai-artifact API is gone).

## Features

- **Scanner** — live Bybit USDT-perp tickers, computes each pair's 24h range %,
  classifies it into zones (too quiet / sweet spot / elevated / too wild), and
  suggests position notional + leverage from your risk settings.
- **Position calc** — manual entry/stop calculator that sizes the trade and
  warns when the risk exceeds what's left of today's drawdown budget (both the
  hard daily limit and your self-imposed soft stop).
- **Journal** — logs closed trades, tracks progress to the Stage 1 target,
  daily/overall drawdown, win rate, expectancy, "trades to target", and an
  equity curve with target / drawdown-floor reference lines.
- **Settings** — every account rule and risk parameter, persisted locally.

## Run locally

```bash
npm install
npm run dev      # http://localhost:5173
```

## Build

```bash
npm run build    # outputs to dist/
npm run preview  # serve the production build
```

## Risk model

- Position notional = risk$ / (stop distance % / 100)
- Stop distance % = coin's 24h range % × stop multiplier (default 1.5×)
- Leverage = notional / account equity
- Risk$ = equity × risk-per-trade % (default 1%)

Elevated-zone coins auto-size to 50%. Defaults match a $5,000 account:
10% max drawdown ($500), $200 daily floor, $400 Stage 1 target.

> Risk tool only. Not financial advice.
