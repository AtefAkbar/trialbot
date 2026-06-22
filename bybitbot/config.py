"""Engine configuration. All knobs in one place; env vars override defaults.

Mode selection (BYBIT_MODE):
  testnet  -> real Bybit V5 API against api-testnet.bybit.com, fake money (DEFAULT)
  paper    -> local simulation against live MAINNET price data, no account needed
  live     -> real orders with real money; requires BYBIT_CONFIRM_LIVE=1 + keys

Credentials come from env only, never code:
  BYBIT_API_KEY / BYBIT_API_SECRET
"""
import os
from dataclasses import dataclass, field


def _state_path():
    """Where to persist state.json. Mirror copytrader: explicit STATE_PATH wins,
    else DATA_DIR/bybit_state.json, else ./bybit_state.json for local runs."""
    explicit = os.environ.get("STATE_PATH")
    if explicit:
        return explicit
    data_dir = os.environ.get("DATA_DIR")
    if data_dir:
        return os.path.join(data_dir, "bybit_state.json")
    return "bybit_state.json"


def _ensure_state_dir(path):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)


def _env_float(name, default):
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_int(name, default):
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


@dataclass
class Config:
    # --- mode / credentials ---
    mode: str = field(default_factory=lambda: os.environ.get("BYBIT_MODE", "testnet").lower())
    api_key: str = field(default_factory=lambda: os.environ.get("BYBIT_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.environ.get("BYBIT_API_SECRET", ""))
    confirm_live: bool = field(default_factory=lambda: os.environ.get("BYBIT_CONFIRM_LIVE", "") == "1")
    category: str = "linear"            # USDT perpetuals
    recv_window: int = 5000

    # --- account / risk (capital-based; everything is a fraction of equity) ---
    account_size: float = field(default_factory=lambda: _env_float("ACCOUNT_SIZE", 1000.0))
    risk_per_trade: float = field(default_factory=lambda: _env_float("RISK_PER_TRADE", 0.005))  # 0.5% floor
    max_per_symbol: float = 0.15        # cap one symbol's notional at 15% of equity
    max_total_exposure: float = 1.50    # cap aggregate notional (leverage) at 1.5x equity
    max_leverage: float = 5.0           # exchange leverage ceiling per position
    max_concurrent_positions: int = 6   # never hold more than this many at once
    min_order_usd: float = 5.0          # skip dust orders a real venue would reject

    # --- profit scaling: risk grows only while the book is in profit ---
    risk_scale_max: float = 2.0         # at full profit-state, risk up to 2x the floor
    scale_profit_ref: float = 0.10      # equity +10% over start => fully scaled up

    # --- initial stop + trailing ratchet (the core ask) ---
    atr_period: int = 14
    init_stop_atr: float = 1.2          # initial stop = entry -/+ 1.2*ATR (tight)
    breakeven_at_r: float = 1.0         # lock breakeven once +1R in profit
    trail_atr_far: float = 2.5          # trail band (ATR mult) just after breakeven
    trail_atr_near: float = 0.8         # trail band (ATR mult) deep in profit -> tightens
    trail_tighten_r: float = 4.0        # R at which the band reaches trail_atr_near

    # --- pyramiding ("HFT-like more bets" while a winner runs) ---
    pyramid_enabled: bool = True
    pyramid_max_adds: int = 2           # extra units stacked on a winner
    pyramid_trigger_r: float = 1.0      # add one unit each +1R of further progress
    pyramid_add_frac: float = 0.5       # each add is 50% of the base unit's risk

    # --- circuit breakers (portfolio protection) ---
    daily_loss_halt: float = 0.02       # halt NEW entries if realized day PnL <= -2% equity
    max_drawdown_halt: float = 0.15     # halt new entries if equity down 15% from peak

    # --- signal / strategy ---
    tf_entry: str = "5"                 # Bybit kline interval (minutes) for entries
    tf_confirm: str = "15"              # higher TF trend confirmation
    kline_limit: int = 200              # bars pulled per symbol per scan
    hma_len: int = 50
    trend_len: int = 3
    swing_len: int = 20
    require_confirm_tf: bool = True     # entry TF and confirm TF trend must agree

    # --- universe ---
    min_turnover_usd: float = 20_000_000.0   # 24h quote turnover floor (liquidity)
    max_universe: int = 60                    # cap symbols scanned per cycle (rate limits)
    symbol_whitelist: tuple = ()              # if set, ONLY trade these symbols
    symbol_blocklist: tuple = ()

    # --- simulated execution costs (paper/testnet accounting fidelity) ---
    taker_fee: float = 0.00055          # Bybit linear taker ~0.055%
    slippage: float = 0.0005            # 0.05% adverse on simulated fills

    # --- loop timing (seconds) ---
    poll_interval_s: int = field(default_factory=lambda: _env_int("POLL_INTERVAL_S", 45))
    universe_refresh_s: int = 1800      # re-enumerate / re-rank the universe every 30m

    # --- persistence ---
    state_path: str = field(default_factory=_state_path)
    log_path: str = "bybitbot.log"

    def __post_init__(self):
        _ensure_state_dir(self.state_path)
        if self.mode not in ("testnet", "paper", "live"):
            self.mode = "testnet"

    @property
    def base_url(self):
        # paper trades against mainnet *data* (read-only); testnet uses the testnet host.
        return "https://api-testnet.bybit.com" if self.mode == "testnet" else "https://api.bybit.com"

    @property
    def is_live(self):
        return self.mode == "live"
