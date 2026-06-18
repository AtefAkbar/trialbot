"""Entrypoint.

  python -m copytrader.run            # run the closed loop forever (paper)
  python -m copytrader.run --once     # a single cycle (smoke test)
  python -m copytrader.run --traders  # just print the live top-N, no engine
"""
import sys
import logging

from .config import Config
from .engine import Engine
from . import pm_data


def _setup_logging(path):
    fmt = "%(asctime)s %(levelname)s %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt, datefmt="%H:%M:%S",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(path)])


def main():
    cfg = Config()

    if "--traders" in sys.argv:
        for t in pm_data.top_traders(cfg.top_n, cfg.leaderboard_category, cfg.leaderboard_metric):
            print(f"  {t['user_name']:<20} pnl=${t['pnl']:>14,.0f}  vol=${t['vol']:>14,.0f}  {t['wallet']}")
        return

    _setup_logging(cfg.log_path)
    Engine(cfg).run(once="--once" in sys.argv)


if __name__ == "__main__":
    main()
