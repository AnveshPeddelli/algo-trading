from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade: float = 0.01
    max_quantity: int = 500
    default_stop_points: float = 25.0


class RiskManager:
    def __init__(self, config=None):
        self.config = config or RiskConfig()

    def position_size(self, capital, entry, stop):
        stop_distance = abs(float(entry) - float(stop))
        if stop_distance <= 0:
            return 0

        risk_amount = float(capital) * self.config.risk_per_trade
        quantity = int(risk_amount / stop_distance)
        return max(0, min(quantity, self.config.max_quantity))

    def size_for_signal(self, capital, price, signal):
        stop = signal.stop_loss
        if stop is None:
            stop = float(price) - self.config.default_stop_points
        return self.position_size(capital, price, stop)


def position_size(capital, entry, stop):
    return RiskManager().position_size(capital, entry, stop)
