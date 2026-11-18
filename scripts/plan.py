#!/usr/bin/env python3
"""Pilih tema + video Pexels, lalu minta AI menulis 3 baris teks & caption."""
import hashlib
import json
import os
from datetime import date
from pathlib import Path

from ai import generate_plan
from pexels import pick_background

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "themes.json"
WORK = ROOT / "work"
MUSIC = WORK / "music"
PLAN_OUT = ROOT / "render_plan.json"


def pick_theme(themes: list[dict], day: str) -> dict:
    return sorted(
        themes,
        key=lambda t: hashlib.sha256(f"{t['id']}|{day}".encode("utf-8")).hexdigest(),
    )[0]


def main() -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    defaults = cfg["defaults"]
    day = os.getenv("RUN_DATE") or date.today().isoformat()
    WORK.mkdir(parents=True, exist_ok=True)
    MUSIC.mkdir(parents=True, exist_ok=True)

    theme = pick_theme(cfg["themes"], day)
    bg_path = WORK / "bg.mp4"
    bg = pick_background(theme, day, bg_path)

    music_pool = theme.get("music") or []
    if isinstance(music_pool, dict):
        music_pool = [music_pool]
    available = [m for m in music_pool if (MUSIC / m["file"]).exists()]
    if not available:
        raise SystemExit(
            f"Tidak ada file musik di {MUSIC}. Upload salah satu dari: "
            + ", ".join(m["file"] for m in music_pool)
        )
    music = sorted(
        available,
        key=lambda m: hashlib.sha256(f"{m['file']}|{day}".encode("utf-8")).hexdigest(),
    )[0]
    music_path = MUSIC / music["file"]

    prompt = f"""Kamu penulis konten Shorts Bahasa Indonesia.

Tema kanal: {theme['niche']}
Video latar berasal dari Pexels dengan deskripsi: {bg.get('description') or theme.get('pexels_query', '')}

Tugas:
1. Tulis tepat {defaults['lines']} baris teks yang akan muncul BERTAHAP di tengah video.
   - Setiap baris maksimal 6 kata dan 32 karakter, Bahasa Indonesia, mudah dipahami.
   - Baris 2 boleh sangat pendek, misalnya: terus bergerak,
   - Tanpa emoji dan tanpa tanda kutip. Hindari titik di akhir.
   - Baris 1 hook, baris 2 jembatan, baris 3 ajakan/penutup. Susun seperti tangga yang bertumpuk.
2. Buat judul YouTube maksimal 100 karakter.
3. Buat caption/hook description maksimal 140 karakter.
4. Buat tepat 6 hashtag, mayoritas Bahasa Indonesia, sertakan #Shorts.

Balas HANYA JSON:
{{
  "lines": ["BARIS SATU", "BARIS DUA", "BARIS TIGA"],
  "title": "...",
  "caption": "...",
  "hashtags": ["#Shorts", "..."],
  "privacy": "public"
}}
"""
    try:
        ai = generate_plan(prompt, [])
        lines = [str(x) for x in ai.get("lines", [])][: defaults["lines"]]
        if len(lines) != defaults["lines"]:
            raise ValueError("Jumlah baris tidak sesuai")
        title = str(ai.get("title") or "Shorts")[:100]
        caption = str(ai.get("caption") or "Tiga baris singkat untuk harimu.")[:140]
        hashtags = [str(h) for h in ai.get("hashtags", [])][:6]
        privacy = str(ai.get("privacy") or "public")
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] AI gagal ({exc}); pakai teks fallback.")
        lines = [
            "KOTA TIDUR, SEMANGATMU TIDAK",
            "TERUS BERGERAK,",
            "SATU LANGKAH DEMI SATU LANGKAH",
        ][: defaults["lines"]]
        title = "Tiga hal singkat yang bikin beda"
        caption = "Satu ide sederhana untuk hari ini. Setuju?"
        hashtags = ["#Shorts", "#Motivasi", "#Produktivitas", "#Tips", "#FYP", "#Indonesia"]
        privacy = "public"

    if not hashtags:
        hashtags = ["#Shorts", "#Ide", "#Tips", "#FYP", "#Viral", "#Indonesia"]

    attribution = (
        f"Video latar: {bg['photographer']} / Pexels — {bg['url']}\n"
        f"Musik: {music['title']} — {music['url']} (Free To Use)"
    )
    description = f"{caption}\n\n{' '.join(hashtags)}\n\n{attribution}"

    plan = {
        "date": day,
        "theme": theme["id"],
        "duration": int(defaults["duration_seconds"]),
        "lines": lines,
        "font_size": int(defaults["font_size"]),
        "min_font_size": int(defaults["min_font_size"]),
        "fade_in_min": float(defaults["fade_in_min"]),
        "fade_in_max": float(defaults["fade_in_max"]),
        "fade_in_per_word": float(defaults["fade_in_per_word"]),
        "read_words_per_sec": float(defaults["read_words_per_sec"]),
        "read_chars_per_sec": float(defaults["read_chars_per_sec"]),
        "read_buffer": float(defaults["read_buffer"]),
        "band_top": int(defaults["band_top"]),
        "band_height": int(defaults["band_height"]),
        "overlay_opacity": float(defaults["overlay_opacity"]),
        "brightness": float(defaults["brightness"]),
        "saturation": float(defaults["saturation"]),
        "music_volume": float(defaults["music_volume"]),
        "background": str(bg_path),
        "music": str(music_path),
        "title": title,
        "caption": caption,
        "hashtags": hashtags,
        "description": description,
        "privacy": os.getenv("YT_PRIVACY") or privacy,
    }
    PLAN_OUT.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] tema: {theme['id']} | Pexels video: {bg['id']} | musik: {music['title']}")
    print(f"[ok] rencana ditulis: {PLAN_OUT}")


if __name__ == "__main__":
    main()
