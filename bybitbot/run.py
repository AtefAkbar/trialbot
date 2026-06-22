"""CLI entrypoint: run the engine loop, a single cycle, or quick smoke checks.

  python -m bybitbot.run                 # run the closed loop (mode from BYBIT_MODE)
  python -m bybitbot.run --once          # one cycle then exit (handy for testing)
  python -m bybitbot.run --smoke         # connectivity + universe + one signal, no orders
"""
import sys
import logging

from .config import Config
from .engine import Engine
from .bybit_api import BybitAPI
from . import strategy


def _smoke(cfg):
    api = BybitAPI(cfg)
    print(f"mode={cfg.mode} base_url={cfg.base_url}")
    insts = api.instruments()
    print(f"instruments: {len(insts)}")
    tk = api.tickers()
    print(f"tickers: {len(tk)}")
    kl = api.klines("BTCUSDT", cfg.tf_entry, cfg.kline_limit)
    print(f"BTCUSDT {cfg.tf_entry}m klines: {len(kl)} (last close {kl[-1][4] if kl else 'n/a'})")
    conf = api.klines("BTCUSDT", cfg.tf_confirm, cfg.kline_limit)
    sig = strategy.evaluate("BTCUSDT", kl, conf, cfg)
    print(f"signal: side={sig.side} score={sig.score} atr={sig.atr:.2f} note={sig.note}")
    print("smoke OK — no orders placed.")


def main():
    logging.basicConfig(
        level=logging.INFO, stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    cfg = Config()
    argv = sys.argv[1:]
    if "--smoke" in argv:
        _smoke(cfg)
        return
    Engine(cfg).run(once="--once" in argv)


if __name__ == "__main__":
    main()
