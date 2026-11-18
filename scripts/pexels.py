"""Ambil satu video latar Pexels lewat URL MP4 langsung (tanpa API key)."""
import hashlib
from pathlib import Path

import requests


def _download(link: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(link, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        with out.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)


def pick_background(theme: dict, seed: str, out: Path) -> dict:
    """Pilih satu background dari pool URL langsung berdasarkan seed (acak per run)."""
    pool = theme.get("pexels_backgrounds") or []
    if not pool:
        raise SystemExit(
            "Tidak ada 'pexels_backgrounds' di config/themes.json. "
            "Tambahkan entri dengan field id, url, photographer, dan file_url."
        )

    valid = [b for b in pool if b.get("file_url")]
    if not valid:
        raise SystemExit(
            "Semua entri 'pexels_backgrounds' belum punya 'file_url' (URL MP4 langsung)."
        )

    chosen = sorted(
        valid,
        key=lambda b: hashlib.sha256(
            f"{b.get('id') or b['file_url']}|{seed}".encode("utf-8")
        ).hexdigest(),
    )[0]

    link = chosen["file_url"]
    _download(link, out)

    return {
        "id": chosen.get("id"),
        "url": chosen.get("url") or chosen.get("page_url") or "",
        "photographer": chosen.get("photographer") or "",
        "description": chosen.get("description") or theme.get("pexels_query", ""),
        "file_url": link,
    }
