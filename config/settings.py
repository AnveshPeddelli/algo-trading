import os
from dataclasses import dataclass


def _load_local_env(path=".env"):
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _float_env(name, default):
    value = os.getenv(name)
    return default if value in (None, "") else float(value)


def _int_env(name, default):
    value = os.getenv(name)
    return default if value in (None, "") else int(value)


@dataclass(frozen=True)
class Settings:
    api_key: str
    api_secret: str
    redirect_uri: str
    auth_port: int
    feed_auth_url: str
    instrument_key: str
    instrument_name: str
    candle_interval_minutes: int
    starting_capital: float
    risk_per_trade: float
    default_stop_points: float
    max_quantity: int


def get_settings():
    _load_local_env()

    return Settings(
        api_key=os.getenv("UPSTOX_API_KEY", ""),
        api_secret=os.getenv("UPSTOX_API_SECRET", ""),
        redirect_uri=os.getenv("UPSTOX_REDIRECT_URI", "http://localhost:8080"),
        auth_port=_int_env("UPSTOX_AUTH_PORT", 8080),
        feed_auth_url=os.getenv(
            "UPSTOX_FEED_AUTH_URL",
            "https://api.upstox.com/v3/feed/market-data-feed",
        ),
        instrument_key=os.getenv("PAPER_INSTRUMENT_KEY", "NSE_INDEX|Nifty 50"),
        instrument_name=os.getenv("PAPER_INSTRUMENT_NAME", "Nifty 50"),
        candle_interval_minutes=_int_env("PAPER_CANDLE_INTERVAL_MINUTES", 1),
        starting_capital=_float_env("PAPER_STARTING_CAPITAL", 100000.0),
        risk_per_trade=_float_env("PAPER_RISK_PER_TRADE", 0.01),
        default_stop_points=_float_env("PAPER_DEFAULT_STOP_POINTS", 25.0),
        max_quantity=_int_env("PAPER_MAX_QUANTITY", 500),
    )


def require_upstox_credentials(settings):
    missing = []
    if not settings.api_key:
        missing.append("UPSTOX_API_KEY")
    if not settings.api_secret:
        missing.append("UPSTOX_API_SECRET")
    if missing:
        raise RuntimeError(
            "Missing Upstox credentials. Set these environment variables or add "
            f"them to a local .env file: {', '.join(missing)}"
        )
