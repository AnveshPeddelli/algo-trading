import json

import requests
import websocket

import market_data_pb2


class UpstoxWS:
    def __init__(self, access_token, instrument_keys, feed_auth_url, on_tick=None, on_status=None):
        self.access_token = access_token
        self.instrument_keys = list(instrument_keys)
        self.feed_auth_url = feed_auth_url
        self.on_tick_callback = on_tick
        self.on_status_callback = on_status
        self.ws = None

    def get_ws_url(self):
        response = requests.get(
            self.feed_auth_url,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "*/*",
            },
            allow_redirects=False,
            timeout=20,
        )

        if response.status_code != 302:
            raise RuntimeError(f"WS URL fetch failed: {response.status_code} {response.text}")

        ws_url = response.headers.get("Location")
        if not ws_url:
            raise RuntimeError("No WS URL found in Upstox redirect response")
        return ws_url

    def on_open(self, ws):
        print("WebSocket connected")
        self._emit_status("connected", {"instrument_keys": self.instrument_keys})
        sub_msg = {
            "guid": "paper-trader-1",
            "method": "sub",
            "data": {
                "mode": "full",
                "instrumentKeys": self.instrument_keys,
            },
        }
        ws.send(json.dumps(sub_msg).encode("utf-8"), opcode=websocket.ABNF.OPCODE_BINARY)
        print(f"Subscribed to {', '.join(self.instrument_keys)}")
        self._emit_status("subscribed", {"instrument_keys": self.instrument_keys})

    def on_message(self, ws, message):
        self._emit_status(
            "message",
            {
                "is_binary": isinstance(message, bytes),
                "size": len(message) if hasattr(message, "__len__") else 0,
            },
        )
        if not isinstance(message, bytes):
            print("WebSocket text message:", message)
            self._emit_status("text_message", {"message": message})
            return

        feed = market_data_pb2.FeedResponse()
        feed.ParseFromString(message)
        self._emit_status("feed", {"feed_keys": list(feed.feeds.keys()), "feed_count": len(feed.feeds)})
        for instrument_key, instrument_feed in feed.feeds.items():
            price = self._extract_ltp(instrument_feed)
            if price is None:
                self._emit_status("feed_without_ltp", {"instrument_key": instrument_key})
                continue
            timestamp = self._extract_timestamp(instrument_feed) or feed.currentTs or None
            if self.on_tick_callback:
                self.on_tick_callback(instrument_key, price, timestamp)

    def on_error(self, ws, error):
        print("WebSocket error:", error)
        self._emit_status("error", {"error": str(error)})

    def on_close(self, ws, code, reason):
        print(f"WebSocket closed code={code} reason={reason}")
        self._emit_status("closed", {"code": code, "reason": reason})

    def connect(self):
        self.ws = websocket.WebSocketApp(
            self.get_ws_url(),
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )
        self.ws.run_forever()

    def _emit_status(self, event, payload=None):
        if self.on_status_callback:
            self.on_status_callback(event, payload or {})

    @staticmethod
    def _extract_ltp(feed):
        if feed.HasField("ltpc"):
            return feed.ltpc.ltp
        if feed.HasField("oc"):
            return feed.oc.ltpc.ltp
        if feed.HasField("ff"):
            if feed.ff.HasField("indexFF"):
                return feed.ff.indexFF.ltpc.ltp
            if feed.ff.HasField("marketFF"):
                return feed.ff.marketFF.ltpc.ltp
        return None

    @staticmethod
    def _extract_timestamp(feed):
        if feed.HasField("ltpc"):
            return feed.ltpc.ltt
        if feed.HasField("oc"):
            return feed.oc.ltpc.ltt
        if feed.HasField("ff"):
            if feed.ff.HasField("indexFF"):
                return feed.ff.indexFF.ltpc.ltt
            if feed.ff.HasField("marketFF"):
                return feed.ff.marketFF.ltpc.ltt
        return None
