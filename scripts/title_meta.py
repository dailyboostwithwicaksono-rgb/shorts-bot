"""Shared title metadata & prompt helpers (used by local workflow; reusable by general workflows).

Source of truth for title styles: config/title_styles.json (shared). Local execution may override
by providing title_styles.json in its folder.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SHARED_TITLE_STYLES_PATH = ROOT / "config" / "title_styles.json"
# Backward compat: old caption styles file
SHARED_CAPTION_STYLES_PATH = ROOT / "config" / "caption_styles.json"


def _normalize_line_parts(line: Any) -> list[dict]:
    if isinstance(line, list):
        out = []
        for p in line:
            if isinstance(p, dict):
                out.append({"text": str(p.get("text", "")), "emphasis": bool(p.get("emphasis", False))})
            elif isinstance(p, str):
                out.append({"text": p, "emphasis": False})
        return out
    if isinstance(line, str):
        return [{"text": line, "emphasis": False}]
    return [{"text": str(line), "emphasis": False}]


def _line_plain_text(parts: list[dict]) -> str:
    return "".join(p.get("text", "") for p in parts)


def transcript_plain_text(transcript: dict | None) -> str:
    parts_out: list[str] = []
    for seg in ((transcript or {}).get("segments") or []):
        if not isinstance(seg, dict):
            continue
        for ln in (seg.get("lines") or []):
            line_parts = _normalize_line_parts(ln)
            txt = _line_plain_text(line_parts).strip()
            if txt:
                parts_out.append(txt)
    return "\n".join(parts_out).strip()


def load_title_styles(exec_dir: Path | None = None) -> dict:
    """Load title styles: prefer exec_dir/title_styles.json, then caption_styles.json (legacy), else shared config."""
    if exec_dir is not None:
        for name in ("title_styles.json", "caption_styles.json"):
            local_p = Path(exec_dir) / name
            if local_p.exists():
                return json.loads(local_p.read_text(encoding="utf-8"))
    for p in (SHARED_TITLE_STYLES_PATH, SHARED_CAPTION_STYLES_PATH):
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"title_styles.json tidak ditemukan: {SHARED_TITLE_STYLES_PATH}")


def select_title_style(styles: dict, yt: dict | None = None) -> dict:
    """Pilih 1 gaya: pakai preferensi title_style/preferred_title_style (legacy: caption_style) jika cocok, selain itu acak."""
    yt = yt or {}
    all_styles = [s for s in (styles.get("styles") or []) if isinstance(s, dict)]
    if not all_styles:
        raise ValueError("title_styles tidak berisi gaya (styles) yang valid.")

    preferred = str(
        yt.get("title_style")
        or yt.get("preferred_title_style")
        or yt.get("caption_style")
        or yt.get("preferred_caption_style")
        or ""
    ).strip().lower()
    if preferred:
        for s in all_styles:
            sid = str(s.get("id") or "").strip().lower()
            sname = str(s.get("name") or "").strip().lower()
            if preferred == sid or preferred == sname:
                return s
        # preferred tidak cocok -> fallback acak
    return random.choice(all_styles)


# Backward-compatible aliases
def load_caption_styles(exec_dir: Path | None = None) -> dict:
    return load_title_styles(exec_dir)


def select_caption_style(styles: dict, yt: dict | None = None) -> dict:
    return select_title_style(styles, yt)


def build_title_prompt(
    styles: dict,
    selected_style: dict,
    quote: dict | None,
    transcript: dict | None,
    yt: dict | None = None,
) -> str:
    """Bangun prompt judul (title) untuk 1 gaya terpilih (AI tidak memilih dari daftar)."""
    yt = yt or {}
    quote = quote or {}
    q_lines = [str(x) for x in (quote.get("lines") or [])]
    q_text = " / ".join([ln for ln in q_lines if ln.strip()])
    author = str(quote.get("author") or "").strip()
    language = str(quote.get("language") or yt.get("defaultLanguage") or "en")
    vo_text = transcript_plain_text(transcript)
    style_json = json.dumps(selected_style, ensure_ascii=False, indent=2)
    notes = styles.get("notes") or []

    return f"""Kamu penulis judul YouTube Shorts yang tenang, jujur, dan reflektif.
Tugas: buat 1 judul singkat berdasarkan konteks konten, mengikuti gaya yang sudah dipilih di bawah (jangan memilih gaya lain).

Konteks konten:
- Bahasa: {language}
- Quote: {q_text or "(tidak ada)"}
- Author: {author or "-"}
- Narasi/voiceover (ringkas, nada & inti): 
{vo_text or "(tidak ada transkrip)"}

Gaya judul yang dipakai (metadata, JSON):
{style_json}

Catatan praktis:
{chr(10).join(f"- {n}" for n in notes) if notes else "- (tidak ada)"}

Aturan WAJIB:
- Judul harus selaras dengan nada voiceover (tenang/jujur, hindari clickbait berlebihan) dan mengikuti gaya di atas.
- Utamakan kejelasan di beberapa kata awal (bisa terpotong di UI Shorts).
- Gunakan bahasa yang sesuai konteks (ikuti Bahasa di atas).
- Jangan pakai emoji. Jangan pakai tanda kutip di dalam judul kecuali sangat perlu.

Balas HANYA JSON valid:
{{
  "title": "teks judul final",
  "style_id": "{str(selected_style.get('id') or '').strip()}",
  "style_name": "{str(selected_style.get('name') or '').strip()}",
  "reason": "alasan singkat mengapa judul ini selaras dengan gaya (1 kalimat)"
}}
"""


# Backward-compatible alias
def build_caption_prompt(*args, **kwargs):
    return build_title_prompt(*args, **kwargs)
