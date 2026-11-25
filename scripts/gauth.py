"""Helper OAuth: tukar refresh token menjadi access token."""
import os

import requests


def get_access_token(refresh_env: str | None = None) -> str:
    """Tukar refresh token menjadi access token.

    refresh_env: nama env var yang berisi refresh token. Default: YT_REFRESH_TOKEN.
    Bisa dioverride global via env YT_REFRESH_TOKEN_ENV (mis. YT_REFRESH_TOKEN_CH2).
    """
    env_name = (refresh_env or os.getenv("YT_REFRESH_TOKEN_ENV") or "YT_REFRESH_TOKEN").strip() or "YT_REFRESH_TOKEN"
    client_id = os.environ.get("YT_CLIENT_ID")
    client_secret = os.environ.get("YT_CLIENT_SECRET")
    refresh_token = os.environ.get(env_name)
    if not client_id or not client_secret:
        raise RuntimeError("YT_CLIENT_ID/YT_CLIENT_SECRET belum diset di environment.")
    if not refresh_token:
        raise RuntimeError(f"Refresh token tidak ditemukan di env '{env_name}'.")

    r = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]
