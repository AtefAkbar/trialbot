"""Engine configuration. All knobs in one place."""
from dataclasses import dataclass


@dataclass
class Config:
    # --- account / risk ---
    account_size: float = 100.0         # virtual USDC bankroll (realistic deploy size)
    risk_per_copy: float = 0.02         # notional per new copy = 2% of account
    max_per_market: float = 0.10        # cap any single market at 10% of account
    max_total_exposure: float = 0.60    # cap total open notional at 60% of account
    min_order_usd: float = 1.0          # Polymarket per-order minimum — skip copies
                                        # smaller than this (keeps paper == live)

    # --- independent risk exits (as fraction of entry price) ---
    stop_loss_pct: float = 0.50         # close if price falls 50% below entry
    take_profit_pct: float = 1.00       # close if price doubles from entry

    # --- simulated execution costs ---
    fee: float = 0.0                    # Polymarket charges no maker/taker fee today
    slippage: float = 0.01              # adverse 1% on simulated fills

    # --- trader selection ---
    top_n: int = 10
    leaderboard_category: str = "OVERALL"
    leaderboard_metric: str = "pnl"     # rank by realized+unrealized PnL
    min_position_size: float = 1.0      # ignore trader dust positions (shares)
    copy_existing_on_start: bool = True # mirror a trader's CURRENT book on onboard
                                        # (False = only copy trades made after start)
    active_markets_only: bool = True    # only copy positions in markets still open for
                                        # trading — skip resolved/redeemable/expired

    # --- loop timing (seconds) ---
    poll_interval_s: int = 30
    rerank_interval_s: int = 3600       # refresh the top-N once an hour

    # --- persistence ---
    state_path: str = "state.json"
    log_path: str = "copytrader.log"
