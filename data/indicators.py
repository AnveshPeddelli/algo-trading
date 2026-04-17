def add_indicators(df):
    df = df.copy()
    if df.empty:
        return df

    df["ema9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
    return df
