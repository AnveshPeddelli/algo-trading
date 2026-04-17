import requests


class MarketData:
    BASE_URL = "https://api.upstox.com/v2"

    def __init__(self, access_token):
        self.access_token = access_token

    def get_ltp(self, instrument_key):
        response = requests.get(
            f"{self.BASE_URL}/market-quote/ltp",
            params={"instrument_key": instrument_key},
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
            },
            timeout=20,
        )
        response.raise_for_status()
        return response.json()
