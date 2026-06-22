"""Autonomous Bybit perpetual-futures trading bot.

Small low-risk bets on a short timeframe with a ratcheting trailing stop that
tightens as profit grows, pyramiding while in profit, and capital-based risk
management (per-trade risk, exposure caps, daily-loss circuit breaker).

Defaults to Bybit TESTNET. Live order placement is wired but stays OFF unless
the user themselves supplies keys AND sets confirm_live — see broker.py.
"""
