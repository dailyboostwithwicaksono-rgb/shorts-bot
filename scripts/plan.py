#!/usr/bin/env python3
"""Buat rencana video quotes: list (default), famous (AI), atau custom (manual)."""
import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

from ai import generate_plan
from common import ROOT, WORK, MUSIC, PLAN_OUT, CONFIG_PATH, load_dotenv, now_utc_iso, read_json, load_used_entries, append_jsonl
from freetouse import pick_music as pick_freetouse_music
from pixabay import pick_background
from runlog import log_run

sys.path.insert(0, str(ROOT / "scripts"))

CONFIG = CONFIG_PATH
DEFAULT_QUOTES = ROOT / "data" / "quotes.json"
DEFAULT_USED = ROOT / "data" / "used_quotes.jsonl"
DEFAULT_USED_VIDEOS = ROOT / "data" / "used_videos.jsonl"
DEFAULT_USED_MUSIC = ROOT / "data" / "used_music.jsonl"

load_dotenv(ROOT / ".env")


def pick_theme(themes: list[dict]) -> dict:
    if not themes:
        raise SystemExit("config/themes.json tidak memiliki themes.")
    return random.choice(themes)


def to_lower(s: str) -> str:
    return str(s or "").lower()


def normalize_lines(lines: list) -> list[str]:
    out = []
    for x in (lines or []):
        s = to_lower(str(x or "").strip())
        if s:
            out.append(s)
    return out[:5]


def format_author(author) -> tuple[str, bool]:
    """Return (display_text, is_dash). display_text sudah termasuk ' - ' jika bukan dash."""
    a = str(author or "").strip()
    if not a:
        return "", True
    a = re.sub(r"^\s*-\s*", "", a)
    a = re.sub(r"\s*-\s*$", "", a).strip()
    if not a:
        return "", True
    return f"- {to_lower(a)} -", False


def compute_emphasis_segments(lines: list[str], emphasis: list[str]) -> list[list[dict]]:
    """Terapkan emphasis berurutan: tiap frasa ke kemunculan berikutnya yang belum terpakai."""
    norm_lines = [to_lower(x) for x in lines]
    phrases = [to_lower(str(p or "").strip()) for p in (emphasis or []) if str(p or "").strip()]
    used = [[False] * len(line) for line in norm_lines]

    matches: list[list[tuple[int, int]]] = [[] for _ in norm_lines]
    for phrase in phrases:
        if not phrase:
            continue
        found = False
        for li, line in enumerate(norm_lines):
            start = 0
            while True:
                idx = line.find(phrase, start)
                if idx == -1:
                    break
                end = idx + len(phrase)
                if not any(used[li][idx:end]):
                    for k in range(idx, end):
                        used[li][k] = True
                    matches[li].append((idx, end))
                    found = True
                    break
                start = idx + 1
            if found:
                break

    segmented: list[list[dict]] = []
    for li, line in enumerate(norm_lines):
        spans = sorted(matches[li])
        segs: list[dict] = []
        pos = 0
        for s, e in spans:
            if s > pos:
                segs.append({"text": line[pos:s], "emphasis": False})
            if e > s:
                segs.append({"text": line[s:e], "emphasis": True})
            pos = e
        if pos < len(line):
            segs.append({"text": line[pos:], "emphasis": False})
        if not segs:
            segs.append({"text": line, "emphasis": False})
        segmented.append(segs)
    return segmented


def split_custom_lines(text: str, max_lines: int = 5) -> list[str]:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if "|" in raw:
        parts = [p.strip() for p in raw.split("|")]
    elif "\n" in raw:
        parts = [p.strip() for p in raw.split("\n")]
    else:
        words = raw.strip().split()
        parts = []
        cur = []
        for w in words:
            cur.append(w)
            if len(cur) >= 6 or (sum(len(x) for x in cur) + max(0, len(cur) - 1)) >= 32:
                parts.append(" ".join(cur))
                cur = []
        if cur:
            parts.append(" ".join(cur))
    parts = [to_lower(p) for p in parts if p and p.strip()]
    return parts[:max_lines] or ["quote hari ini"]


def detect_language(text: str, hint: str = "auto") -> str:
    hint = (hint or "auto").strip().lower()
    if hint in ("en", "id"):
        return hint
    ascii_letters = sum(1 for c in text if ("a" <= c.lower() <= "z"))
    non_ascii = sum(1 for c in text if ord(c) > 127)
    if non_ascii == 0 and ascii_letters >= max(4, len(text) // 3):
        id_markers = {"yang", "dan", "untuk", "dengan", "tidak", "kamu", "aku", "kita", "hari", "hidup"}
        words = {w.lower().strip(".,!?\"'") for w in text.split()}
        if words & id_markers:
            return "id"
        return "en"
    return "id"


def ensure_hashtags(tags: list, language: str) -> list[str]:
    out = [str(t).strip() for t in (tags or []) if str(t).strip()]
    base = ["#Shorts", "#Quotes", "#QuoteOfTheDay"]
    if language == "en":
        base += ["#FamousQuotes", "#Inspiration", "#Wisdom"]
    else:
        base += ["#KataBijak", "#Motivasi", "#Inspirasi"]
    for t in base:
        if t not in out:
            out.append(t)
    seen = set()
    deduped = []
    for t in out:
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        deduped.append(t if t.startswith("#") else "#" + t)
    return deduped[:8]


def choose_music(theme: dict, seed: str, target_duration: int) -> tuple[dict, Path]:
    """Pilih musik dari Freetouse API (non-premium, tema calm/motivasi). Fallback ke file lokal bila ada."""
    out = MUSIC / "freetouse_bg.mp3"
    try:
        meta = pick_freetouse_music(seed, out, target_duration)
        return meta, out
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] Gagal mengambil musik dari Freetouse API ({exc}); coba file lokal.")
    # fallback: local files
    music_pool = theme.get("music") or []
    if isinstance(music_pool, dict):
        music_pool = [music_pool]
    local_files = []
    if MUSIC.exists():
        for ext in ("*.mp3", "*.wav", "*.m4a", "*.ogg"):
            local_files.extend(MUSIC.glob(ext))
    # prefer configured files
    available = [m for m in music_pool if (MUSIC / str(m.get("file", ""))).exists()]
    if available:
        music = random.choice(available)
        return {**music, "source": "local"}, MUSIC / music["file"]
    if local_files:
        p = random.choice(local_files)
        return {"title": p.stem, "url": "https://freetouse.com/music", "file": p.name, "source": "local"}, p
    raise SystemExit(
        f"Gagal mengambil musik Freetouse dan tidak ada file musik lokal di {MUSIC}."
    )


def build_famous_prompt(theme: dict, used: list[dict]) -> str:
    used_lines = []
    for u in used[-30:]:
        q = str(u.get("quote") or "").strip()
        a = str(u.get("author") or "").strip()
        if q:
            used_lines.append(f"- {q} — {a}" if a else f"- {q}")
    used_block = "\n".join(used_lines) if used_lines else "- (belum ada)"
    return f"""Kamu kurator quotes terkenal untuk YouTube Shorts.

Tema/niche: {theme.get('niche', 'Quotes inspiratif')}

Buat 1 quotes terkenal yang belum pernah dipakai.
Aturan WAJIB:
- Jika quotes aslinya berbahasa Inggris, TETAP gunakan bahasa Inggris.
- Jika quotes aslinya bukan bahasa Inggris, gunakan Bahasa Indonesia (terjemahan yang umum/baik).
- Sertakan nama penulis/tokoh yang benar.
- Pecah teks quote menjadi 1-5 baris pendek (mudah dibaca di layar HP).
- Gunakan huruf kecil semua (jangan huruf kapital di awal kecuali tidak bisa dihindari, sebaiknya semua kecil).
- Jangan pakai emoji dan jangan pakai tanda kutip di dalam baris.
- Hindari mengulang quotes berikut:
{used_block}

Balas HANYA JSON valid:
{{
  "quote": "teks quote utuh",
  "quote_lines": ["baris 1", "baris 2"],
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


def load_list_quote(quotes_path: Path, used_path: Path) -> dict:
    data = read_json(quotes_path)
    quotes = data.get("quotes", data) if isinstance(data, dict) else data
    if not isinstance(quotes, list) or not quotes:
        raise SystemExit(f"Daftar quotes kosong/tidak valid: {quotes_path}")

    normed = []
    for q in quotes:
        if not isinstance(q, dict):
            continue
        normed.append({
            "id": q.get("id"),
            "lines": normalize_lines(q.get("lines") or []),
            "emphasis": [to_lower(str(e).strip()) for e in (q.get("emphasis") or []) if str(e).strip()],
            "author": str(q.get("author") or "").strip(),
            "duration": int(q.get("duration") or 30),
        })
    normed = [q for q in normed if q.get("id") is not None and q["lines"]]
    normed.sort(key=lambda x: (int(x["id"]) if str(x["id"]).isdigit() else str(x["id"])))

    used_entries = load_used_entries(used_path, limit=10000)
    used_ids = set()
    for u in used_entries:
        if u.get("id") is not None:
            used_ids.add(str(u.get("id")))

    selected = None
    for q in normed:
        if str(q["id"]) not in used_ids:
            selected = q
            break
    if selected is None:
        selected = normed[0]
        print("[info] Semua quotes sudah terpakai, loop dari awal.")

    return selected


def resolve_quote(mode: str, defaults: dict, theme: dict, used: list[dict],
                  quotes_path: Path, used_path: Path) -> dict:
    selected_id = None
    quote_text = ""
    quote_lines: list[str] = []
    emphasis: list[str] = []
    author_raw = ""
    duration = int(defaults.get("duration_seconds", 30))
    language = "id"
    title = "quote hari ini"
    caption = "sebuah kutipan untuk hari ini."
    hashtags: list[str] = []
    privacy = os.getenv("YT_PRIVACY") or "public"
    source = mode

    if mode == "custom":
        custom_text = (os.getenv("QUOTE_TEXT") or "").strip()
        custom_author = (os.getenv("QUOTE_AUTHOR") or "dbcw").strip()
        custom_lang = (os.getenv("QUOTE_LANGUAGE") or "auto").strip().lower()
        custom_duration = os.getenv("QUOTE_DURATION")
        source = "custom"
        quote_lines = split_custom_lines(custom_text, max_lines=5) if custom_text else ["quote hari ini"]
        quote_text = " / ".join(quote_lines)
        author_raw = custom_author or "dbcw"
        emphasis = []
        language = detect_language(" ".join(quote_lines), custom_lang)
        if custom_duration and str(custom_duration).strip().isdigit():
            duration = max(5, min(60, int(custom_duration)))
        else:
            duration = int(defaults.get("duration_seconds", 30))
        author_name_for_meta = re.sub(r"^\s*-\s*|\s*-\s*$", "", str(author_raw)).strip() or author_raw
        try:
            meta = generate_plan(build_custom_metadata_prompt(quote_text, author_name_for_meta, language), [])
            title = str(meta.get("title") or title)[:100]
            caption = str(meta.get("caption") or caption)[:140]
            hashtags = [str(h) for h in (meta.get("hashtags") or [])]
            privacy = str(meta.get("privacy") or privacy)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] Metadata AI gagal ({exc}); pakai metadata default.")
            if language == "en":
                title = "a quote for today"
                caption = "a short quote to reflect on."
            else:
                title = "quote hari ini"
                caption = "sebuah kutipan singkat untuk direnungkan."
            hashtags = []

    elif mode == "famous":
        source = "ai"
        prompt = build_famous_prompt(theme, used)
        try:
            ai = generate_plan(prompt, [])
            raw_lines = [str(x).strip() for x in (ai.get("quote_lines") or []) if str(x).strip()]
            if not raw_lines and ai.get("quote"):
                raw_lines = split_custom_lines(str(ai.get("quote")), max_lines=5)
            quote_lines = normalize_lines(raw_lines)[:5] or ["quote hari ini"]
            quote_text = to_lower(str(ai.get("quote") or "").strip()) or " / ".join(quote_lines)
            author_raw = str(ai.get("author") or "unknown").strip() or "unknown"
            emphasis = [to_lower(str(e).strip()) for e in (ai.get("emphasis") or []) if str(e).strip()]
            language = str(ai.get("language") or "id").strip().lower()
            if language not in ("en", "id"):
                language = detect_language(" ".join(quote_lines), "auto")
            title = str(ai.get("title") or title)[:100]
            caption = str(ai.get("caption") or caption)[:140]
            hashtags = [str(h) for h in (ai.get("hashtags") or [])]
            privacy = str(ai.get("privacy") or privacy)
            duration = int(defaults.get("duration_seconds", 30))
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] AI gagal ({exc}); pakai quote fallback.")
            language = "id"
            quote_lines = ["jangan menunggu sempurna", "mulai dari yang ada"]
            quote_text = " / ".join(quote_lines)
            author_raw = "unknown"
            emphasis = []
            title = "quote hari ini"
            caption = "mulai dari langkah kecil hari ini."
            hashtags = []
            duration = int(defaults.get("duration_seconds", 30))

    else:
        # list (default)
        mode = "list"
        source = "list"
        selected = load_list_quote(quotes_path, used_path)
        selected_id = selected.get("id")
        quote_lines = selected.get("lines") or []
        quote_text = " / ".join(quote_lines)
        emphasis = selected.get("emphasis") or []
        author_raw = selected.get("author") or ""
        duration = int(selected.get("duration") or defaults.get("duration_seconds", 30))
        language = "id"
        if author_raw and str(author_raw).strip():
            caption = f"kutipan dari {to_lower(author_raw)}."
        else:
            caption = "sebuah kutipan untuk direnungkan."
        title = (quote_lines[0][:97] + "...") if quote_lines and len(quote_lines[0]) > 100 else (quote_lines[0] if quote_lines else "quote hari ini")
        hashtags = []

    # Title kanonik: gunakan AI + 1 gaya bersama (acak/preferensi) bila memungkinkan.
    # Fallback mengutamakan title (baris quote asli), baru caption legacy.
    title, _title_style_id = generate_styled_title(quote_lines, author_raw, language, title or caption)

    return {
        "mode": mode, "source": source, "selected_id": selected_id,
        "quote_text": quote_text, "quote_lines": quote_lines, "emphasis": emphasis,
        "author_raw": author_raw, "duration": duration, "language": language,
        "title": title, "caption": title, "hashtags": hashtags, "privacy": privacy,
    }


def build_description(caption: str, quote_lines: list[str], quote_text: str, author_name: str,
                      hashtags: list[str], bg: dict, music: dict) -> str:
    # attribution
    if bg.get("source") in ("pixabay", "pixabay_cache"):
        bg_credit = f"Video latar: {bg.get('user') or bg.get('photographer','')} / Pixabay — {bg.get('pageURL') or bg.get('url','')}"
    else:
        bg_credit = f"Video latar: {bg.get('photographer', '')} / Pexels — {bg.get('url', '')}"

    music_artist = music.get('artist') or ""
    music_title = music.get('title') or ""
    music_label = f"{music_title} — {music_artist}" if music_artist and music_artist != "Unknown" else music_title
    music_url = music.get('url') or ""
    if (music.get('source') or '').lower() == 'freetouse':
        music_credit = f"Musik: {music_label} — {music_url} (Free To Use / freetouse.com)" if music_url else f"Musik: {music_label} (Free To Use / freetouse.com)"
    else:
        music_credit = f"Musik: {music_label} — {music_url} (Free To Use)" if music_url else f"Musik: {music_label} (Free To Use)"

    attribution = f"{bg_credit}\n{music_credit}"
    quote_text_display = " ".join([ln.strip() for ln in quote_lines if str(ln).strip()]).strip() or quote_text.replace(" / ", " ")
    quote_credit = f"Quote: {quote_text_display}" + (f" — {author_name}" if author_name else "")
    return f"{caption}\n\n{quote_credit}\n{' '.join(hashtags)}\n\n{attribution}"


def generate_styled_title(quote_lines: list[str], author_raw: str, language: str, fallback_title: str) -> tuple[str, str | None]:
    """Generate title via shared title styles (1 random/preferred style). Fallback on failure."""
    try:
        from title_meta import build_title_prompt, load_title_styles, select_title_style

        styles = load_title_styles(None)  # config/title_styles.json (shared)
        yt_ctx = {"defaultLanguage": language}
        selected_style = select_title_style(styles, yt_ctx)
        quote = {"lines": quote_lines, "author": author_raw, "language": language}
        prompt = build_title_prompt(styles, selected_style, quote, None, yt_ctx)
        result = generate_plan(prompt, [])
        # Terima "caption" hanya sebagai alias balasan AI lama; hasil tetap title kanonik.
        title = str((result or {}).get("title") or (result or {}).get("caption") or "").strip()[:100]
        if title:
            sid = str((result or {}).get("style_id") or selected_style.get("id") or "").strip() or None
            print(f"[info] Title (AI, style={sid or '?'}) dihasilkan via gaya bersama.")
            return title, sid
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] Title AI/gaya bersama gagal ({exc}); pakai title fallback.")
    return str(fallback_title or "").strip()[:100], None


# Backward-compatible alias
def generate_styled_caption(quote_lines: list[str], author_raw: str, language: str, fallback_caption: str) -> tuple[str, str | None]:
    return generate_styled_title(quote_lines, author_raw, language, fallback_caption)


def build_plan(day: str, theme: dict, defaults: dict, q: dict, bg: dict, bg_path: Path,
               music: dict, music_path: Path) -> dict:
    quote_lines = q["quote_lines"]
    quote_text = q["quote_text"]
    author_raw = q["author_raw"]
    author_display, author_is_dash = format_author(author_raw)
    author_name = to_lower(re.sub(r"^\s*-\s*|\s*-\s*$", "", str(author_raw or "")).strip())
    quote_line_segments = compute_emphasis_segments(quote_lines, q["emphasis"])
    hashtags = ensure_hashtags(q["hashtags"], q["language"])
    privacy = os.getenv("YT_PRIVACY") or q["privacy"] or "public"
    description = build_description(q["caption"], quote_lines, quote_text, author_name, hashtags, bg, music)

    return {
        "date": day,
        "theme": theme.get("id"),
        "mode": q["mode"],
        "source": q["source"],
        "id": q["selected_id"],
        "language": q["language"],
        "quote": quote_text,
        "author": author_name,
        "duration": q["duration"],
        "lines": quote_lines + ([author_display] if author_display and not author_is_dash else (["-"] if author_is_dash else [])),
        "quote_line_segments": quote_line_segments,
        "author_display": author_display,
        "author_is_dash": author_is_dash,
        "title": q["title"],
        "caption": q["caption"],
        "hashtags": hashtags,
        "description": description,
        "privacy": privacy,
        "background": str(bg_path),
        "background_meta": {
            "source": bg.get("source"),
            "id": bg.get("id"),
            "url": bg.get("pageURL") or bg.get("url"),
            "user": bg.get("user") or bg.get("photographer"),
            "file_url": bg.get("file_url"),
            "duration_meta": bg.get("duration_meta"),
            "duration_actual": bg.get("duration_actual"),
            "keyword": bg.get("keyword"),
        },
        "music": str(music_path),
        "music_meta": {
            "source": music.get("source"),
            "id": music.get("id"),
            "title": music.get("title"),
            "artist": music.get("artist"),
            "artists": music.get("artists"),
            "url": music.get("url"),
            "mp3_url": music.get("mp3_url"),
            "duration": music.get("duration"),
            "is_premium": music.get("is_premium"),
            "genre": music.get("genre"),
            "tags": music.get("tags"),
            "query": music.get("query"),
        },
        # typography/layout/render params
        "quote_font_size": int(defaults.get("quote_font_size", 51)),
        "author_font_size": int(defaults.get("author_font_size", 28)),
        "line_spacing": float(defaults.get("line_spacing", 1.3)),
        "max_text_width": int(defaults.get("max_text_width", 920)),
        "fade_in_min": float(defaults.get("fade_in_min", 0.7)),
        "fade_in_max": float(defaults.get("fade_in_max", 1.4)),
        "fade_in_per_word": float(defaults.get("fade_in_per_word", 0.12)),
        "line_gap": float(defaults.get("line_gap", 0.7)),
        "band_top": int(defaults.get("band_top", 560)),
        "band_height": int(defaults.get("band_height", 800)),
        "overlay_opacity": float(defaults.get("overlay_opacity", 0.55)),
        "brightness": float(defaults.get("brightness", -0.18)),
        "saturation": float(defaults.get("saturation", 0.0)),
        "music_volume": float(defaults.get("music_volume", 0.28)),
        "dash_width": int(defaults.get("dash_width", 100)),
        "dash_height": int(defaults.get("dash_height", 2)),
        "quote_color": str(defaults.get("quote_color", "#FFFFFF")),
        "author_color": str(defaults.get("author_color", "#DDDDDD")),
        "full_overlay_opacity": float(defaults.get("full_overlay_opacity", 0.3)),
        "band_feather": int(defaults.get("band_feather", 140)),
    }


def main() -> None:
    t0 = time.perf_counter()
    cfg = read_json(CONFIG)
    defaults = cfg.get("defaults", {})
    day = os.getenv("RUN_DATE") or date.today().isoformat()
    run_seed = (
        os.getenv("RUN_SEED")
        or os.getenv("GITHUB_RUN_ID")
        or os.getenv("GITHUB_RUN_NUMBER")
        or datetime.now(timezone.utc).isoformat()
        or str(random.random())
    )

    WORK.mkdir(parents=True, exist_ok=True)
    MUSIC.mkdir(parents=True, exist_ok=True)
    (ROOT / "out").mkdir(parents=True, exist_ok=True)

    theme = pick_theme(cfg.get("themes") or [])

    mode = (os.getenv("QUOTE_MODE") or defaults.get("default_mode") or "list").strip().lower()
    if mode not in ("list", "custom", "famous"):
        mode = "list"

    quotes_path = ROOT / str(defaults.get("quotes_file") or "data/quotes.json")
    used_path = ROOT / str(defaults.get("used_quotes_file") or "data/used_quotes.jsonl")
    cache_path = ROOT / str(defaults.get("pixabay_cache_file") or "data/pixabay_cache.json")
    used_videos_path = ROOT / str(defaults.get("used_videos_file") or "data/used_videos.jsonl")
    used_music_path = ROOT / str(defaults.get("used_music_file") or "data/used_music.jsonl")
    used = load_used_entries(used_path)

    t_quote = time.perf_counter()
    q = resolve_quote(mode, defaults, theme, used, quotes_path, used_path)
    mode = q["mode"]
    quote_elapsed = time.perf_counter() - t_quote

    # ambil latar (Pixabay) & musik (Freetouse) paralel: independen setelah quote/duration diketahui
    bg_path = WORK / "bg.mp4"
    t_media = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_bg = ex.submit(
            pick_background,
            theme, run_seed, bg_path,
            quote_duration=q["duration"],
            quote_lines=q["quote_lines"],
            quote_text=q["quote_text"],
            cache_path=cache_path,
        )
        fut_music = ex.submit(choose_music, theme, run_seed, q["duration"])
        bg = fut_bg.result()
        music, music_path = fut_music.result()
    media_elapsed = time.perf_counter() - t_media

    # normalisasi akhir
    q["quote_lines"] = normalize_lines(q["quote_lines"]) or ["quote hari ini"]
    q["quote_text"] = to_lower(q["quote_text"]) or " / ".join(q["quote_lines"])
    author_name = to_lower(re.sub(r"^\s*-\s*|\s*-\s*$", "", str(q["author_raw"] or "")).strip())

    plan = build_plan(day, theme, defaults, q, bg, bg_path, music, music_path)
    PLAN_OUT.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    ts = now_utc_iso()
    log_run(
        ts, day, run_seed, mode, q["source"], q["selected_id"], q["language"],
        plan["quote"], plan["author"], q["quote_lines"], plan["title"], q["duration"],
        bg, music, used_path, used_videos_path, used_music_path,
    )

    print(f"[ok] tema: {theme.get('id')} | mode: {mode} | Pixabay: {bg.get('id')} ({bg.get('user')}) | musik: {music.get('title')} ({music.get('artist','')}, {music.get('source','')})")
    print(f"[ok] quote: {plan['quote']} — {plan['author'] or '-'} (durasi {q['duration']}s)")
    print(f"[ok] rencana ditulis: {PLAN_OUT}")
    print(f"[ok] log ditambah: {used_path}, {used_videos_path}, {used_music_path}")
    print(f"[info] waktu plan: quote={quote_elapsed:.2f}s media={media_elapsed:.2f}s total={time.perf_counter()-t0:.2f}s")


if __name__ == "__main__":
    main()
