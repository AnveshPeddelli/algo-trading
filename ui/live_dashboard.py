import queue
import threading
import tkinter as tk
from collections import OrderedDict
from datetime import datetime
from tkinter import messagebox, ttk

from config.auto_login import get_login_token
from config.settings import get_settings
from data.market_data import MarketData
from data.upstox_ws import UpstoxWS


class LiveCandleStore:
    def __init__(self, interval_minutes=1, max_candles=120):
        self.interval_minutes = interval_minutes
        self.max_candles = max_candles
        self._candles = OrderedDict()

    def on_tick(self, price, timestamp=None):
        tick_time = timestamp or datetime.now()
        if isinstance(tick_time, (int, float)):
            tick_time = datetime.fromtimestamp(tick_time / 1000)
        bucket_minute = tick_time.minute - (tick_time.minute % self.interval_minutes)
        candle_time = tick_time.replace(minute=bucket_minute, second=0, microsecond=0)
        price = float(price)

        candle = self._candles.get(candle_time)
        if candle is None:
            self._candles[candle_time] = {
                "open": price,
                "high": price,
                "low": price,
                "close": price,
            }
        else:
            candle["high"] = max(candle["high"], price)
            candle["low"] = min(candle["low"], price)
            candle["close"] = price

        while len(self._candles) > self.max_candles:
            self._candles.popitem(last=False)

    def rows(self, limit=20):
        items = list(self._candles.items())[-limit:]
        return [(candle_time, values.copy()) for candle_time, values in items]


class LiveMarketSession:
    def __init__(self, settings, event_queue):
        self.settings = settings
        self.event_queue = event_queue
        self.instrument_name = settings.instrument_name
        self.instrument_key = settings.instrument_key
        self.candle_store = LiveCandleStore(settings.candle_interval_minutes)
        self.last_price = None
        self.last_tick_time = None
        self.tick_count = 0
        self.connection_status = "DISCONNECTED"
        self.feed_status = "Not connected"
        self.last_error = ""
        self.last_feed_keys = []
        self._ws_client = None
        self._thread = None

    def start(self, instrument_name, instrument_key):
        self.instrument_name = instrument_name.strip() or self.settings.instrument_name
        self.instrument_key = instrument_key.strip() or self.settings.instrument_key
        self.candle_store = LiveCandleStore(self.settings.candle_interval_minutes)
        self.last_price = None
        self.last_tick_time = None
        self.tick_count = 0
        self.connection_status = "CONNECTING"
        self.feed_status = "Opening browser for login..."
        self.last_error = ""
        self.last_feed_keys = []
        self.event_queue.put(("snapshot", self.snapshot()))
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        if self._ws_client and self._ws_client.ws:
            try:
                self._ws_client.ws.close()
            except Exception:
                pass
        self.connection_status = "DISCONNECTED"
        self.feed_status = "Disconnected"
        self.event_queue.put(("snapshot", self.snapshot()))

    def snapshot(self):
        return {
            "connection_status": self.connection_status,
            "feed_status": self.feed_status,
            "instrument_name": self.instrument_name,
            "instrument_key": self.instrument_key,
            "last_price": self.last_price,
            "last_tick_time": self.last_tick_time,
            "tick_count": self.tick_count,
            "last_error": self.last_error,
            "last_feed_keys": list(self.last_feed_keys),
            "candles": self.candle_store.rows(limit=20),
        }

    def _run(self):
        try:
            token = get_login_token(self.settings)
            self._push_status("CONNECTED", "Logged in. Checking initial price...")
            self._check_initial_price(token)
            self._push_status("CONNECTING", "Connecting websocket...")
            self._ws_client = UpstoxWS(
                token,
                instrument_keys=[self.instrument_key],
                feed_auth_url=self.settings.feed_auth_url,
                on_tick=self._on_tick,
                on_status=self._on_status,
            )
            self._ws_client.connect()
        except Exception as exc:
            self.last_error = str(exc)
            self.connection_status = "ERROR"
            self.feed_status = f"Connection failed: {exc}"
            self.event_queue.put(("snapshot", self.snapshot()))

    def _check_initial_price(self, token):
        try:
            quote = MarketData(token).get_ltp(self.instrument_key)
        except Exception as exc:
            self.feed_status = f"Initial price check failed: {exc}"
            self.event_queue.put(("snapshot", self.snapshot()))
            return

        price = self._find_ltp_in_quote(quote)
        if price is None:
            self.feed_status = "Initial price check returned no LTP."
        else:
            self.last_price = price
            self.feed_status = f"Initial price check ok: {price:.2f}"
        self.event_queue.put(("snapshot", self.snapshot()))

    def _find_ltp_in_quote(self, quote):
        if not isinstance(quote, dict):
            return None
        stack = [quote]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                for key, value in item.items():
                    if key in {"last_price", "ltp"} and isinstance(value, (int, float)):
                        return float(value)
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(item, list):
                stack.extend(item)
        return None

    def _on_tick(self, instrument_key, price, timestamp=None):
        if instrument_key != self.instrument_key:
            self.feed_status = f"Receiving other key: {instrument_key}"
            self.last_feed_keys = [instrument_key]
            self.event_queue.put(("snapshot", self.snapshot()))
            return

        self.tick_count += 1
        self.last_price = float(price)
        self.last_tick_time = datetime.now()
        self.connection_status = "CONNECTED"
        self.feed_status = f"Live ticks flowing ({self.tick_count} received)"
        self.candle_store.on_tick(price, timestamp)
        self.event_queue.put(("snapshot", self.snapshot()))

    def _on_status(self, event, payload):
        if event == "connected":
            self._push_status("CONNECTED", "Websocket connected")
        elif event == "subscribed":
            self._push_status("CONNECTED", f"Subscribed to {self.instrument_key}")
        elif event == "message":
            if self.tick_count == 0:
                self.feed_status = "Feed message received. Waiting for price tick..."
                self.event_queue.put(("snapshot", self.snapshot()))
        elif event == "feed":
            keys = payload.get("feed_keys", [])
            self.last_feed_keys = keys[:5]
            if payload.get("feed_count", 0) == 0:
                self.feed_status = "Feed connected, but no instrument data in last message"
            elif self.tick_count == 0:
                if keys:
                    self.feed_status = f"Feed active. Last keys: {', '.join(keys[:3])}"
                else:
                    self.feed_status = "Feed active. Waiting for decodable price..."
            self.event_queue.put(("snapshot", self.snapshot()))
        elif event == "error":
            self.last_error = payload.get("error", "")
            self.connection_status = "ERROR"
            self.feed_status = self.last_error or "Unknown websocket error"
            self.event_queue.put(("snapshot", self.snapshot()))
        elif event == "closed":
            self.connection_status = "DISCONNECTED"
            reason = payload.get("reason") or "Websocket closed"
            self.feed_status = reason
            self.event_queue.put(("snapshot", self.snapshot()))

    def _push_status(self, connection_status, feed_status):
        self.connection_status = connection_status
        self.feed_status = feed_status
        self.event_queue.put(("snapshot", self.snapshot()))


class LiveDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Algo Trader Live Market Monitor")
        self.root.geometry("1220x820")
        self.root.minsize(1080, 720)

        self.settings = get_settings()
        self.event_queue = queue.Queue()
        self.session = LiveMarketSession(self.settings, self.event_queue)

        self.instrument_name_var = tk.StringVar(value=self.settings.instrument_name)
        self.instrument_key_var = tk.StringVar(value=self.settings.instrument_key)
        self.connection_var = tk.StringVar(value="DISCONNECTED")
        self.feed_var = tk.StringVar(value="Not connected")
        self.price_var = tk.StringVar(value="n/a")
        self.tick_var = tk.StringVar(value="0")
        self.last_tick_var = tk.StringVar(value="Never")
        self.feed_keys_var = tk.StringVar(value="n/a")
        self.error_var = tk.StringVar(value="")

        self._build_layout()
        self.root.after(300, self._poll_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_layout(self):
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        left = ttk.Frame(self.root, padding=16)
        left.grid(row=0, column=0, sticky="ns")
        left.columnconfigure(0, weight=1)

        right = ttk.Frame(self.root, padding=(0, 16, 16, 16))
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(2, weight=1)

        ttk.Label(left, text="Live Market Feed", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(left, text="Instrument Name").grid(row=1, column=0, sticky="w", pady=(16, 4))
        ttk.Entry(left, textvariable=self.instrument_name_var).grid(row=2, column=0, sticky="ew")
        ttk.Label(left, text="Instrument Key").grid(row=3, column=0, sticky="w", pady=(12, 4))
        ttk.Entry(left, textvariable=self.instrument_key_var).grid(row=4, column=0, sticky="ew")
        ttk.Button(left, text="Connect Live Feed", command=self.connect_live_feed).grid(
            row=5, column=0, sticky="ew", pady=(16, 0)
        )
        ttk.Button(left, text="Disconnect", command=self.disconnect_live_feed).grid(
            row=6, column=0, sticky="ew", pady=(8, 0)
        )

        status = ttk.LabelFrame(right, text="Market Status", padding=12)
        status.grid(row=0, column=0, sticky="ew")
        for col in range(2):
            status.columnconfigure(col, weight=1)

        status_rows = [
            ("Connection", self.connection_var),
            ("Feed", self.feed_var),
            ("Current Price", self.price_var),
            ("Ticks Received", self.tick_var),
            ("Last Tick", self.last_tick_var),
            ("Feed Keys", self.feed_keys_var),
            ("Last Error", self.error_var),
        ]
        for row, (label, variable) in enumerate(status_rows):
            ttk.Label(status, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=4)
            ttk.Label(status, textvariable=variable, wraplength=720, justify="left").grid(
                row=row, column=1, sticky="w", pady=4
            )

        candles_frame = ttk.LabelFrame(right, text="Live Candles", padding=10)
        candles_frame.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        candles_frame.columnconfigure(0, weight=1)
        candles_frame.rowconfigure(0, weight=1)

        self.candle_tree = ttk.Treeview(
            candles_frame,
            columns=("time", "open", "high", "low", "close"),
            show="headings",
            height=18,
        )
        for key, heading, width in (
            ("time", "Time", 180),
            ("open", "Open", 120),
            ("high", "High", 120),
            ("low", "Low", 120),
            ("close", "Close", 120),
        ):
            self.candle_tree.heading(key, text=heading)
            self.candle_tree.column(key, width=width, anchor="center")
        self.candle_tree.grid(row=0, column=0, sticky="nsew")

        note = ttk.LabelFrame(right, text="What This Means", padding=10)
        note.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ttk.Label(
            note,
            text=(
                "CONNECTED means the websocket is open. "
                "Live ticks flowing means you are receiving real market prices for the selected instrument. "
                "If Current Price stays n/a and candles stay empty, the feed is connected but your selected "
                "instrument is not streaming usable price ticks."
            ),
            wraplength=820,
            justify="left",
        ).grid(row=0, column=0, sticky="w")

    def connect_live_feed(self):
        self.session.start(self.instrument_name_var.get(), self.instrument_key_var.get())
        self.connection_var.set("CONNECTING")
        self.feed_var.set("Starting login flow...")

    def disconnect_live_feed(self):
        self.session.stop()

    def _poll_queue(self):
        try:
            while True:
                _, snapshot = self.event_queue.get_nowait()
                self._apply_snapshot(snapshot)
        except queue.Empty:
            pass
        self.root.after(300, self._poll_queue)

    def _apply_snapshot(self, snapshot):
        self.connection_var.set(snapshot["connection_status"])
        self.feed_var.set(snapshot["feed_status"])
        self.price_var.set("n/a" if snapshot["last_price"] is None else f"{snapshot['last_price']:.2f}")
        self.tick_var.set(str(snapshot["tick_count"]))
        if snapshot["last_tick_time"] is None:
            self.last_tick_var.set("Never")
        else:
            self.last_tick_var.set(snapshot["last_tick_time"].strftime("%Y-%m-%d %H:%M:%S"))
        self.feed_keys_var.set(
            "n/a" if not snapshot["last_feed_keys"] else ", ".join(snapshot["last_feed_keys"])
        )
        self.error_var.set(snapshot["last_error"] or "None")

        self.candle_tree.delete(*self.candle_tree.get_children())
        candles = snapshot["candles"]
        for candle_time, row in candles:
            self.candle_tree.insert(
                "",
                "end",
                values=(
                    candle_time.strftime("%Y-%m-%d %H:%M"),
                    f"{row['open']:.2f}",
                    f"{row['high']:.2f}",
                    f"{row['low']:.2f}",
                    f"{row['close']:.2f}",
                ),
            )

    def _on_close(self):
        try:
            self.session.stop()
        finally:
            self.root.destroy()
