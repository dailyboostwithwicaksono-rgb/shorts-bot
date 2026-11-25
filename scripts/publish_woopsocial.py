"""Publisher WoopSocial: upload video + publish langsung ke Instagram Reels/TikTok.

Dipanggil oleh `scripts/publish.py` lewat target `woopsocial`. Perilakunya
sengaja mengikuti `publish_youtube.py`: sekali jalan, langsung publish
(`PUBLISH_NOW`), tanpa penjadwalan. Metadata diambil dari artefak kanonik
`out/manifest.json` (sudah dihasilkan AI oleh workflow utama).

Env:
- WOOPSOCIAL_API_KEY   : wajib (kunci API WoopSocial).
- WOOPSOCIAL_PLATFORMS : opsional, default `instagram,tiktok`.
- WOOPSOCIAL_PROJECT_ID: opsional, default proyek akun pertama yang terhubung.
- WOOPSOCIAL_IG_ACCOUNT_ID / WOOPSOCIAL_TIKTOK_ACCOUNT_ID: opsional.
- WOOPSOCIAL_LINK      : opsional, default `-`.
- WOOPSOCIAL_AI_CONTENT: opsional, default `1` (flag AI-generated di IG).

Dry-run: cek kredensial/akun + `posts_validate`. Bila library media kosong,
video di-upload hanya sebagai bahan validasi. Tidak pernah membuat post.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import requests

from common import WORK, now_utc_iso
from content import CanonicalContent
from publish_youtube import PublishResult

BASE_URL = "https://api.woopsocial.com/v1"
CAPTION_LIMIT = 2200
PLATFORM_ALIASES = {
    "ig": "INSTAGRAM",
    "instagram": "INSTAGRAM",
    "reels": "INSTAGRAM",
    "tt": "TIKTOK",
    "tiktok": "TIKTOK",
}


def _env_flag(name: str, default: bool = True) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _requested_platforms() -> list[str]:
    raw = (os.getenv("WOOPSOCIAL_PLATFORMS") or "instagram,tiktok").strip()
    result: list[str] = []
    for part in raw.replace(";", ",").split(","):
        key = part.strip().lower()
        platform = PLATFORM_ALIASES.get(key)
        if platform and platform not in result:
            result.append(platform)
    return result or ["INSTAGRAM", "TIKTOK"]


def _clean_hashtags(content: CanonicalContent) -> list[str]:
    tags: list[str] = []
    for item in content.hashtags:
        tag = re.sub(r"[^a-z0-9]", "", str(item).lstrip("#").lower())
        if tag and tag not in tags:
            tags.append(tag)
        if len(tags) == 5:
            break
    if not tags:
        for tag in re.findall(r"#(\w+)", content.description):
            tag = re.sub(r"[^a-z0-9]", "", tag.lower())
            if tag and tag not in tags:
                tags.append(tag)
            if len(tags) == 5:
                break
    return tags


def format_caption(content: CanonicalContent) -> str:
    """Judul + deskripsi + link + hashtag, dipotong aman di batas TikTok/IG."""
    title = (content.title or "").strip()[:55] or "Video Shorts"
    description = re.sub(r"#\w+", " ", content.description or "")
    description = re.sub(r"[ \t]{2,}", " ", description).strip()
    link = (os.getenv("WOOPSOCIAL_LINK") or "-").strip() or "-"
    tags = " ".join("#" + tag for tag in _clean_hashtags(content))
    footer = f"\n\nLink: {link}" + (f"\n{tags}" if tags else "")

    prefix = f"{title}\n\n"
    room = CAPTION_LIMIT - len(prefix) - len(footer)
    if room < 40:
        return (prefix + footer)[:CAPTION_LIMIT]
    if len(description) > room:
        description = description[:room].rstrip() + "..."
    return (prefix + description + footer).strip()


class WoopSocial:
    def __init__(self, api_key: str) -> None:
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict | None = None,
        files: dict | None = None,
        params: dict | None = None,
        timeout: int = 180,
    ) -> dict:
        response = requests.request(
            method,
            BASE_URL + path,
            headers=self.headers,
            json=payload if files is None else None,
            files=files,
            params=params,
            timeout=timeout,
        )
        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text[:800]}
        if not response.ok:
            raise RuntimeError(
                f"WoopSocial {method} {path} → HTTP {response.status_code}: "
                f"{json.dumps(body, ensure_ascii=False)[:800]}"
            )
        return body


def _select_accounts(client: WoopSocial, platforms: list[str]) -> tuple[list[dict], str]:
    accounts = client.request("GET", "/social-accounts")
    if isinstance(accounts, dict):
        accounts = accounts.get("socialAccounts") or accounts.get("items") or []
    selected: list[dict] = []
    for platform in platforms:
        env_name = (
            "WOOPSOCIAL_IG_ACCOUNT_ID"
            if platform == "INSTAGRAM"
            else "WOOPSOCIAL_TIKTOK_ACCOUNT_ID"
        )
        forced_id = (os.getenv(env_name) or "").strip()
        matches = [
            item
            for item in accounts
            if item.get("platform") == platform
            and item.get("status") == "CONNECTED"
            and (not forced_id or str(item.get("id")) == forced_id)
        ]
        if not matches:
            raise RuntimeError(
                f"tidak ada akun {platform} yang CONNECTED di WoopSocial"
                + (f" (id {forced_id} tidak cocok)" if forced_id else "")
            )
        selected.append(matches[0])

    project_id = (os.getenv("WOOPSOCIAL_PROJECT_ID") or "").strip()
    if not project_id:
        project_id = str(selected[0].get("projectId") or "")
    if not project_id:
        raise RuntimeError("project id WoopSocial tidak ditemukan")
    if any(str(item.get("projectId")) != project_id for item in selected):
        raise RuntimeError("akun Instagram/TikTok tidak berada dalam project yang sama")
    return selected, project_id


def _social_targets(accounts: list[dict]) -> list[dict]:
    targets: list[dict] = []
    for account in accounts:
        platform = account["platform"]
        base = {"platform": platform, "socialAccountId": str(account["id"])}
        if platform == "INSTAGRAM":
            base.update(
                {
                    "postType": "REEL",
                    "isAiGeneratedContent": _env_flag("WOOPSOCIAL_AI_CONTENT"),
                }
            )
        else:
            base.update(
                {
                    "postType": "VIDEO",
                    "postMode": "DIRECT_POST",
                    "privacyLevel": "PUBLIC_TO_EVERYONE",
                    "allowComment": True,
                    "allowDuet": True,
                    "allowStitch": True,
                    "isYourBrand": False,
                    "isBrandedContent": False,
                    "autoAddMusic": False,
                }
            )
        targets.append(base)
    return targets


def build_payload(media_id: str, accounts: list[dict], caption: str) -> dict:
    return {
        "content": [
            {
                "text": caption,
                "media": [{"type": "MEDIA_LIBRARY", "mediaId": media_id}],
            }
        ],
        "schedule": {"type": "PUBLISH_NOW"},
        "socialAccounts": _social_targets(accounts),
    }


def _find_test_media(client: WoopSocial) -> str | None:
    response = client.request("GET", "/media")
    items = response.get("media", []) if isinstance(response, dict) else response
    for item in items or []:
        if item.get("mediaType") == "VIDEO" and item.get("id"):
            return str(item["id"])
    return None


def _upload_media(client: WoopSocial, project_id: str, video: Path) -> str:
    print(f"[info] Upload video ke WoopSocial: {video.name}")
    with video.open("rb") as handle:
        media = client.request(
            "POST",
            "/media",
            params={"projectId": project_id},
            files={"file": (video.name, handle, "video/mp4")},
            timeout=600,
        )
    media_id = str(media.get("mediaId") or media.get("id") or "")
    if not media_id:
        raise RuntimeError(f"respons upload media tanpa id: {json.dumps(media, ensure_ascii=False)[:500]}")
    return media_id


def _write_log(name: str, data: dict) -> None:
    directory = WORK / "woopsocial"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def publish_woopsocial(content: CanonicalContent, dry_run: bool = False) -> PublishResult:
    api_key = (os.getenv("WOOPSOCIAL_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("WOOPSOCIAL_API_KEY belum diisi")

    video = Path(content.video_path)
    if not video.is_file():
        raise RuntimeError(f"video kanonik tidak ditemukan: {video}")

    client = WoopSocial(api_key)
    accounts, project_id = _select_accounts(client, _requested_platforms())
    caption = format_caption(content)
    print(
        "[info] WoopSocial target: "
        + ", ".join(f"{a['platform']}:{a.get('username', a['id'])}" for a in accounts)
    )

    if dry_run:
        media_id = _find_test_media(client)
        uploaded_for_test = False
        if not media_id:
            print("[info] Library media kosong; upload video hanya untuk validasi dry-run.")
            media_id = _upload_media(client, project_id, video)
            uploaded_for_test = True
        payload = build_payload(media_id, accounts, caption)
        validation = client.request("POST", "/posts/validate", payload=payload)
        print(f"[info] WoopSocial dry-run validate: {json.dumps(validation, ensure_ascii=False)}")
        return PublishResult(
            target="woopsocial",
            status="dry_run",
            message=(
                f"dry-run: metadata {len(caption)} karakter, validasi "
                f"{'OK' if validation.get('isValid') else 'GAGAL'}, "
                f"{'upload untuk validasi' if uploaded_for_test else 'media uji'}, post tidak dibuat"
            ),
        )

    media_id = _upload_media(client, project_id, video)
    payload = build_payload(media_id, accounts, caption)
    validation = client.request("POST", "/posts/validate", payload=payload)
    if not validation.get("isValid"):
        raise RuntimeError(f"payload WoopSocial ditolak: {json.dumps(validation, ensure_ascii=False)[:800]}")

    post = client.request("POST", "/posts", payload=payload)
    post_id = str(post.get("id") or "")
    if not post_id:
        raise RuntimeError(f"respons posts_create tanpa id: {json.dumps(post, ensure_ascii=False)[:500]}")

    deliveries = [
        {
            "platform": item.get("platform"),
            "status": item.get("deliveryStatus"),
            "url": item.get("externalPostUrl"),
        }
        for item in post.get("socialAccountPosts", [])
    ]
    _write_log(
        f"post-{post_id}-{now_utc_iso().replace(':', '-')}",
        {
            "createdAt": now_utc_iso(),
            "postId": post_id,
            "projectId": project_id,
            "mediaId": media_id,
            "schedule": payload["schedule"],
            "caption": caption,
            "targets": payload["socialAccounts"],
            "validation": validation,
            "deliveries": deliveries,
        },
    )
    print(f"[ok] WoopSocial post ID: {post_id}")
    for item in deliveries:
        print(f"[ok] {item['platform']}: {item['status']} {item['url'] or ''}".rstrip())
    url = next((item["url"] for item in deliveries if item.get("url")), None)
    message = ", ".join(f"{d['platform']}={d['status']}" for d in deliveries) or None
    return PublishResult(target="woopsocial", status="success", id=post_id, url=url, message=message)
