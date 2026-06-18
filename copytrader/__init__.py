"""Polymarket copy-trading bot — paper engine.

Copies the top-N leaderboard traders (by PnL), sizes each copy from account
size + a risk budget, and runs a closed loop that mirrors entries/exits and
applies independent stop-loss / take-profit.

PAPER ONLY: simulates fills against real live Polymarket prices and tracks a
virtual portfolio. No real orders are ever placed (see broker.py).
"""
