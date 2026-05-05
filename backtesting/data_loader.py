import math
import random

import pandas as pd


def load_price_data(csv_path):
    df = pd.read_csv(csv_path)
    lower_map = {column.lower(): column for column in df.columns}

    time_column = _find_column(lower_map, ["time", "datetime", "date", "timestamp"])
    open_column = _find_column(lower_map, ["open"])
    high_column = _find_column(lower_map, ["high"])
    low_column = _find_column(lower_map, ["low"])
    close_column = _find_column(lower_map, ["close"])

    normalized = pd.DataFrame(
        {
            "time": pd.to_datetime(df[time_column]),
            "open": pd.to_numeric(df[open_column], errors="coerce"),
            "high": pd.to_numeric(df[high_column], errors="coerce"),
            "low": pd.to_numeric(df[low_column], errors="coerce"),
            "close": pd.to_numeric(df[close_column], errors="coerce"),
        }
    ).dropna()

    normalized = normalized.sort_values("time").drop_duplicates("time")
    normalized = normalized.set_index("time")
    return normalized


def generate_demo_data(rows=300, start_price=24000.0, interval_minutes=1):
    random.seed(7)
    timestamps = pd.date_range("2026-01-01 09:15:00", periods=rows, freq=f"{interval_minutes}min")
    prices = []
    previous_close = start_price

    for index, timestamp in enumerate(timestamps):
        drift = math.sin(index / 18.0) * 10 + math.cos(index / 33.0) * 4
        move = drift + random.uniform(-12, 12)
        open_price = previous_close
        close_price = max(100.0, open_price + move)
        high_price = max(open_price, close_price) + random.uniform(1, 8)
        low_price = min(open_price, close_price) - random.uniform(1, 8)
        prices.append((timestamp, open_price, high_price, low_price, close_price))
        previous_close = close_price

    return pd.DataFrame(prices, columns=["time", "open", "high", "low", "close"]).set_index("time")


def _find_column(lower_map, candidates):
    for candidate in candidates:
        if candidate in lower_map:
            return lower_map[candidate]
    raise ValueError(
        "CSV is missing required columns. Expected at least time/date and open/high/low/close."
    )
