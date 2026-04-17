from config.auto_login import get_login_token
from config.settings import get_settings
from data.market_data import MarketData


def main():
    settings = get_settings()
    token = get_login_token(settings)
    quote = MarketData(token).get_ltp(settings.instrument_key)
    print(quote)


if __name__ == "__main__":
    main()
