"""End-to-end engine wiring against a scripted data layer (no network):
entry -> proportional add -> mirror-exit, and independent take-profit."""
import os
from copytrader.config import Config
from copytrader.engine import Engine


def _pos(size):
    return {"asset": "A", "size": size, "avgPrice": 0.4, "curPrice": 0.4,
            "outcome": "Yes", "conditionId": "cA", "title": "TA", "slug": "sA"}


class FakeData:
    def __init__(self, lists, px=0.4):
        self.lists = list(lists)
        self.px = px

    def top_traders(self, n, category, metric):
        return [{"wallet": "0xW", "user_name": "W"}]

    def positions(self, wallet, limit=500):
        return self.lists.pop(0) if len(self.lists) > 1 else self.lists[0]

    def midpoint(self, token_id):
        return self.px


def _engine(lists, path, **over):
    if os.path.exists(path):
        os.remove(path)
    base = dict(account_size=10_000, risk_per_copy=0.02, slippage=0.0,
                rerank_interval_s=10**9, state_path=path,
                copy_existing_on_start=False)
    base.update(over)
    return Engine(Config(**base), FakeData(lists))


def test_entry_add_mirror_exit():
    eng = _engine([[], [_pos(100)], [_pos(200)], []], "/tmp/ct_eng1.json")
    eng.cycle()                                   # baseline [] then OPEN A
    p = eng.portfolio.get("0xW", "A")
    assert p and abs(p["shares"] - 500) < 1e-6    # $200 / 0.40
    assert abs(p["ratio"] - 5.0) < 1e-6           # 500 ours / 100 trader

    eng.cycle()                                   # trader doubles -> we mirror to 1000
    assert abs(eng.portfolio.get("0xW", "A")["shares"] - 1000) < 1e-6

    eng.data.px = 0.5
    eng.cycle()                                   # trader closes -> mirror exit @0.5
    assert not eng.portfolio.has("0xW", "A")
    assert abs(eng.portfolio.realized_pnl - 100) < 1e-6   # (0.5-0.4)*1000


def test_independent_take_profit():
    eng = _engine([[], [_pos(100)], [_pos(100)]], "/tmp/ct_eng2.json",
                  take_profit_pct=1.0, stop_loss_pct=0.5)
    eng.cycle()                                   # OPEN A, entry 0.40, tp 0.80
    eng.data.px = 0.9
    eng.cycle()                                   # no trader change, but TP fires
    assert not eng.portfolio.has("0xW", "A")
    assert abs(eng.portfolio.realized_pnl - 250) < 1e-6   # (0.9-0.4)*500


def test_add_respects_per_market_cap():
    # trader scales 10 -> 1000 shares; our mirror must NOT exceed the 10% market cap.
    eng = _engine([[], [_pos(10)], [_pos(1000)]], "/tmp/ct_eng3.json", account_size=100)
    eng.data.px = 0.5
    eng.cycle()                                   # OPEN: $2 risk / 0.5 = 4 shares
    assert abs(eng.portfolio.get("0xW", "A")["shares"] - 4) < 1e-6
    eng.cycle()                                   # trader 100x's it -> we cap at $10 = 20 sh
    sh = eng.portfolio.get("0xW", "A")["shares"]
    assert abs(sh - 20) < 1e-6, f"expected 20 (the per-market cap), got {sh}"


if __name__ == "__main__":
    test_entry_add_mirror_exit()
    test_independent_take_profit()
    test_add_respects_per_market_cap()
    print("test_engine OK")
