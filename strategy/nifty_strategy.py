from data.indicators import add_indicators
from strategy.base_strategy import BaseStrategy, Signal


class NiftyEmaCrossoverStrategy(BaseStrategy):
    name = "nifty_ema_crossover"

    def __init__(self, min_candles=30, stop_points=25.0):
        self.min_candles = min_candles
        self.stop_points = stop_points

    def generate_signal(self, candles, position=None):
        candles = add_indicators(candles)
        if len(candles) < self.min_candles:
            return Signal("HOLD", "waiting for enough candles")

        previous = candles.iloc[-2]
        current = candles.iloc[-1]
        crossed_up = previous["ema9"] <= previous["ema21"] and current["ema9"] > current["ema21"]
        crossed_down = previous["ema9"] >= previous["ema21"] and current["ema9"] < current["ema21"]

        if position is None and crossed_up:
            return Signal(
                "BUY",
                "ema9 crossed above ema21",
                stop_loss=float(current["close"] - self.stop_points),
            )

        if position is not None and crossed_down:
            return Signal("EXIT", "ema9 crossed below ema21")

        return Signal("HOLD", "no crossover")
