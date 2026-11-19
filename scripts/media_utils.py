"""Utilitas bersama untuk sumber media (HTTP, unduhan, seed, cache)."""
import hashlib
import json
import random
import urllib.request
from pathlib import Path

import requests


def seeded_rng(seed: str, salt: str = "") -> random.Random:
    key = f"{seed}|{salt}" if salt else str(seed)
    return random.Random(hashlib.sha256(key.encode("utf-8")).hexdigest())


def fetch_json_urllib(url: str, timeout: int = 30, headers: dict | None = None) -> dict:
    req_headers = {"Accept": "application/json", "User-Agent": "shorts-bot/1.0"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def download_file_urllib(url: str, out: Path, timeout: int = 300) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "shorts-bot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, out.open("wb") as fh:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)


def download_file_requests(url: str, out: Path, timeout: int = 300) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        with out.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)


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