"""Snapshot-diff logic: baseline is silent; opens/adds/trims/closes detected."""
from copytrader.config import Config
from copytrader.tracker import Tracker


def _pos(asset, size, avg=0.5, cur=0.5):
    return {"asset": asset, "size": size, "avgPrice": avg, "curPrice": cur,
            "outcome": "Yes", "conditionId": "c" + asset, "title": "T" + asset,
            "slug": "s" + asset}


class FakeData:
    """Returns the next scripted position list each time positions() is called."""
    def __init__(self, script):
        self.script = {w: list(seq) for w, seq in script.items()}

    def positions(self, wallet, limit=500):
        seq = self.script[wallet]
        return seq.pop(0) if len(seq) > 1 else seq[0]

    def top_traders(self, n, category, metric):
        return [{"wallet": w, "user_name": w} for w in self.script]


def test_baseline_then_diffs():
    W = "0xW"
    data = FakeData({W: [
        [_pos("A", 10)],                       # baseline (silent)
        [_pos("A", 10), _pos("B", 5)],         # poll1: B opened
        [_pos("A", 12), _pos("B", 5)],         # poll2: A added +2
        [_pos("A", 12), _pos("B", 2)],         # poll3: B trimmed -3
        [_pos("A", 12)],                       # poll4: B closed (gone)
    ]})
    tr = Tracker(Config(copy_existing_on_start=False), data)

    added, _ = tr.refresh_leaderboard()
    assert added == [W]

    s1 = tr.poll()
    assert len(s1) == 1 and s1[0].kind == "OPEN" and s1[0].asset == "B"

    s2 = tr.poll()
    assert len(s2) == 1 and s2[0].kind == "ADD" and s2[0].asset == "A"
    assert abs(s2[0].size_delta - 2) < 1e-9 and abs(s2[0].trader_size - 12) < 1e-9

    s3 = tr.poll()
    assert len(s3) == 1 and s3[0].kind == "TRIM" and s3[0].asset == "B"
    assert abs(s3[0].size_delta + 3) < 1e-9

    s4 = tr.poll()
    assert len(s4) == 1 and s4[0].kind == "CLOSE" and s4[0].asset == "B"
    assert s4[0].trader_size == 0.0


def test_below_min_counts_as_close():
    W = "0xW"
    data = FakeData({W: [
        [_pos("A", 10)],
        [_pos("A", 0.4)],          # drops under min_position_size (1.0) -> CLOSE
    ]})
    tr = Tracker(Config(copy_existing_on_start=False), data)
    tr.refresh_leaderboard()
    sigs = tr.poll()
    assert len(sigs) == 1 and sigs[0].kind == "CLOSE"


def test_active_market_filter():
    tr = Tracker(Config(), FakeData({"0xW": [[]]}))
    live = {"redeemable": False, "curPrice": 0.66, "endDate": "2999-01-01"}
    assert tr._tradeable(live)
    assert not tr._tradeable({"redeemable": True, "curPrice": 0.0})      # resolved/claimable
    assert not tr._tradeable({"redeemable": False, "curPrice": 0.0})     # loser, pinned to 0
    assert not tr._tradeable({"redeemable": False, "curPrice": 1.0})     # winner, pinned to 1
    assert not tr._tradeable({"redeemable": False, "curPrice": 0.5,
                              "endDate": "2000-01-01"})                  # expired


if __name__ == "__main__":
    test_baseline_then_diffs()
    test_below_min_counts_as_close()
    test_active_market_filter()
    print("test_diff OK")
