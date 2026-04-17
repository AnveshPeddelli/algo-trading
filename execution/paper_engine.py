from dataclasses import dataclass
from datetime import datetime


@dataclass
class Position:
    symbol: str
    side: str
    quantity: int
    entry_price: float
    entry_time: datetime
    stop_loss: float | None = None


@dataclass
class Fill:
    time: datetime
    symbol: str
    action: str
    quantity: int
    price: float
    pnl: float = 0.0
    reason: str = ""


class PaperTrader:
    def __init__(self, starting_capital=100000.0):
        self.starting_capital = float(starting_capital)
        self.cash = float(starting_capital)
        self.position = None
        self.fills = []

    @property
    def realized_pnl(self):
        return self.cash - self.starting_capital

    def buy(self, symbol, price, quantity, stop_loss=None, reason=""):
        if self.position is not None or quantity <= 0:
            return None

        self.position = Position(
            symbol=symbol,
            side="LONG",
            quantity=int(quantity),
            entry_price=float(price),
            entry_time=datetime.now(),
            stop_loss=stop_loss,
        )
        fill = Fill(datetime.now(), symbol, "BUY", int(quantity), float(price), reason=reason)
        self.fills.append(fill)
        print(f"PAPER BUY {symbol} qty={quantity} price={price:.2f} reason={reason}")
        return fill

    def exit(self, price, reason=""):
        if self.position is None:
            return None

        pnl = (float(price) - self.position.entry_price) * self.position.quantity
        self.cash += pnl
        fill = Fill(
            datetime.now(),
            self.position.symbol,
            "EXIT",
            self.position.quantity,
            float(price),
            pnl=pnl,
            reason=reason,
        )
        self.fills.append(fill)
        print(
            f"PAPER EXIT {self.position.symbol} qty={self.position.quantity} "
            f"price={price:.2f} pnl={pnl:.2f} reason={reason}"
        )
        self.position = None
        return fill

    def check_stop(self, price):
        if self.position is None or self.position.stop_loss is None:
            return None
        if float(price) <= self.position.stop_loss:
            return self.exit(price, "stop loss hit")
        return None

    def mark_to_market(self, last_price):
        if self.position is None or last_price is None:
            return self.cash
        unrealized = (float(last_price) - self.position.entry_price) * self.position.quantity
        return self.cash + unrealized

    def execute(self, signal, price, quantity=1, symbol="UNKNOWN"):
        action = signal.action if hasattr(signal, "action") else signal
        reason = getattr(signal, "reason", "")
        stop_loss = getattr(signal, "stop_loss", None)

        if action == "BUY":
            return self.buy(symbol, price, quantity, stop_loss=stop_loss, reason=reason)
        if action in {"SELL", "EXIT"}:
            return self.exit(price, reason=reason)
        return None
