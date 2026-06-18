"""Risk + sizing. Fixed-fraction per copy with per-market and total-exposure caps."""


def size_copy(price, asset, portfolio, cfg):
    """How much to deploy on a NEW copy at `price`.
    Returns (notional, shares), both 0 if there is no headroom.

    notional = min(
        risk_per_copy * account,                 # base bet
        per-market headroom for this market,     # cap concentration
        total-exposure headroom,                 # cap aggregate risk
        available cash,                          # can't spend what we don't have
    )
    """
    if price <= 0:
        return 0.0, 0.0

    desired = cfg.risk_per_copy * cfg.account_size

    per_market_cap = cfg.max_per_market * cfg.account_size
    per_market_head = max(0.0, per_market_cap - portfolio.market_notional(asset))

    total_cap = cfg.max_total_exposure * cfg.account_size
    total_head = max(0.0, total_cap - portfolio.open_notional())

    notional = min(desired, per_market_head, total_head, portfolio.cash)
    if notional < cfg.min_order_usd:        # below venue minimum -> a real exchange
        return 0.0, 0.0                     # would reject; skip for paper==live fidelity
    return notional, notional / price


def stop_take_levels(entry_price, cfg):
    """Independent SL/TP price levels for a long outcome-token position."""
    sl = entry_price * (1.0 - cfg.stop_loss_pct)
    tp = entry_price * (1.0 + cfg.take_profit_pct)
    return sl, tp
