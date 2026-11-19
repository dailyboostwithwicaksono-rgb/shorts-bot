"""Publisher YouTube: formatter metadata + upload resumable (perilaku paritas)."""
import os
from dataclasses import dataclass
from pathlib import Path

import requests

from content import CanonicalContent
from gauth import get_access_token

CHUNK = 8 * 1024 * 1024


@dataclass
class PublishResult:
    target: str
    status: str  # success|skipped|failed|dry_run
    id: str | None = None
    url: str | None = None
    message: str | None = None


def format_youtube_metadata(content: CanonicalContent) -> dict:
    hashtags = content.hashtags
    return {
        "snippet": {
            "title": content.title[:100],
            "description": content.description[:5000],
            "tags": [h for h in hashtags[:10] if h],
            "categoryId": "24",
            "defaultLanguage": "id",
            "defaultAudioLanguage": "id",
        },
        "status": {
            "privacyStatus": content.privacy,
            "selfDeclaredMadeForKids": False,
            "embeddable": True,
        },
    }


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


def publish_youtube(content: CanonicalContent, dry_run: bool = False) -> PublishResult:
    metadata = format_youtube_metadata(content)
    if dry_run:
        return PublishResult(target="youtube", status="dry_run", message="dry-run: metadata disiapkan, upload dilewati")
    token = get_access_token()
    video_id = resumable_upload(token, content.video_path, metadata)
    url = f"https://www.youtube.com/shorts/{video_id}"
    print(f"[ok] YouTube video ID: {video_id}")
    print(f"[ok] URL: {url}")
    return PublishResult(target="youtube", status="success", id=video_id, url=url)