"""Risk + sizing. Capital-based: every bet is sized so the distance to the
initial stop equals a fixed fraction of equity (the user's 0.5% floor), with
per-symbol, total-exposure and leverage caps on top.

Risk-per-trade scales UP only while the book is in profit (the "act like an HFT
when winning" ask) and never below the floor — so a losing streak automatically
shrinks bet size.
"""


def scaled_risk_frac(equity, start_equity, cfg):
    """Risk fraction for a new trade, between the floor and risk_scale_max*floor,
    interpolated by how far equity sits above its starting point."""
    floor = cfg.risk_per_trade
    if equity <= start_equity or cfg.scale_profit_ref <= 0:
        return floor
    gain = (equity - start_equity) / start_equity
    frac = min(1.0, gain / cfg.scale_profit_ref)
    return floor * (1.0 + (cfg.risk_scale_max - 1.0) * frac)


def _round_step(qty, step):
    if step and step > 0:
        return (int(qty / step)) * step
    return qty


def size_trade(entry, stop, equity, start_equity, symbol_notional, total_notional,
               cash, meta, cfg):
    """Units for a NEW position so that (entry-stop) risk == scaled risk budget,
    clamped by per-symbol / total-exposure / leverage / cash caps.

    Returns (qty, notional, risk_usd). qty=0 when there's no room or it's dust.
    meta: instrument filters dict {lot_step, min_qty, ...} or None.
    """
    risk_dist = abs(entry - stop)
    if entry <= 0 or risk_dist <= 0:
        return 0.0, 0.0, 0.0

    risk_usd = scaled_risk_frac(equity, start_equity, cfg) * equity
    qty = risk_usd / risk_dist
    notional = qty * entry

    # caps (in notional terms)
    per_symbol_head = max(0.0, cfg.max_per_symbol * equity - symbol_notional)
    total_head = max(0.0, cfg.max_total_exposure * equity - total_notional)
    leverage_cap = cfg.max_leverage * equity                      # never lever a single bet past this
    margin_cap = cash * cfg.max_leverage                          # can't post more margin than we have
    notional = min(notional, per_symbol_head, total_head, leverage_cap, margin_cap)

    if notional < cfg.min_order_usd:
        return 0.0, 0.0, 0.0
    qty = notional / entry

    if meta:
        qty = _round_step(qty, meta.get("lot_step", 0))
        if qty < meta.get("min_qty", 0):
            return 0.0, 0.0, 0.0
    if qty <= 0:
        return 0.0, 0.0, 0.0
    return qty, qty * entry, qty * risk_dist


def can_pyramid(pos, equity, total_notional, cfg):
    """True if we may stack another unit on an existing winner.
    Gate: pyramiding enabled, under the add cap, position is in profit past the
    next trigger, and total exposure still has headroom."""
    if not cfg.pyramid_enabled:
        return False
    if pos.get("adds", 0) >= cfg.pyramid_max_adds:
        return False
    r = pos.get("peak_r", 0.0)
    needed = cfg.breakeven_at_r + (pos.get("adds", 0) + 1) * cfg.pyramid_trigger_r
    if r < needed:
        return False
    if total_notional >= cfg.max_total_exposure * equity:
        return False
    return True
