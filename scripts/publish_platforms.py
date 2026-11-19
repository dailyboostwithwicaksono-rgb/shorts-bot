"""Scaffolding multi-platform (Fase 4): formatter & publisher stub/dry-run untuk TikTok/Meta/X.

Catatan: integrasi API nyata bergantung pada akses, kredensial, izin, dan batasan masing-masing platform.
Modul ini menyediakan kontrak/formatter dan mode dry-run; publish nyata diaktifkan bertahap saat siap.
"""
import os
from dataclasses import dataclass

from content import CanonicalContent
from publish_youtube import PublishResult


def _join_hashtags(hashtags: list[str], limit: int | None = None) -> str:
    hs = hashtags[:limit] if limit is not None else hashtags
    return " ".join(hs).strip()


def format_tiktok(content: CanonicalContent) -> dict:
    # TikTok: caption teks (batas konservatif ~2200); tidak ada title terpisah.
    base = content.caption or content.title
    tags = _join_hashtags(content.hashtags)
    text = base.strip()
    if tags:
        text = f"{text}\n\n{tags}".strip()
    if len(text) > 2200:
        text = text[:2197].rstrip() + "..."
    return {"caption": text, "privacy": content.privacy}


def format_meta(content: CanonicalContent) -> dict:
    # Meta (IG/Facebook/Reels): caption; batas konservatif ~2200.
    base = content.caption or content.title
    tags = _join_hashtags(content.hashtags)
    text = base.strip()
    if tags:
        text = f"{text}\n\n{tags}".strip()
    if len(text) > 2200:
        text = text[:2197].rstrip() + "..."
    return {"caption": text, "privacy": content.privacy}


def format_x(content: CanonicalContent) -> dict:
    # X: teks post terbatas (280); unggah media terpisah di API nyata.
    base = (content.caption or content.title or "").strip()
    tags = content.hashtags[:3]
    suffix = (" " + " ".join(tags)) if tags else ""
    max_len = 280
    room = max_len - len(suffix)
    if room < 0:
        suffix = ""
        room = max_len
    if len(base) > room:
        base = base[: max(0, room - 1)].rstrip() + "…"
    text = (base + suffix).strip()
    return {"text": text}


def _has_env(*names: str) -> bool:
    return all((os.getenv(n) or "").strip() for n in names)


def publish_platform(target: str, content: CanonicalContent, dry_run: bool = False) -> PublishResult:
    target = (target or "").lower()
    if target == "tiktok":
        formatted = format_tiktok(content)
        required = ("TIKTOK_ACCESS_TOKEN",)
        impl_ready = False
    elif target == "meta":
        formatted = format_meta(content)
        required = ("META_ACCESS_TOKEN", "META_IG_USER_ID")
        impl_ready = False
    elif target == "x":
        formatted = format_x(content)
        required = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")
        impl_ready = False
    else:
        return PublishResult(target=target, status="skipped", message="target tidak dikenal")

    if dry_run:
        print(f"[info] {target} dry-run payload: {formatted}")
        return PublishResult(target=target, status="dry_run", message="dry-run: formatter OK, upload/publish dilewati")

    if not _has_env(*required):
        missing = [n for n in required if not (os.getenv(n) or "").strip()]
        raise RuntimeError(f"kredensial {target} belum lengkap: {', '.join(missing)}")

    if not impl_ready:
        # Belum ada integrasi API nyata; jaga agar tidak diam-diam gagal/sukses palsu.
        raise RuntimeError(
            f"publish nyata untuk {target} belum diimplementasikan (butuh akses/API & implementasi platform). "
            "Gunakan PUBLISH_DRY_RUN=1 untuk verifikasi formatter."
        )

    # Tempat integrasi nyata per platform (saat akses & API siap).
    return PublishResult(target=target, status="failed", message="implementasi publish nyata belum tersedia")