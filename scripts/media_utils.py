"""Utilitas bersama untuk sumber media (HTTP, unduhan, seed, cache)."""
import hashlib
import json
import random
import time
import urllib.error
import urllib.request
from pathlib import Path

import requests


def seeded_rng(seed: str, salt: str = "") -> random.Random:
    key = f"{seed}|{salt}" if salt else str(seed)
    return random.Random(hashlib.sha256(key.encode("utf-8")).hexdigest())


def _should_retry_requests(exc: Exception) -> bool:
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, requests.HTTPError):
        status = getattr(exc.response, "status_code", None)
        return status == 429 or (status is not None and status >= 500)
    return False


def _should_retry_urllib(exc: Exception) -> bool:
    if isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError)):
        return True
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or exc.code >= 500
    return False


def fetch_json_urllib(url: str, timeout: int = 30, headers: dict | None = None, attempts: int = 3) -> dict:
    req_headers = {"Accept": "application/json", "User-Agent": "shorts-bot/1.0"}
    if headers:
        req_headers.update(headers)
    last_exc = None
    for i in range(max(1, attempts)):
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if i >= attempts - 1 or not _should_retry_urllib(exc):
                raise
            time.sleep(min(0.8 * (2 ** i), 4.0))
    raise last_exc  # pragma: no cover


def download_file_urllib(url: str, out: Path, timeout: int = 300, attempts: int = 3) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    last_exc = None
    for i in range(max(1, attempts)):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "shorts-bot/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp, out.open("wb") as fh:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if i >= attempts - 1 or not _should_retry_urllib(exc):
                raise
            time.sleep(min(0.8 * (2 ** i), 4.0))
    raise last_exc  # pragma: no cover


def download_file_requests(url: str, out: Path, timeout: int = 300, attempts: int = 3) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    last_exc = None
    for i in range(max(1, attempts)):
        try:
            with requests.get(url, stream=True, timeout=timeout) as resp:
                resp.raise_for_status()
                with out.open("wb") as fh:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            fh.write(chunk)
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if i >= attempts - 1 or not _should_retry_requests(exc):
                raise
            time.sleep(min(0.8 * (2 ** i), 4.0))
    raise last_exc  # pragma: no cover


def load_cache_items(cache_path: Path | None) -> list[dict]:
    if not cache_path or not cache_path.exists():
        return []
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("items") or data.get("cache") or []
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_cache_items(cache_path: Path | None, items: list[dict], limit: int = 200) -> None:
    if not cache_path:
        return
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    # keep unique by id, most recent last, cap size
    seen = {}
    ordered = []
    for it in items:
        key = str(it.get("id") or it.get("pageURL") or it.get("file_url"))
        if key in seen:
            ordered[seen[key]] = it
        else:
            seen[key] = len(ordered)
            ordered.append(it)
    if len(ordered) > limit:
        ordered = ordered[-limit:]
    cache_path.write_text(json.dumps({"items": ordered}, ensure_ascii=False, indent=2), encoding="utf-8")