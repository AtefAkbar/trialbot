"""Execution brokers.

PaperBroker is the ONLY enabled implementation: it applies adverse slippage and
returns a fill price; all accounting happens in the portfolio. It moves no money.

LiveBroker is a deliberate stub. Per this project's standing rule (signals +
paper only, never place live orders or move money) it raises unless the user
*themselves* supplies a private key AND sets confirm_live=True. Wiring it to the
real CLOB is out of scope here.
"""


class PaperBroker:
    live = False

    def __init__(self, slippage):
        self.slippage = slippage

    def fill(self, side, price):
        """side: +1 buy, -1 sell. Adverse slippage: pay up to buy, get less to sell."""
        return price * (1.0 + self.slippage * side)


class LiveBroker:
    live = True

    def __init__(self, private_key=None, confirm_live=False):
        if not (private_key and confirm_live):
            raise NotImplementedError(
                "LiveBroker is disabled. This project is paper-only. To ever enable "
                "real orders you must supply your own private key AND set "
                "confirm_live=True yourself — and implement order placement against "
                "the Polymarket CLOB, which is intentionally not done here."
            )
        raise NotImplementedError("Live order placement is not implemented.")
