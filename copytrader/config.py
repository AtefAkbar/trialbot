"""Engine configuration. All knobs in one place."""
import os
from dataclasses import dataclass, field


def _state_path():
    """Where to persist state.json.
    On ephemeral hosts (Railway/Render/Fly), point this at a mounted persistent
    volume via env vars so the paper account survives redeploys/restarts:
      - STATE_PATH=/data/state.json   (explicit file path), or
      - DATA_DIR=/data                (dir; state.json is written inside it)
    Defaults to ./state.json for local runs (no absolute path, so it never tries
    to write to a read-only/non-existent dir like /app on machines without it).
    Production sets STATE_PATH=/data/state.json (its mounted volume) via env var.
    """
    explicit = os.environ.get("STATE_PATH")
    if explicit:
        return explicit
    data_dir = os.environ.get("DATA_DIR")
    if data_dir:
        return os.path.join(data_dir, "state.json")
    return "state.json"


def _ensure_state_dir(path):
    """Create the directory that will hold state.json if it doesn't exist yet."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)


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
    # Defaults to /app/state/state.json (Railway persistent volume mount).
    # Override with STATE_PATH or DATA_DIR env vars for other platforms.
    state_path: str = field(default_factory=_state_path)
    log_path: str = "copytrader.log"

    def __post_init__(self):
        # Guarantee the directory exists before the portfolio tries to read/write it.
        _ensure_state_dir(self.state_path)
