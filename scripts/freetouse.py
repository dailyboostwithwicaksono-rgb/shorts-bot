"""Ambil musik latar dari Freetouse Public API (non-premium, cocok untuk short motivasi)."""
import re
import urllib.parse
from pathlib import Path

from media_utils import download_file_urllib, fetch_json_urllib, seeded_rng

BASE = "https://api.freetouse.com/v3"

MOTIVATION_QUERIES = [
    "inspirational",
    "motivational",
    "calm",
    "uplifting",
    "ambient",
    "hopeful",
    "peaceful",
    "piano",
    "cinematic",
    "nature",
]

SUITABLE_KEYWORDS = {
    "calm", "peaceful", "relaxing", "soft", "slow", "ambient", "inspirational",
    "motivational", "hopeful", "uplifting", "emotional", "gentle", "soothing",
    "meditation", "piano", "cinematic", "beautiful", "warm", "dreamy", "nature",
    "atmospheric", "inspiring", "positive", "reflective", "serene", "acoustic",
    "light", "tender", "thoughtful",
}


class FreetouseError(Exception):
    """Kesalahan domain saat memilih/mengambil musik Freetouse."""


def _fetch_json(url: str, timeout: int = 30) -> dict:
    return fetch_json_urllib(url, timeout=timeout)


def _download(url: str, out: Path) -> None:
    download_file_urllib(url, out, timeout=300)


def slugify(text: str) -> str:
    s = (text or "").lower().strip()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s or "track"


def _track_page_url(title: str, artists: list[str]) -> str:
    # Best-effort; API does not provide page URL. Falls back to browse page if unknown.
    artist = artists[0] if artists else ""
    if artist and title:
        return f"https://freetouse.com/music/{slugify(artist)}/{slugify(title)}"
    return "https://freetouse.com/music"


def _extract_artists(track: dict) -> list[str]:
    names = []
    for item in (track.get("artists") or []):
        try:
            # format: [seq, {id,name}]
            if isinstance(item, list) and len(item) >= 2 and isinstance(item[1], dict):
                n = item[1].get("name")
                if n:
                    names.append(str(n))
            elif isinstance(item, dict) and item.get("name"):
                names.append(str(item.get("name")))
        except Exception:
            continue
    return names


def _extract_tags(track: dict) -> list[str]:
    out = []
    for item in (track.get("tags") or []):
        try:
            if isinstance(item, list) and len(item) >= 2:
                out.append(str(item[1]).lower())
            elif isinstance(item, str):
                out.append(item.lower())
        except Exception:
            continue
    for item in (track.get("categories") or []):
        try:
            if isinstance(item, list) and len(item) >= 2 and isinstance(item[1], dict):
                out.append(str(item[1].get("name", "")).lower())
        except Exception:
            continue
    g = track.get("genre")
    if g:
        out.append(str(g).lower())
    # unique preserve order
    seen = set(); res = []
    for x in out:
        x = x.strip()
        if x and x not in seen:
            seen.add(x); res.append(x)
    return res


def _is_suitable(track: dict, query: str) -> tuple[bool, int]:
    tags = set(_extract_tags(track))
    title = (track.get("title") or "").lower()
    score = 0
    score += len(tags & SUITABLE_KEYWORDS)
    if any(k in title for k in ["calm", "hope", "inspir", "peace", "dream", "light", "rise", "gentle", "seren"]):
        score += 1
    # came from a motivation/calm query, so accept even if tags sparse
    base_ok = query in MOTIVATION_QUERIES
    return (base_ok or score > 0), score


def _collect_candidates(min_duration: float) -> list[dict]:
    seen = set()
    candidates = []
    # try preferred queries
    for q in MOTIVATION_QUERIES:
        for offset in (0, 30):
            try:
                url = f"{BASE}/music/tracks/search?query={urllib.parse.quote(q)}&limit=30&offset={offset}"
                data = _fetch_json(url)
            except Exception:
                continue
            items = data.get("data") or []
            if not items:
                break
            for t in items:
                tid = t.get("id")
                if not tid or tid in seen:
                    continue
                dur = float(t.get("duration") or 0)
                if t.get("is_premium") is not False:
                    continue
                if int(t.get("status") or 0) != 1:
                    continue
                if not ((t.get("files") or {}).get("mp3")):
                    continue
                if dur < min_duration:
                    continue
                ok, score = _is_suitable(t, q)
                if not ok:
                    continue
                seen.add(tid)
                candidates.append({"track": t, "score": score, "query": q})
    # fallback: browse all if too few
    if len(candidates) < 5:
        for offset in range(0, 200, 50):
            try:
                data = _fetch_json(f"{BASE}/music/tracks/all?limit=50&offset={offset}")
            except Exception:
                continue
            items = data.get("data") or []
            if not items:
                break
            for t in items:
                tid = t.get("id")
                if not tid or tid in seen:
                    continue
                dur = float(t.get("duration") or 0)
                if t.get("is_premium") is not False or int(t.get("status") or 0) != 1:
                    continue
                if not ((t.get("files") or {}).get("mp3")):
                    continue
                if dur < min_duration:
                    continue
                ok, score = _is_suitable(t, "browse")
                if not ok and score <= 0:
                    # accept generic non-premium if from browse as last resort
                    score = 0
                seen.add(tid)
                candidates.append({"track": t, "score": score, "query": "browse"})
            if len(candidates) >= 40:
                break
    return candidates


def pick_music(seed: str, out: Path, target_duration: int) -> dict:
    """Pilih & unduh musik Freetouse non-premium (calm/motivasi) durasi memadai."""
    target_duration = int(target_duration or 30)
    # prefer tracks >= 60s and >= target_duration; relax if needed
    tiers = [max(60.0, float(target_duration)), float(target_duration), 30.0]
    candidates = []
    used_min = tiers[0]
    for min_d in tiers:
        used_min = min_d
        candidates = _collect_candidates(min_d)
        if candidates:
            break
    if not candidates:
        raise FreetouseError("Tidak ada musik Freetouse non-premium yang cocok ditemukan (cek koneksi internet).")

    # prefer higher suitability score, but keep randomness
    candidates.sort(key=lambda x: (-x["score"], -float(x["track"].get("duration") or 0)))
    top_n = min(30, len(candidates))
    pool = candidates[:top_n]
    rng = seeded_rng(seed, "music")
    pick = rng.choice(pool)
    t = pick["track"]

    mp3_url = ((t.get("files") or {}).get("mp3") or "")
    if not mp3_url:
        raise FreetouseError("Track Freetouse terpilih tidak memiliki file mp3.")

    _download(mp3_url, out)

    artists = _extract_artists(t)
    artist_str = ", ".join(artists) if artists else "Unknown"
    title = str(t.get("title") or "Unknown")
    page_url = _track_page_url(title, artists)
    tags = _extract_tags(t)

    meta = {
        "id": t.get("id"),
        "title": title,
        "artists": artists,
        "artist": artist_str,
        "duration": float(t.get("duration") or 0),
        "is_premium": t.get("is_premium"),
        "status": t.get("status"),
        "genre": t.get("genre"),
        "tags": tags,
        "mp3_url": mp3_url,
        "url": page_url,
        "source": "freetouse",
        "record_label": t.get("record_label"),
        "query": pick.get("query"),
        "score": pick.get("score"),
        "min_duration_filter": used_min,
        "file": out.name,
    }
    return meta
