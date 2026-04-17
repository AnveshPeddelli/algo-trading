from dataclasses import dataclass


@dataclass(frozen=True)
class Signal:
    action: str
    reason: str = ""
    stop_loss: float | None = None

    @property
    def is_trade(self):
        return self.action in {"BUY", "SELL", "EXIT"}


class BaseStrategy:
    name = "base"

    def generate_signal(self, candles, position=None):
        raise NotImplementedError
