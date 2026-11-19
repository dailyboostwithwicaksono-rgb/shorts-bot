#!/usr/bin/env python3
"""Buat rencana video quotes: list (default), famous (AI), atau custom (manual)."""
import json
import os
import random
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
DEFAULT_QUOTES = ROOT / "data" / "quotes.json"
DEFAULT_USED = ROOT / "data" / "used_quotes.jsonl"


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def pick_theme(themes: list[dict]) -> dict:
    # satu tema utama; kalau ada banyak, pilih acak per run
    if not themes:
        raise SystemExit("config/themes.json tidak memiliki themes.")
    return random.choice(themes)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_used_entries(path: Path, limit: int = 200) -> list[dict]:
    if not path.exists():
        return []
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except Exception:
            continue
    return items[-limit:]


def append_used_entry(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


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
        # jika tidak ditemukan, lewati

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


def choose_music(theme: dict) -> tuple[dict, Path]:
    music_pool = theme.get("music") or []
    if isinstance(music_pool, dict):
        music_pool = [music_pool]
    available = [m for m in music_pool if (MUSIC / str(m.get("file", ""))).exists()]
    if not available:
        raise SystemExit(
            f"Tidak ada file musik di {MUSIC}. Upload salah satu dari: "
            + ", ".join(str(m.get("file")) for m in music_pool)
        )
    music = random.choice(available)
    return music, MUSIC / music["file"]


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

    # normalisasi dasar
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
        # loop dari awal
        selected = normed[0]
        print("[info] Semua quotes sudah terpakai, loop dari awal.")

    return selected


def main() -> None:
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
    OUT_DIR = ROOT / "out"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    theme = pick_theme(cfg.get("themes") or [])
    bg_path = WORK / "bg.mp4"
    bg = pick_background(theme, run_seed, bg_path)
    music, music_path = choose_music(theme)

    mode = (os.getenv("QUOTE_MODE") or defaults.get("default_mode") or "list").strip().lower()
    if mode not in ("list", "custom", "famous"):
        mode = "list"

    quotes_path = ROOT / str(defaults.get("quotes_file") or "data/quotes.json")
    used_path = ROOT / str(defaults.get("used_quotes_file") or "data/used_quotes.jsonl")
    used = load_used_entries(used_path)

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
        prompt = build_famous_prompt(theme, bg, used)
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
        # metadata sederhana & konsisten
        if author_raw and str(author_raw).strip():
            caption = f"kutipan dari {to_lower(author_raw)}."
        else:
            caption = "sebuah kutipan untuk direnungkan."
        title = (quote_lines[0][:97] + "...") if quote_lines and len(quote_lines[0]) > 100 else (quote_lines[0] if quote_lines else "quote hari ini")
        hashtags = []

    # normalisasi akhir
    quote_lines = normalize_lines(quote_lines) or ["quote hari ini"]
    quote_text = to_lower(quote_text) or " / ".join(quote_lines)
    author_display, author_is_dash = format_author(author_raw)
    author_name = to_lower(re.sub(r"^\s*-\s*|\s*-\s*$", "", str(author_raw or "")).strip())

    # segmen emphasis (quote saja)
    quote_line_segments = compute_emphasis_segments(quote_lines, emphasis)

    # metadata umum
    hashtags = ensure_hashtags(hashtags, language)
    privacy = os.getenv("YT_PRIVACY") or privacy or "public"

    attribution = (
        f"Video latar: {bg.get('photographer', '')} / Pexels — {bg.get('url', '')}\n"
        f"Musik: {music.get('title', '')} — {music.get('url', '')} (Free To Use)"
    )
    quote_credit = f"Quote: {quote_text}" + (f" — {author_name}" if author_name else "")
    description = f"{caption}\n\n{quote_credit}\n{' '.join(hashtags)}\n\n{attribution}"

    plan = {
        "date": day,
        "theme": theme.get("id"),
        "mode": mode,
        "source": source,
        "id": selected_id,
        "language": language,
        "quote": quote_text,
        "author": author_name,
        "duration": duration,
        "lines": quote_lines + ([author_display] if author_display and not author_is_dash else (["-"] if author_is_dash else [])),
        "quote_line_segments": quote_line_segments,
        "author_display": author_display,
        "author_is_dash": author_is_dash,
        "title": title,
        "caption": caption,
        "hashtags": hashtags,
        "description": description,
        "privacy": privacy,
        "background": str(bg_path),
        "music": str(music_path),
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
        "saturation": float(defaults.get("saturation", 0.75)),
        "music_volume": float(defaults.get("music_volume", 0.28)),
        "dash_width": int(defaults.get("dash_width", 100)),
        "dash_height": int(defaults.get("dash_height", 2)),
        "quote_color": str(defaults.get("quote_color", "#FFFFFF")),
        "author_color": str(defaults.get("author_color", "#DDDDDD")),
    }
    PLAN_OUT.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    log_entry = {
        "ts": now_utc_iso(),
        "date": day,
        "mode": mode,
        "source": source,
        "id": selected_id,
        "language": language,
        "quote": quote_text,
        "author": author_name,
        "lines": quote_lines,
        "title": title,
    }
    append_used_entry(used_path, log_entry)

    print(f"[ok] tema: {theme.get('id')} | mode: {mode} | Pexels: {bg.get('id')} | musik: {music.get('title')}")
    print(f"[ok] quote: {quote_text} — {author_name or '-'} (durasi {duration}s)")
    print(f"[ok] rencana ditulis: {PLAN_OUT}")
    print(f"[ok] log ditambah: {used_path}")


if __name__ == "__main__":
    main()
