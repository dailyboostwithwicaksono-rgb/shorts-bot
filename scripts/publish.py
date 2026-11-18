#!/usr/bin/env python3
"""Upload video ke YouTube lewat refresh token (resumable upload)."""
import json
from pathlib import Path

import requests

from gauth import get_access_token

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "out" / "manifest.json"
CHUNK = 8 * 1024 * 1024


def resumable_upload(token: str, video: Path, metadata: dict) -> str:
    size = video.stat().st_size
    init = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos"
        "?uploadType=resumable&part=snippet,status",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(size),
        },
        json=metadata,
        timeout=60,
    )
    init.raise_for_status()
    session_url = init.headers["Location"]
    data = video.read_bytes()

    start = 0
    while start < size:
        end = min(start + CHUNK, size) - 1
        part = data[start : end + 1]
        r = requests.put(
            session_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "video/mp4",
                "Content-Length": str(len(part)),
                "Content-Range": f"bytes {start}-{end}/{size}",
            },
            data=part,
            timeout=300,
        )
        if r.status_code in (200, 201):
            return r.json()["id"]
        if r.status_code == 308:
            rng = r.headers.get("Range", "")
            try:
                next_start = int(rng.split("=", 1)[1].split("-", 1)[1]) + 1
            except (IndexError, ValueError):
                next_start = end + 1
            if next_start <= start:
                raise SystemExit(f"Upload tidak maju: {rng}")
            start = next_start
            continue
        raise SystemExit(f"Gagal upload {r.status_code}: {r.text[:600]}")

    raise SystemExit("Upload selesai tanpa response video ID.")


def main() -> None:
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    video = ROOT / "out" / m["file"]
    hashtags = m["hashtags"]
    description = m.get("description") or f"{m['caption']}\n\n{' '.join(hashtags)}"
    metadata = {
        "snippet": {
            "title": m["title"][:100],
            "description": description[:5000],
            "tags": [h for h in hashtags[:10] if h],
            "categoryId": "24",
            "defaultLanguage": "id",
            "defaultAudioLanguage": "id",
        },
        "status": {
            "privacyStatus": m.get("privacy", "public"),
            "selfDeclaredMadeForKids": False,
            "embeddable": True,
        },
    }
    token = get_access_token()
    video_id = resumable_upload(token, video, metadata)
    print(f"[ok] YouTube video ID: {video_id}")
    print(f"[ok] URL: https://www.youtube.com/shorts/{video_id}")


if __name__ == "__main__":
    main()
