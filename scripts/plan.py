#!/usr/bin/env python3
"""Buat rencana video quotes: famous (AI) atau custom (input manual/Telegram nanti)."""
import hashlib
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path

from ai import generate_plan
from pexels import pick_background

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "themes.json"
WORK = ROOT / "work"
MUSIC = WORK / "music"
PLAN_OUT = ROOT / "render_plan.json"
USED_QUOTES = ROOT / "data" / "used_quotes.jsonl"


def pick_theme(themes: list[dict], day: str) -> dict:
    return sorted(
        themes,
        key=lambda t: hashlib.sha256(f"{t['id']}|{day}".encode("utf-8")).hexdigest(),
    )[0]


def load_used_quotes(limit: int = 60) -> list[dict]:
    if not USED_QUOTES.exists():
        return []
    items: list[dict] = []
    for line in USED_QUOTES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except Exception:
            continue
    return items[-limit:]


def append_used_quote(entry: dict) -> None:
    USED_QUOTES.parent.mkdir(parents=True, exist_ok=True)
    with USED_QUOTES.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def normalize_author(author: str) -> str:
    a = str(author or "").strip()
    a = re.sub(r"^\s*-\s*", "", a)
    a = re.sub(r"\s*-\s*$", "", a)
    a = a.strip() or "Unknown"
    return f"- {a} -"


def split_quote_lines(text: str, max_lines: int = 3) -> list[str]:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if "|" in raw:
        parts = [p.strip() for p in raw.split("|")]
    elif "\n" in raw:
        parts = [p.strip() for p in raw.split("\n")]
    else:
        # coba pecah otomatis jadi baris pendek
        words = raw.strip().split()
        parts = []
        cur: list[str] = []
        for w in words:
            cur.append(w)
            if len(cur) >= 5 or sum(len(x) for x in cur) + len(cur) - 1 >= 28:
                parts.append(" ".join(cur))
                cur = []
        if cur:
            parts.append(" ".join(cur))
    parts = [p for p in parts if p]
    if not parts:
        parts = ["Quotes hari ini"]
    return parts[:max_lines]


def detect_language(text: str, hint: str = "auto") -> str:
    hint = (hint or "auto").strip().lower()
    if hint in ("en", "id"):
        return hint
    # heuristik sederhana: dominan ASCII/english words -> en
    ascii_letters = sum(1 for c in text if ("a" <= c.lower() <= "z"))
    non_ascii = sum(1 for c in text if ord(c) > 127)
    if non_ascii == 0 and ascii_letters >= max(4, len(text) // 3):
        # cek beberapa kata umum ID
        id_markers = {"yang", "dan", "untuk", "dengan", "tidak", "kamu", "aku", "kita", "hari", "hidup"}
        words = {w.lower().strip(".,!?\"'") for w in text.split()}
        if words & id_markers:
            return "id"
        return "en"
    return "id"


def build_famous_prompt(theme: dict, bg: dict, used: list[dict]) -> str:
    used_lines = []
    for u in used[-30:]:
        q = str(u.get("quote") or "").strip()
        a = str(u.get("author") or "").strip()
        if q:
            used_lines.append(f"- {q} — {a}" if a else f"- {q}")
    used_block = "\n".join(used_lines) if used_lines else "- (belum ada)"
    return f"""Kamu kurator quotes terkenal untuk YouTube Shorts.

Tema/niche: {theme.get('niche', 'Quotes inspiratif')}
Latar video (Pexels): {bg.get('description') or theme.get('pexels_query', '')}

Buat 1 quotes terkenal yang belum pernah dipakai.
Aturan WAJIB:
- Jika quotes aslinya berbahasa Inggris, TETAP gunakan bahasa Inggris.
- Jika quotes aslinya bukan bahasa Inggris, gunakan Bahasa Indonesia (terjemahan yang umum/baik).
- Sertakan nama penulis/ tokoh yang benar.
- Pecah teks quote menjadi 1-3 baris pendek (maks 6 kata / 32 karakter per baris), mudah dibaca di layar HP.
- Jangan pakai emoji dan jangan pakai tanda kutip di dalam baris.
- Hindari mengulang quotes berikut:
{used_block}

Balas HANYA JSON valid:
{{
  "quote": "teks quote utuh",
  "quote_lines": ["BARIS 1", "BARIS 2"],
  "author": "Nama Penulis",
  "language": "en",
  "title": "judul YouTube maks 100 karakter",
  "caption": "caption maks 140 karakter",
  "hashtags": ["#Shorts", "#Quotes", "..."],
  "privacy": "public"
}}
"""


def build_custom_metadata_prompt(quote: str, author: str, language: str) -> str:
    lang_name = "English" if language == "en" else "Bahasa Indonesia"
    return f"""Buat metadata YouTube Shorts untuk quote berikut.

Quote: {quote}
Author: {author}
Bahasa utama: {lang_name}

Balas HANYA JSON valid:
{{
  "title": "judul YouTube maks 100 karakter",
  "caption": "caption maks 140 karakter",
  "hashtags": ["#Shorts", "#Quotes", "..."],
  "privacy": "public"
}}
"""


def ensure_hashtags(tags: list[str], language: str) -> list[str]:
    out = [str(t).strip() for t in (tags or []) if str(t).strip()]
    base = ["#Shorts", "#Quotes", "#QuoteOfTheDay"]
    if language == "en":
        base += ["#FamousQuotes", "#Inspiration", "#Wisdom"]
    else:
        base += ["#KataBijak", "#Motivasi", "#Inspirasi"]
    for t in base:
        if t not in out:
            out.append(t)
    # dedupe preserve order
    seen = set()
    deduped = []
    for t in out:
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        deduped.append(t if t.startswith("#") else "#" + t)
    return deduped[:8]


def main() -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    defaults = cfg["defaults"]
    day = os.getenv("RUN_DATE") or date.today().isoformat()
    run_seed = (
        os.getenv("RUN_SEED")
        or os.getenv("GITHUB_RUN_ID")
        or os.getenv("GITHUB_RUN_NUMBER")
        or datetime.now(timezone.utc).isoformat()
    )
    WORK.mkdir(parents=True, exist_ok=True)
    MUSIC.mkdir(parents=True, exist_ok=True)

    theme = pick_theme(cfg["themes"], day)
    bg_path = WORK / "bg.mp4"
    bg = pick_background(theme, run_seed, bg_path)

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
        key=lambda m: hashlib.sha256(f"{m['file']}|{run_seed}".encode("utf-8")).hexdigest(),
    )[0]
    music_path = MUSIC / music["file"]

    mode = (os.getenv("QUOTE_MODE") or "famous").strip().lower()
    custom_text = (os.getenv("QUOTE_TEXT") or "").strip()
    custom_author = (os.getenv("QUOTE_AUTHOR") or "dbcw").strip()
    custom_lang = (os.getenv("QUOTE_LANGUAGE") or "auto").strip().lower()

    used = load_used_quotes()
    quote_text = ""
    quote_lines: list[str] = []
    author_name = ""
    author_line = ""
    language = "id"
    title = "Quote of the day"
    caption = "Sebuah quote untuk hari ini."
    hashtags: list[str] = []
    privacy = "public"
    source = "ai"

    if mode == "custom" and custom_text:
        source = "custom"
        quote_text = custom_text.replace("\\n", "\n").strip()
        language = detect_language(quote_text, custom_lang)
        quote_lines = split_quote_lines(quote_text, max_lines=3)
        author_line = normalize_author(custom_author)
        author_name = author_line.strip("- ")
        try:
            meta = generate_plan(build_custom_metadata_prompt(" / ".join(quote_lines), author_name, language), [])
            title = str(meta.get("title") or title)[:100]
            caption = str(meta.get("caption") or caption)[:140]
            hashtags = [str(h) for h in meta.get("hashtags", [])]
            privacy = str(meta.get("privacy") or privacy)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] Metadata AI gagal ({exc}); pakai metadata default.")
            if language == "en":
                title = "A quote for today"
                caption = "A short quote to reflect on."
            else:
                title = "Quote hari ini"
                caption = "Sebuah kutipan singkat untuk direnungkan."
            hashtags = []
    else:
        mode = "famous"
        prompt = build_famous_prompt(theme, bg, used)
        try:
            ai = generate_plan(prompt, [])
            quote_text = str(ai.get("quote") or "").strip()
            quote_lines = [str(x).strip() for x in (ai.get("quote_lines") or []) if str(x).strip()]
            if not quote_lines and quote_text:
                quote_lines = split_quote_lines(quote_text, max_lines=3)
            quote_lines = quote_lines[:3] or ["Quotes hari ini"]
            author_name = str(ai.get("author") or "Unknown").strip() or "Unknown"
            author_line = normalize_author(author_name)
            language = str(ai.get("language") or "id").strip().lower()
            if language not in ("en", "id"):
                language = detect_language(" ".join(quote_lines), "auto")
            title = str(ai.get("title") or title)[:100]
            caption = str(ai.get("caption") or caption)[:140]
            hashtags = [str(h) for h in ai.get("hashtags", [])]
            privacy = str(ai.get("privacy") or privacy)
            if not quote_text:
                quote_text = " / ".join(quote_lines)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] AI gagal ({exc}); pakai quote fallback.")
            language = "id"
            quote_lines = ["JANGAN MENUNGGU SEMPURNA", "MULAI DARI YANG ADA"]
            quote_text = " / ".join(quote_lines)
            author_name = "Unknown"
            author_line = "- Unknown -"
            title = "Quote hari ini"
            caption = "Mulai dari langkah kecil hari ini."
            hashtags = []

    hashtags = ensure_hashtags(hashtags, language)
    lines = quote_lines + [author_line]
    line_styles = ["quote"] * len(quote_lines) + ["author"]

    attribution = (
        f"Video latar: {bg['photographer']} / Pexels — {bg['url']}\n"
        f"Musik: {music['title']} — {music['url']} (Free To Use)"
    )
    quote_credit = f"Quote: {quote_text} — {author_name}" if mode == "famous" else f"Quote: {quote_text} — {author_name}"
    description = f"{caption}\n\n{quote_credit}\n{' '.join(hashtags)}\n\n{attribution}"

    plan = {
        "date": day,
        "theme": theme["id"],
        "mode": mode,
        "source": source,
        "language": language,
        "quote": quote_text,
        "author": author_name,
        "duration": int(defaults["duration_seconds"]),
        "lines": lines,
        "line_styles": line_styles,
        "font_size": int(defaults["font_size"]),
        "min_font_size": int(defaults["min_font_size"]),
        "author_font_size": int(defaults.get("author_font_size", 48)),
        "author_min_font_size": int(defaults.get("author_min_font_size", 30)),
        "fade_in_min": float(defaults["fade_in_min"]),
        "fade_in_max": float(defaults["fade_in_max"]),
        "fade_in_per_word": float(defaults["fade_in_per_word"]),
        "line_gap": float(defaults["line_gap"]),
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

    log_entry = {
        "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "date": day,
        "mode": mode,
        "source": source,
        "language": language,
        "quote": quote_text,
        "author": author_name,
        "lines": quote_lines,
        "title": title,
    }
    append_used_quote(log_entry)

    print(f"[ok] tema: {theme['id']} | mode: {mode} | Pexels: {bg['id']} | musik: {music['title']}")
    print(f"[ok] quote: {quote_text} — {author_name}")
    print(f"[ok] rencana ditulis: {PLAN_OUT}")
    print(f"[ok] log ditambah: {USED_QUOTES}")


if __name__ == "__main__":
    main()
