"""Ambil satu video latar dari Pexels (text-only, tanpa kirim gambar ke AI)."""
import hashlib
import os
from pathlib import Path

import requests

SEARCH_URL = "https://api.pexels.com/v1/videos/search"
SHOW_URL = "https://api.pexels.com/v1/videos/videos/{}"


def _headers() -> dict[str, str]:
    return {"Authorization": os.environ["PEXELS_API_KEY"]}


def _download(link: str, out: Path) -> None:
    with requests.get(link, stream=True, timeout=180) as resp:
        resp.raise_for_status()
        with out.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)


def _best_file(video: dict) -> dict:
    files = [
        f for f in video.get("video_files", [])
        if f.get("file_type") == "video/mp4" and f.get("link")
    ]
    if not files:
        raise SystemExit(f"Video Pexels {video.get('id')} tidak punya file mp4.")
    files.sort(
        key=lambda f: (
            -int(f.get("height") or 0),
            -int(f.get("width") or 0),
            0 if f.get("quality") == "hd" else 1,
        )
    )
    return files[0]


def pick_background(theme: dict, day: str, out: Path) -> dict:
    """Pakai daftar ID bila ada; kalau tidak, cari berdasarkan query tema."""
    ids = theme.get("pexels_video_ids") or []
    if ids:
        videos = []
        for vid in ids:
            r = requests.get(SHOW_URL.format(vid), headers=_headers(), timeout=30)
            r.raise_for_status()
            videos.append(r.json())
        portrait = [
            v for v in videos
            if int(v.get("height") or 0) > int(v.get("width") or 0)
        ]
        if portrait:
            videos = portrait
        else:
            print("[warn] tidak ada video portrait di pool; pakai semua (tetap di-crop 9:16).")
    else:
        r = requests.get(
            SEARCH_URL,
            headers=_headers(),
            params={
                "query": theme["pexels_query"],
                "orientation": "portrait",
                "size": "medium",
                "per_page": 6,
                "locale": "id-ID",
            },
            timeout=30,
        )
        r.raise_for_status()
        videos = r.json().get("videos", [])

    if not videos:
        raise SystemExit("Pexels tidak mengembalikan video untuk tema ini.")

    chosen = sorted(
        videos,
        key=lambda v: hashlib.sha256(f"{v['id']}|{day}".encode("utf-8")).hexdigest(),
    )[0]
    _download(_best_file(chosen)["link"], out)

    return {
        "id": chosen["id"],
        "url": chosen.get("url", ""),
        "photographer": (chosen.get("user") or {}).get("name", ""),
        "pexels_duration": chosen.get("duration"),
    }
