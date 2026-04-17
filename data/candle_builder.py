from datetime import datetime

import pandas as pd


class CandleBuilder:
    def __init__(self, interval_minutes=1):
        if interval_minutes <= 0:
            raise ValueError("interval_minutes must be greater than zero")
        self.interval_minutes = interval_minutes
        self._ticks = []

    def on_tick(self, price, timestamp=None):
        timestamp = timestamp or datetime.now()
        if isinstance(timestamp, (int, float)):
            timestamp = datetime.fromtimestamp(timestamp / 1000)
        self._ticks.append((timestamp, float(price)))

    update = on_tick

    def get_dataframe(self):
        if not self._ticks:
            return pd.DataFrame(columns=["open", "high", "low", "close"])

        df = pd.DataFrame(self._ticks, columns=["time", "price"])
        bucket = f"{self.interval_minutes}min"
        df["candle_time"] = df["time"].dt.floor(bucket)
        candles = df.groupby("candle_time").agg(
            open=("price", "first"),
            high=("price", "max"),
            low=("price", "min"),
            close=("price", "last"),
        )
        candles.index.name = "time"
        return candles

    def latest_close(self):
        if not self._ticks:
            return None
        return self._ticks[-1][1]
