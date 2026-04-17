import threading
import time
from datetime import datetime

from config.auto_login import get_login_token
from config.settings import get_settings
from data.candle_builder import CandleBuilder
from data.market_data import MarketData
from data.upstox_ws import UpstoxWS
from execution.order_manager import PaperOrderManager
from execution.paper_engine import PaperTrader
from risk.risk_manager import RiskConfig, RiskManager
from strategy.nifty_strategy import NiftyEmaCrossoverStrategy


class PaperTradingApp:
    def __init__(self, settings):
        self.settings = settings
        self.candles = CandleBuilder(settings.candle_interval_minutes)
        self.trader = PaperTrader(settings.starting_capital)
        self.risk = RiskManager(
            RiskConfig(
                risk_per_trade=settings.risk_per_trade,
                max_quantity=settings.max_quantity,
                default_stop_points=settings.default_stop_points,
            )
        )
        self.strategy = NiftyEmaCrossoverStrategy(stop_points=settings.default_stop_points)
        self.orders = PaperOrderManager(self.trader, self.risk, settings.instrument_key)
        self._last_evaluated_candle_time = None
        self._last_tick_time = None
        self._last_price = None
        self._tick_count = 0
        self._ws_connected = False
        self._ws_message_count = 0
        self._ws_binary_message_count = 0
        self._ws_text_message_count = 0
        self._ws_feed_count = 0
        self._empty_feed_count = 0
        self._last_ws_event = "not started"
        self._last_ws_message_time = None
        self._subscribed_at = None
        self._last_feed_keys = []
        self._unmatched_tick_count = 0
        self._heartbeat_started = False

    def on_tick(self, instrument_key, price, timestamp=None):
        if instrument_key != self.settings.instrument_key:
            self._unmatched_tick_count += 1
            return

        self._tick_count += 1
        self._last_tick_time = datetime.now()
        self._last_price = price

        self.candles.on_tick(price, timestamp)
        self.trader.check_stop(price)

        candle_df = self.candles.get_dataframe()
        if len(candle_df) < 2:
            return

        completed_candles = candle_df.iloc[:-1]
        latest_completed_time = completed_candles.index[-1]
        if latest_completed_time == self._last_evaluated_candle_time:
            return

        self._last_evaluated_candle_time = latest_completed_time
        self.print_completed_candle(latest_completed_time, completed_candles.iloc[-1])
        signal = self.strategy.generate_signal(completed_candles, self.trader.position)
        fill = self.orders.handle_signal(signal, price)

        if fill:
            equity = self.trader.mark_to_market(price)
            print(f"Paper equity={equity:.2f} realized_pnl={self.trader.realized_pnl:.2f}")

    def print_completed_candle(self, candle_time, candle):
        print(f"\n[{datetime.now():%H:%M:%S}] Candle Closed")
        print(f"  Time         : {candle_time:%Y-%m-%d %H:%M}")
        print(f"  Instrument   : {self.settings.instrument_name}")
        print(f"  Open         : {candle['open']:.2f}")
        print(f"  High         : {candle['high']:.2f}")
        print(f"  Low          : {candle['low']:.2f}")
        print(f"  Close        : {candle['close']:.2f}")

    def run(self):
        token = get_login_token(self.settings)
        self.check_initial_price(token)
        websocket_client = UpstoxWS(
            token,
            instrument_keys=[self.settings.instrument_key],
            feed_auth_url=self.settings.feed_auth_url,
            on_tick=self.on_tick,
            on_status=self.on_ws_status,
        )
        websocket_client.connect()

    def check_initial_price(self, token):
        try:
            quote = MarketData(token).get_ltp(self.settings.instrument_key)
        except Exception as exc:
            print(f"Initial price check failed for {self.settings.instrument_key}: {exc}")
            return

        price = self._find_ltp_in_quote(quote)
        if price is None:
            print(f"Initial price check returned no LTP for {self.settings.instrument_key}: {quote}")
            return

        print(f"Initial price check: {self.settings.instrument_name} = {price:.2f}")

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

    def on_ws_status(self, event, payload):
        self._last_ws_event = event
        if event == "connected":
            self._ws_connected = True
        elif event == "subscribed":
            self._subscribed_at = datetime.now()
            self.start_heartbeat()
        elif event == "closed":
            self._ws_connected = False
        elif event == "message":
            self._ws_message_count += 1
            self._last_ws_message_time = datetime.now()
            if payload.get("is_binary"):
                self._ws_binary_message_count += 1
            else:
                self._ws_text_message_count += 1
        elif event == "feed":
            feed_count = payload.get("feed_count", 0)
            self._ws_feed_count += feed_count
            if feed_count == 0:
                self._empty_feed_count += 1
            self._last_feed_keys = payload.get("feed_keys", [])[:5]

    def start_heartbeat(self):
        if self._heartbeat_started:
            return
        self._heartbeat_started = True
        thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        thread.start()

    def _heartbeat_loop(self):
        while True:
            now = datetime.now()
            candle_count = len(self.candles.get_dataframe())
            position = "FLAT" if self.trader.position is None else f"LONG {self.trader.position.quantity}"
            equity = self.trader.mark_to_market(self._last_price)
            price = "n/a" if self._last_price is None else f"{self._last_price:.2f}"
            connection = "CONNECTED" if self._ws_connected else "WAITING"
            market_data = self._market_data_status(now)
            candle_status = self._candle_status(candle_count)
            strategy_status = "READY" if candle_count >= self.strategy.min_candles else (
                f"WARMING UP ({candle_count}/{self.strategy.min_candles} candles)"
            )

            print(f"\n[{now:%H:%M:%S}] Paper Trading Status")
            print(f"  Connection   : {connection}")
            print(f"  Instrument   : {self.settings.instrument_name} ({self.settings.instrument_key})")
            print(f"  Market Data  : {market_data}")
            print(f"  Last Price   : {price}")
            print(f"  Candles      : {candle_status}")
            print(f"  Strategy     : {strategy_status}")
            print(f"  Position     : {position}")
            print(f"  Equity       : {equity:.2f}")
            time.sleep(60)

    def _market_data_status(self, now):
        if self._tick_count > 0 and self._last_tick_time is not None:
            age = (now - self._last_tick_time).total_seconds()
            if age <= 5:
                return f"LIVE - receiving ticks ({self._tick_count} total, last {age:.0f}s ago)"
            return f"STALE - last tick {age:.0f}s ago"

        if self._ws_message_count == 0:
            wait_time = self._wait_time_since_subscription(now)
            return f"WAITING - subscribed, no feed messages yet{wait_time}"

        if self._ws_feed_count == 0:
            wait_seconds = self._seconds_since_subscription(now)
            if wait_seconds is not None and wait_seconds < 15:
                return "WAITING - market status received, waiting for first price snapshot"
            return f"NOT LIVE - no instruments received after subscription ({self._empty_feed_count} empty messages)"

        if self._unmatched_tick_count > 0:
            keys = "unknown" if not self._last_feed_keys else ", ".join(self._last_feed_keys)
            return f"WRONG INSTRUMENT - feed key is {keys}"

        return "NO PRICE YET - feed received, but no LTP decoded"

    def _wait_time_since_subscription(self, now):
        if self._subscribed_at is None:
            return ""
        return f" ({self._seconds_since_subscription(now):.0f}s)"

    def _seconds_since_subscription(self, now):
        if self._subscribed_at is None:
            return None
        return (now - self._subscribed_at).total_seconds()

    def _candle_status(self, candle_count):
        if candle_count == 0:
            return "NOT STARTED - waiting for first tick"
        if candle_count == 1:
            return f"FORMING - 1 candle in progress ({self.settings.candle_interval_minutes} min)"
        return f"{candle_count} candles built, latest candle forming"


if __name__ == "__main__":
    PaperTradingApp(get_settings()).run()
