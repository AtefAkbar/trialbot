"""Shared runtime controls the dashboard can toggle and the engine obeys.

serve.py runs the engine and the dashboard in one process, so a single shared
Control instance lets the browser pause entries or flatten the book without any
IPC. Thread-safe via a lock; flags are advisory and checked once per cycle.
"""
import threading


class Control:
    def __init__(self):
        self._lock = threading.Lock()
        self.paused = False              # halt NEW entries (open trades still managed)
        self.flatten = False             # one-shot: close everything, then clears
        self.blocklist = set()           # symbols the user never wants traded

    def snapshot(self):
        with self._lock:
            return {"paused": self.paused, "flatten": self.flatten,
                    "blocklist": sorted(self.blocklist)}

    def set_paused(self, val):
        with self._lock:
            self.paused = bool(val)

    def request_flatten(self):
        with self._lock:
            self.flatten = True

    def take_flatten(self):
        with self._lock:
            v = self.flatten
            self.flatten = False
            return v

    def block(self, symbol):
        with self._lock:
            self.blocklist.add(symbol)

    def unblock(self, symbol):
        with self._lock:
            self.blocklist.discard(symbol)

    def is_blocked(self, symbol):
        with self._lock:
            return symbol in self.blocklist


# process-wide singleton shared by engine + dashboard
CONTROL = Control()
