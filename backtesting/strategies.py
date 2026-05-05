import pandas as pd

from data.indicators import add_indicators
from strategy.base_strategy import BaseStrategy, Signal
from strategy.nifty_strategy import NiftyEmaCrossoverStrategy


class RsiMeanReversionStrategy(BaseStrategy):
    name = "rsi_mean_reversion"

    def __init__(self, min_candles=20, stop_points=30.0, oversold=35.0, overbought=65.0):
        self.min_candles = min_candles
        self.stop_points = stop_points
        self.oversold = oversold
        self.overbought = overbought

    def generate_signal(self, candles, position=None):
        if len(candles) < self.min_candles:
            return Signal("HOLD", "waiting for enough candles")

        df = candles.copy()
        df["rsi"] = _rsi(df["close"])
        current = df.iloc[-1]
        price = float(current["close"])

        if position is None and current["rsi"] <= self.oversold:
            return Signal("BUY", f"rsi below {self.oversold:.0f}", stop_loss=price - self.stop_points)

        if position is not None and current["rsi"] >= self.overbought:
            return Signal("EXIT", f"rsi above {self.overbought:.0f}")

        return Signal("HOLD", "no rsi setup")


class BreakoutStrategy(BaseStrategy):
    name = "breakout_20"

    def __init__(self, lookback=20, stop_points=35.0):
        self.lookback = lookback
        self.min_candles = lookback + 1
        self.stop_points = stop_points

    def generate_signal(self, candles, position=None):
        if len(candles) < self.min_candles:
            return Signal("HOLD", "waiting for enough candles")

        recent = candles.iloc[-self.min_candles : -1]
        current = candles.iloc[-1]
        breakout_level = float(recent["high"].max())
        breakdown_level = float(recent["low"].min())
        price = float(current["close"])

        if position is None and price > breakout_level:
            return Signal("BUY", "20-candle breakout", stop_loss=price - self.stop_points)

        if position is not None and price < breakdown_level:
            return Signal("EXIT", "20-candle breakdown")

        return Signal("HOLD", "inside breakout range")


def build_strategy_catalog(stop_points):
    return {
        "EMA Crossover": lambda: NiftyEmaCrossoverStrategy(stop_points=stop_points),
        "RSI Mean Reversion": lambda: RsiMeanReversionStrategy(stop_points=stop_points),
        "20 Candle Breakout": lambda: BreakoutStrategy(stop_points=max(stop_points, 35.0)),
    }


def rank_runs(runs):
    return sorted(
        runs,
        key=lambda run: (run.net_profit, run.win_rate, -run.max_drawdown),
        reverse=True,
    )


def _rsi(close_series, period=14):
    delta = close_series.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)
