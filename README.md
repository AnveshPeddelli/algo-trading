# Algo Trader

Paper-trading harness for Upstox market data. The framework handles login, websocket ticks, candle building, risk sizing, and simulated fills so strategy work can stay inside `strategy/`.

## Setup

1. Create a local `.env` from `.env.example`.
2. Set `UPSTOX_API_KEY` and `UPSTOX_API_SECRET`.
3. Set `PAPER_INSTRUMENT_KEY` to the instrument you want to paper trade.
4. Install dependencies:

```powershell
pip install -r requirements.txt
```

## Run Paper Trading

```powershell
python main.py
```

The app opens the Upstox login page, subscribes to the configured instrument, builds candles, runs the active strategy on completed candles, sizes entries, and prints paper fills with running equity. Stops are checked on every tick.

## Strategy Work

Most strategy changes should happen in `strategy/nifty_strategy.py`.

Implement or replace `generate_signal(self, candles, position=None)` and return:

- `Signal("BUY", reason="...", stop_loss=price)`
- `Signal("EXIT", reason="...")`
- `Signal("HOLD", reason="...")`

The rest of the app will handle position sizing and paper execution.
