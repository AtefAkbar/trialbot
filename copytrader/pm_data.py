"""Polymarket read-only data layer (free, no API key).

Mirrors the retry/backoff + polite-sleep pattern from altcoin_backtest/data.py.
Endpoints:
  - leaderboard : https://data-api.polymarket.com/v1/leaderboard
  - positions   : https://data-api.polymarket.com/positions
  - midpoint    : https://clob.polymarket.com/midpoint
"""
import time
import requests

DATA = "https://data-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

_session = requests.Session()
_session.headers.update({"User-Agent": "copytrader/1.0 (paper)"})


def _get(url, params=None, tries=5):
    for i in range(tries):
        try:
            r = _session.get(url, params=params, timeout=20)
            if r.status_code == 200:
                return r.json()
            time.sleep(1.0 * (i + 1))      # rate-limit / transient -> back off
        except Exception:
            time.sleep(1.0 * (i + 1))
    raise RuntimeError(f"GET failed: {url} {params}")


def top_traders(n=10, category="OVERALL", metric="pnl"):
    """Top-N leaderboard wallets, ranked by `metric` (pnl|vol), descending."""
    rows = _get(f"{DATA}/v1/leaderboard", {"category": category})
    out = []
    for r in rows:
        out.append({
            "wallet": r["proxyWallet"],
            "user_name": r.get("userName") or r["proxyWallet"][:10],
            "pnl": float(r.get("pnl") or 0.0),
            "vol": float(r.get("vol") or 0.0),
        })
    out.sort(key=lambda x: x[metric], reverse=True)
    return out[:n]


def positions(wallet, limit=500):
    """Current positions for a wallet. Returns the raw list of position dicts."""
    rows = _get(f"{DATA}/positions", {"user": wallet, "limit": limit})
    return rows if isinstance(rows, list) else []


def midpoint(token_id):
    """Live CLOB midpoint for an outcome token, or None if no book exists.

    Single fast attempt (no retry/backoff): resolved/closed markets return a
    non-200, and we must NOT burn ~15s of backoff per token — None just falls
    back to the position's reported curPrice for marking.
    """
    try:
        r = _session.get(f"{CLOB}/midpoint", params={"token_id": token_id}, timeout=5)
        if r.status_code != 200:
            return None
        j = r.json()
    except Exception:
        return None
    if isinstance(j, dict) and "mid" in j:
        try:
            return float(j["mid"])
        except (TypeError, ValueError):
            return None
    return None
