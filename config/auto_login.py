import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

from config.settings import get_settings, require_upstox_credentials


class OAuthHandler(BaseHTTPRequestHandler):
    auth_code = None

    def do_GET(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        OAuthHandler.auth_code = query.get("code", [None])[0]

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Login successful. You can close this window.")

    def log_message(self, format, *args):
        return


def get_login_token(settings=None):
    settings = settings or get_settings()
    require_upstox_credentials(settings)

    encoded_redirect = urllib.parse.quote(settings.redirect_uri, safe="")
    auth_url = (
        "https://api.upstox.com/v2/login/authorization/dialog"
        f"?response_type=code&client_id={settings.api_key}"
        f"&redirect_uri={encoded_redirect}"
    )

    print("Opening Upstox login page...")
    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", settings.auth_port), OAuthHandler)
    server.handle_request()

    if not OAuthHandler.auth_code:
        raise RuntimeError("Upstox login did not return an authorization code.")

    response = requests.post(
        "https://api.upstox.com/v2/login/authorization/token",
        data={
            "code": OAuthHandler.auth_code,
            "client_id": settings.api_key,
            "client_secret": settings.api_secret,
            "redirect_uri": settings.redirect_uri,
            "grant_type": "authorization_code",
        },
        headers={
            "accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout=20,
    )
    response.raise_for_status()
    token_data = response.json()
    token = token_data.get("access_token")
    if not token:
        raise RuntimeError("Upstox token response did not include access_token.")

    print("Upstox access token acquired.")
    return token
