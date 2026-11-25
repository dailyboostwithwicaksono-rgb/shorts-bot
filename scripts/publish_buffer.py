"""Publisher Buffer: createPost (shareNow) ke Facebook + Threads via GraphQL.

Buffer tidak menyediakan endpoint upload media. Video harus berupa URL HTTPS
publik yang stabil. Secara default video di-host sebagai GitHub Release asset
(repo public + `contents: write`), lalu URL-nya dipakai di `assets[].video.url`.
Google Drive tidak dipakai karena link-nya bukan file direct/public.

Env:
- BUFFER_API_KEY        : wajib (kunci API personal Buffer).
- BUFFER_ORGANIZATION_ID: opsional, default organisasi utama.
- BUFFER_SERVICES       : opsional, default `facebook,threads`.
- BUFFER_MODE           : opsional, default `shareNow` (atau `customScheduled`).
- BUFFER_FACEBOOK_POST_TYPE: opsional, default `reel` (`post`/`reel`/`story`).
- BUFFER_DUE_AT         : wajib bila mode `customScheduled` (ISO 8601 UTC).
- BUFFER_VIDEO_URL      : opsional; bila diisi, upload Release dilewati.
- BUFFER_RELEASE_TAG    : opsional, default `media`.
- BUFFER_ASSET_TTL_HOURS: opsional, default 6 jam (asset lama dibersihkan).
- GH_TOKEN/GITHUB_TOKEN : diperlukan untuk upload Release asset.

Dry-run: hanya query akun/channel + susun payload; tidak upload dan tidak
membuat post.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from common import ROOT, WORK
from content import CanonicalContent
from publish_youtube import PublishResult

BUFFER_API = "https://api.buffer.com"
GH_API = "https://api.github.com"
GH_UPLOAD = "https://uploads.github.com"
DEFAULT_ORG_ID = "67966ea2f0cdace9b4192336"
DEFAULT_SERVICES = ("facebook", "threads")
THREADS_TEXT_LIMIT = 500
FACEBOOK_TEXT_LIMIT = 2200
FACEBOOK_POST_TYPES = ("post", "reel", "story")

QUERY_CHANNELS = """
query BufferChannels($organizationId: OrganizationId!) {
  channels(input: { organizationId: $organizationId }) {
    id
    name
    service
    isDisconnected
    isLocked
    isQueuePaused
  }
}
"""

MUTATION_CREATE_POST = """
mutation BufferCreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    __typename
    ... on PostActionSuccess {
      post { id status dueAt channelId text externalLink }
    }
    ... on MutationError {
      message
    }
  }
}
"""

_REDACT = (
    re.compile(r"(?i)(key=)[^&\s]+"),
    re.compile(r"(?i)(bearer\s+)[^\s]+"),
)


def _env_flag(name: str, default: bool = True) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _safe_error(exc: Exception, api_key: str = "") -> str:
    msg = str(exc)
    if api_key:
        msg = msg.replace(api_key, "***")
    for pattern in _REDACT:
        msg = pattern.sub(r"\1***", msg)
    return msg[:600]


def _requested_services() -> list[str]:
    raw = (os.getenv("BUFFER_SERVICES") or ",".join(DEFAULT_SERVICES)).strip()
    result: list[str] = []
    for part in raw.replace(";", ",").split(","):
        key = part.strip().lower()
        if key and key not in result:
            result.append(key)
    return result or list(DEFAULT_SERVICES)


def _facebook_post_type() -> str:
    raw = (os.getenv("BUFFER_FACEBOOK_POST_TYPE") or "reel").strip().lower()
    if not raw:
        raw = "reel"
    if raw not in FACEBOOK_POST_TYPES:
        raise RuntimeError(
            "BUFFER_FACEBOOK_POST_TYPE tidak dikenal: "
            f"{raw} (pilih: {', '.join(FACEBOOK_POST_TYPES)})"
        )
    return raw


def _format_text(content: CanonicalContent, service: str) -> str:
    """Judul + deskripsi kanonik, dipotong sesuai batas masing-masing channel.

    `manifest.caption` sengaja dipakai sebagai alias judul oleh `plan.py`, jadi
    bukan sumber deskripsi. Memakainya membuat caption Threads/fb hanya mengulang
    judul. Sumber konten adalah `manifest.description` (lihat publish_woopsocial).
    """
    title = (content.title or "").strip()
    body = re.sub(r"[ \t]{2,}", " ", (content.description or "").strip())
    if not body:
        body = (content.caption or "").strip()
    if body == title:
        body = ""

    tags = " ".join(content.hashtags or [])
    suffix = ""
    if tags and tags not in body:
        suffix = f"\n\n{tags}"

    limit = THREADS_TEXT_LIMIT if service == "threads" else FACEBOOK_TEXT_LIMIT
    prefix = f"{title}\n\n" if title else ""
    room = limit - len(prefix) - len(suffix) - 3  # 3 karakter untuk elipsis
    if room < 40:
        return (prefix + suffix)[:limit].strip()
    if len(body) > room:
        body = body[:room].rstrip() + "..."
    return (prefix + body + suffix).strip()


class BufferClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def gql(self, query: str, variables: dict | None = None) -> dict:
        response = requests.post(
            BUFFER_API,
            headers=self.headers,
            json={"query": query, "variables": variables or {}},
            timeout=90,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Buffer HTTP {response.status_code}: "
                f"{_safe_error(Exception(response.text[:300]), self.api_key)}"
            )
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError(
                "Buffer GraphQL error: "
                + _safe_error(Exception(json.dumps(payload["errors"])), self.api_key)
            )
        return payload.get("data") or {}

    def channels(self, organization_id: str) -> list[dict]:
        data = self.gql(QUERY_CHANNELS, {"organizationId": organization_id})
        return data.get("channels") or []

    def create_post(self, payload: dict) -> dict:
        data = self.gql(MUTATION_CREATE_POST, {"input": payload})
        result = data.get("createPost") or {}
        typename = result.get("__typename")
        if typename != "PostActionSuccess":
            raise RuntimeError(
                f"Buffer createPost {typename}: {result.get('message') or 'tanpa pesan'}"
            )
        return result.get("post") or {}


def _github_repo() -> str:
    repo = (os.getenv("GITHUB_REPOSITORY") or "").strip()
    if repo:
        return repo
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    remote = (result.stdout or "").strip()
    match = re.search(r"(?:github\.com[/:])([^/]+)/([^/.]+)(?:\.git)?$", remote)
    if not match:
        raise RuntimeError("Tidak bisa menentukan repo GitHub untuk Release asset.")
    return f"{match.group(1)}/{match.group(2)}"


def _gh_headers() -> dict[str, str]:
    token = (os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("GH_TOKEN/GITHUB_TOKEN kosong; tidak bisa upload Release asset.")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }


def _release_or_create(repo: str, tag: str, headers: dict[str, str]) -> int:
    url = f"{GH_API}/repos/{repo}/releases/tags/{tag}"
    response = requests.get(url, headers=headers, timeout=60)
    if response.status_code == 200:
        return int(response.json()["id"])
    if response.status_code != 404:
        raise RuntimeError(f"Gagal cek Release {tag}: HTTP {response.status_code}")

    response = requests.post(
        f"{GH_API}/repos/{repo}/releases",
        headers=headers,
        json={
            "tag_name": tag,
            "name": tag,
            "body": "Public video assets untuk publish Buffer (shorts-bot).",
            "draft": False,
            "prerelease": False,
        },
        timeout=60,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"Gagal buat Release {tag}: HTTP {response.status_code} {response.text[:300]}"
        )
    return int(response.json()["id"])


def _cleanup_old_assets(repo: str, release_id: int, headers: dict[str, str]) -> None:
    raw = (os.getenv("BUFFER_ASSET_TTL_HOURS") or "6").strip()
    try:
        ttl = float(raw)
    except ValueError:
        ttl = 6.0
    if ttl <= 0:
        return
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl)
    response = requests.get(
        f"{GH_API}/repos/{repo}/releases/{release_id}/assets",
        headers=headers,
        params={"per_page": 100},
        timeout=60,
    )
    if response.status_code != 200:
        return
    for asset in response.json() or []:
        try:
            created = datetime.fromisoformat(
                str(asset.get("created_at") or "").replace("Z", "+00:00")
            )
        except ValueError:
            continue
        if created < cutoff:
            requests.delete(str(asset.get("url") or ""), headers=headers, timeout=60)


def _upload_video(repo: str, release_id: int, video: Path, headers: dict[str, str]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = (os.getenv("GITHUB_RUN_ID") or "").strip()
    prefix = f"shorts-{run_id}-" if run_id else "shorts-"
    name = f"{prefix}{stamp}.mp4"
    upload_headers = {**headers, "Content-Type": "video/mp4"}
    with video.open("rb") as handle:
        response = requests.post(
            f"{GH_UPLOAD}/repos/{repo}/releases/{release_id}/assets",
            params={"name": name},
            headers=upload_headers,
            data=handle,
            timeout=600,
        )
    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"Gagal upload Release asset: HTTP {response.status_code} {response.text[:300]}"
        )
    return str(response.json()["browser_download_url"])


def _verify_media_url(url: str) -> None:
    response = requests.get(url, stream=True, allow_redirects=True, timeout=120)
    try:
        length = response.headers.get("Content-Length")
        if response.status_code != 200 or (length and int(length) <= 0):
            raise RuntimeError(f"URL media tidak bisa diakses publik: HTTP {response.status_code}")
    finally:
        response.close()


def _host_video(video: Path) -> str:
    explicit = (os.getenv("BUFFER_VIDEO_URL") or "").strip()
    if explicit:
        _verify_media_url(explicit)
        return explicit
    if not video.is_file():
        raise RuntimeError(f"File video tidak ditemukan: {video}")
    headers = _gh_headers()
    repo = _github_repo()
    tag = (os.getenv("BUFFER_RELEASE_TAG") or "media").strip() or "media"
    release_id = _release_or_create(repo, tag, headers)
    _cleanup_old_assets(repo, release_id, headers)
    url = _upload_video(repo, release_id, video, headers)
    _verify_media_url(url)
    return url


def _log_payload(entry: dict) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = WORK / f"buffer_{stamp}.json"
    path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[info] Log Buffer: {path}")


def publish_buffer(content: CanonicalContent, dry_run: bool = False) -> PublishResult:
    api_key = (os.getenv("BUFFER_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("BUFFER_API_KEY kosong. Isi Secret GitHub / .env lokal.")

    organization_id = (
        os.getenv("BUFFER_ORGANIZATION_ID") or DEFAULT_ORG_ID
    ).strip()
    services = _requested_services()
    mode = (os.getenv("BUFFER_MODE") or "shareNow").strip() or "shareNow"
    if mode not in ("shareNow", "customScheduled", "addToQueue", "shareNext"):
        raise RuntimeError(f"BUFFER_MODE tidak dikenal: {mode}")
    fb_post_type = _facebook_post_type()

    client = BufferClient(api_key)
    available = client.channels(organization_id)
    channels: dict[str, dict] = {}
    for channel in available:
        service = str(channel.get("service") or "").lower()
        if service not in services:
            continue
        if channel.get("isDisconnected") or channel.get("isLocked"):
            print(f"[warn] Buffer channel {service} tidak aktif; dilewati.")
            continue
        channels.setdefault(service, channel)
    for service in services:
        if service not in channels:
            print(f"[warn] Buffer channel `{service}` belum terhubung; dilewati.")
    if not channels:
        raise RuntimeError("Tidak ada channel Buffer yang aktif untuk target: " + ", ".join(services))

    texts = {service: _format_text(content, service) for service in channels}
    video_url = "<URL Release asset dibuat saat eksekusi>"
    if dry_run:
        explicit = (os.getenv("BUFFER_VIDEO_URL") or "").strip()
        if explicit:
            _verify_media_url(explicit)
            video_url = explicit
    else:
        video_url = _host_video(content.video_path)

    payloads: list[dict] = []
    for service in services:
        channel = channels.get(service)
        if not channel:
            continue
        payload: dict = {
            "text": texts[service],
            "channelId": channel["id"],
            "schedulingType": "automatic",
            "mode": mode,
            "assets": [{"video": {"url": video_url}}],
        }
        if service == "facebook":
            payload["metadata"] = {"facebook": {"type": fb_post_type}}
        if mode == "customScheduled":
            due_at = (os.getenv("BUFFER_DUE_AT") or "").strip()
            if not due_at:
                raise RuntimeError("BUFFER_DUE_AT wajib untuk mode customScheduled.")
            payload["dueAt"] = due_at
        payloads.append({"service": service, "channel": channel["name"], "input": payload})

    summary = {
        "dry_run": dry_run,
        "mode": mode,
        "facebookPostType": fb_post_type,
        "organizationId": organization_id,
        "videoUrl": video_url,
        "texts": texts,
        "payloads": payloads,
        "results": [],
    }

    if dry_run:
        _log_payload(summary)
        names = ", ".join(f"{p['service']}:{p['channel']}" for p in payloads)
        return PublishResult(
            target="buffer",
            status="dry_run",
            message=f"{len(payloads)} channel valid, 0 post dibuat ({names})",
        )

    failures: list[str] = []
    ids: list[str] = []
    for item in payloads:
        try:
            post = client.create_post(item["input"])
            post_id = str(post.get("id") or "")
            ids.append(post_id)
            item["result"] = {
                "id": post_id,
                "status": post.get("status"),
                "externalLink": post.get("externalLink"),
            }
            print(
                f"[ok] Buffer {item['service']}: post {post_id} "
                f"status={post.get('status') or '-'}"
            )
        except Exception as exc:  # noqa: BLE001 - lanjut channel berikutnya
            msg = _safe_error(exc, api_key)
            failures.append(f"{item['service']}: {msg}")
            item["result"] = {"error": msg}
            print(f"[error] Buffer {item['service']} gagal: {msg}")

    summary["results"] = [p.get("result") for p in payloads]
    _log_payload(summary)
    if failures:
        raise RuntimeError("Buffer gagal: " + " | ".join(failures))
    return PublishResult(
        target="buffer",
        status="success",
        id=",".join(ids) or None,
        message=f"{len(ids)} post dibuat via {mode}",
    )
