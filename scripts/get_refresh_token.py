"""Ambil YouTube OAuth refresh token SEKALI di laptop, lalu simpan ke GitHub Secret.

Jalankan:
    copy .env.example .env
    isi YT_CLIENT_ID dan YT_CLIENT_SECRET
    python scripts/get_refresh_token.py

Browser akan terbuka; setelah izin diberikan, token muncul di terminal.
"""
import http.server
import os
import secrets
import socketserver
import subprocess
import urllib.parse
import webbrowser
from pathlib import Path

import requests

PORT = 8080
REDIRECT_URI = f"http://localhost:{PORT}"
SCOPE = "https://www.googleapis.com/auth/youtube.upload"


def _read_env() -> dict[str, str]:
    env: dict[str, str] = {}
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _save_env_value(key: str, value: str) -> None:
    """Simpan/memperbarui satu key di .env tanpa mencetak nilai."""
    path = Path(__file__).resolve().parent.parent / ".env"
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    prefix = f"{key}="
    kept = [line for line in lines if not line.strip().startswith(prefix)]
    kept.append(f"{prefix}{value}")
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")


def _copy_to_clipboard(value: str) -> None:
    """Salin ke clipboard Windows via perintah clip (stdin, bukan argumen)."""
    try:
        subprocess.run(["clip"], input=value, text=True, check=True)
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    local = _read_env()
    client_id = os.getenv("YT_CLIENT_ID") or local.get("YT_CLIENT_ID")
    client_secret = os.getenv("YT_CLIENT_SECRET") or local.get("YT_CLIENT_SECRET")
    if not client_id or not client_secret:
        client_id = input("YT_CLIENT_ID: ").strip()
        client_secret = input("YT_CLIENT_SECRET: ").strip()

    state = secrets.token_urlsafe(24)
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if query.get("state", [None])[0] != state or "code" not in query:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State tidak cocok atau code tidak ada.")
                return
            self.server.auth_code = query["code"][0]  # type: ignore[attr-defined]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                b"Berhasil! Tutup tab ini dan lihat refresh token di terminal."
            )

        def log_message(self, *_args) -> None:
            pass

    print("\nBuka URL ini di browser:\n")
    print(auth_url, "\n")
    webbrowser.open(auth_url)

    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as server:
        server.handle_request()
        code = getattr(server, "auth_code", None)

    if not code:
        raise SystemExit("Tidak mendapat authorization code.")

    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    response.raise_for_status()
    tokens = response.json()

    refresh_token = tokens.get("refresh_token", "")
    if refresh_token:
        _save_env_value("YT_REFRESH_TOKEN", refresh_token)
        _copy_to_clipboard(refresh_token)
        print(
            f"\n[ok] Refresh token tersimpan di .env dan clipboard "
            f"(panjang {len(refresh_token)} karakter, tidak ditampilkan)."
        )
        print("Tempel sebagai GitHub Secret YT_REFRESH_TOKEN.\n")
    else:
        print("\n[warn] Google tidak mengembalikan refresh_token. Periksa consent screen.\n")
    print(
        "Catatan: status OAuth 'Testing' membuat token ini kedaluwarsa dalam 7 hari. "
        "Ulangi script ini bila upload gagal dengan error invalid_grant."
    )


if __name__ == "__main__":
    main()
