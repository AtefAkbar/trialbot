"""Cloud/local entrypoint: engine loop + dashboard in ONE process.

The engine runs in a daemon thread writing state.json; the dashboard HTTP server
runs in the main thread bound to 0.0.0.0:$PORT. They share one Control instance
so the browser can pause/flatten the live engine, and the dashboard reads the
engine's live scanner ranking and halt status directly.

  BYBIT_MODE=testnet PORT=8787 python -m bybitbot.serve
"""
import os
import sys
import logging
import threading
from http.server import ThreadingHTTPServer

from .config import Config
from .engine import Engine
from . import dashboard


def main():
    logging.basicConfig(
        level=logging.INFO, stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    cfg = Config()
    logging.info("mode=%s base_url=%s state=%s", cfg.mode, cfg.base_url, cfg.state_path)

    engine = Engine(cfg)
    threading.Thread(target=engine.run, daemon=True, name="engine").start()

    # wire the dashboard to the same config + live engine
    dashboard.STATE_PATH = cfg.state_path
    dashboard.ENGINE = engine
    dashboard.Handler.cfg = cfg
    port = int(os.environ.get("PORT", "8787"))
    host = os.environ.get("HOST", "0.0.0.0")
    srv = ThreadingHTTPServer((host, port), dashboard.Handler)
    logging.info("bybitbot serving (engine + dashboard) on %s:%d", host, port)
    srv.serve_forever()


if __name__ == "__main__":
    main()
