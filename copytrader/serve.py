"""Cloud entrypoint: run the engine loop AND the dashboard in ONE process.

Designed for any host that runs a persistent process (Railway / Render / Fly.io /
a plain VPS). The engine runs in a background thread writing state.json; the
dashboard HTTP server runs in the main thread bound to 0.0.0.0:$PORT so the
platform can route public traffic to it. Paper only — no real orders.

  PORT=8080 python -m copytrader.serve
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

    # engine loop in a daemon thread (writes state.json every cycle)
    engine = Engine(cfg)
    threading.Thread(target=engine.run, daemon=True, name="engine").start()

    # dashboard in the main thread, reading the same state file
    dashboard.STATE_PATH = cfg.state_path
    dashboard.Handler.cfg = cfg
    port = int(os.environ.get("PORT", "8787"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), dashboard.Handler)
    logging.info("copytrader serving (engine + dashboard) on 0.0.0.0:%d", port)
    srv.serve_forever()


if __name__ == "__main__":
    main()
