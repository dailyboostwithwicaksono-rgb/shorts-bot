"""Ambil latar video dari Pixabay Video API (keyword dari AI, filter metadata oleh kode)."""
import hashlib
import json
import os
import random
import re
import subprocess
from pathlib import Path

import requests

from ai import generate_plan

PIXABAY_API = "https://pixabay.com/api/videos/"
TARGET_W, TARGET_H = 1080, 1920


def _download(link: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(link, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        with out.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)


def _probe_duration(path: Path) -> float | None:
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True, capture_output=True, text=True, timeout=30,
        )
        val = (r.stdout or "").strip()
        return float(val) if val else None
    except Exception:
        return None


def _load_cache(cache_path: Path) -> list[dict]:
    if not cache_path or not cache_path.exists():
        return []
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("items") or data.get("cache") or []
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_cache(cache_path: Path, items: list[dict]) -> None:
    if not cache_path:
        return
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    # keep unique by id, most recent last, cap size
    seen = {}
    ordered = []
    for it in items:
        key = str(it.get("id") or it.get("pageURL") or it.get("file_url"))
        if key in seen:
            ordered[seen[key]] = it
        else:
            seen[key] = len(ordered)
            ordered.append(it)
    if len(ordered) > 200:
        ordered = ordered[-200:]
    cache_path.write_text(json.dumps({"items": ordered}, ensure_ascii=False, indent=2), encoding="utf-8")


def _fallback_keywords(lines: list[str], quote_text: str, theme: dict) -> list[str]:
    text = " ".join(lines or []) or (quote_text or "")
    # simple heuristic: pick a few alphabetic words
    words = re.findall(r"[A-Za-z]{3,}", text.lower())
    stop = {"the", "and", "for", "with", "that", "this", "from", "your", "you", "are", "but", "not", "into", "dari", "yang", "dan", "untuk", "dengan", "tidak", "akan", "ada", "kamu"}
    words = [w for w in words if w not in stop]
    if words:
        kw = " ".join(words[:3])
        return [kw] if kw else [theme.get("pixabay_query") or theme.get("pexels_query") or "inspiration"]
    return [theme.get("pixabay_query") or theme.get("pexels_query") or "inspiration"]


def generate_keywords(lines: list[str], quote_text: str, theme: dict) -> list[str]:
    prompt = (
        "Buat 1 sampai 3 kata kunci pencarian video latar (stock video) yang relevan dengan quotes berikut.\n"
        "- Gunakan bahasa Inggris.\n"
        "- Hanya kata/frasa sederhana yang menggambarkan suasana/visual (bukan nama orang, bukan kalimat).\n"
        "- Jangan mempertimbangkan atau membandingkan video; keluarkan kata kunci saja.\n\n"
        f"Quotes: {quote_text}\n"
        f"Baris: {json.dumps(lines or [], ensure_ascii=False)}\n\n"
        'Balas HANYA JSON valid: {"keywords": ["keyword 1", "keyword 2", "keyword 3"]}'
    )
    try:
        res = generate_plan(prompt, [])
        kws = res.get("keywords") or []
        if isinstance(kws, str):
            kws = [kws]
        out = []
        for k in kws:
            s = str(k or "").strip().lower()
            if s:
                out.append(s)
        if out:
            # dedupe keep order
            seen = set(); ded = []
            for k in out:
                if k not in seen:
                    seen.add(k); ded.append(k)
            return ded[:3]
    except Exception as exc:
        print(f"[warn] Gagal membuat keyword Pixabay via AI ({exc}); pakai fallback.")
    return _fallback_keywords(lines, quote_text, theme)


def _cover_scale(w: int, h: int, tw: int = TARGET_W, th: int = TARGET_H) -> float:
    if not w or not h:
        return 999.0
    return max(tw / w, th / h)


def _best_file(hit: dict) -> dict | None:
    videos = hit.get("videos") or {}
    for label in ("large", "medium", "small", "tiny"):
        v = videos.get(label)
        if v and v.get("url"):
            return {"label": label, **v}
    return None


def _search(api_key: str, query: str, per_page: int = 20) -> list[dict]:
    params = {
        "key": api_key,
        "q": query,
        "per_page": per_page,
        "safesearch": "true",
    }
    r = requests.get(PIXABAY_API, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data.get("hits") or []


def _select_from_hits(hits: list[dict], quote_duration: int, seed: str) -> dict | None:
    analyzed = []
    for h in hits:
        if (h.get("type") or "").lower() == "animation":
            continue
        f = _best_file(h)
        if not f:
            continue
        w = int(f.get("width") or 0)
        hgt = int(f.get("height") or 0)
        scale = _cover_scale(w, hgt)
        analyzed.append({
            "hit": h,
            "file": f,
            "scale": scale,
            "no_upscale": w >= TARGET_W and hgt >= TARGET_H,
            "scale_ok_12": scale <= 1.2,
            "dur_meta": int(h.get("duration") or 0),
        })

    if not analyzed:
        return None

    stages = [
        ("S1", lambda x: x["dur_meta"] >= quote_duration and x["no_upscale"]),
        ("S2", lambda x: x["dur_meta"] >= quote_duration and x["scale_ok_12"]),
        ("S3", lambda x: x["dur_meta"] >= quote_duration),
        ("S4", lambda x: x["no_upscale"]),
        ("S5", lambda x: x["scale_ok_12"]),
        ("S6", lambda x: True),
    ]

    pool = []
    chosen_stage = None
    for name, fn in stages:
        p = [x for x in analyzed if fn(x)]
        if p:
            pool = p
            chosen_stage = name
            break

    if not pool:
        return None

    # deterministic-ish random per seed+query context: shuffle with seed, pick up to 3, then random among them
    rng = random.Random(hashlib.sha256(seed.encode("utf-8")).hexdigest())
    pool_copy = list(pool)
    rng.shuffle(pool_copy)
    top = pool_copy[:3]
    pick = random.choice(top)  # final pick random (code)
    pick["_stage"] = chosen_stage
    pick["_pool_size"] = len(pool)
    return pick


def _hit_to_bginfo(hit: dict, file_info: dict, keyword: str, stage: str) -> dict:
    return {
        "id": hit.get("id"),
        "url": hit.get("pageURL") or "",
        "pageURL": hit.get("pageURL") or "",
        "photographer": hit.get("user") or "",
        "user": hit.get("user") or "",
        "description": hit.get("tags") or "",
        "tags": hit.get("tags") or "",
        "type": hit.get("type") or "",
        "duration_meta": hit.get("duration"),
        "file_url": file_info.get("url") or "",
        "file_label": file_info.get("label"),
        "width": file_info.get("width"),
        "height": file_info.get("height"),
        "source": "pixabay",
        "keyword": keyword,
        "stage": stage,
    }


def pick_background(theme: dict, seed: str, out: Path, quote_duration: int,
                    quote_lines: list[str] | None = None, quote_text: str = "",
                    cache_path: Path | None = None) -> dict:
    """Pilih & unduh latar dari Pixabay. Fallback ke cache sukses jika kosong."""
    api_key = (os.getenv("PIXABAY_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("PIXABAY_API_KEY tidak ditemukan. Set env/secret PIXABAY_API_KEY untuk mengambil latar Pixabay.")

    keywords = generate_keywords(quote_lines or [], quote_text or "", theme)
    print(f"[info] Pixabay keywords: {keywords}")

    cache_items = _load_cache(cache_path) if cache_path else []

    last_err = None
    for kw in keywords:
        try:
            hits = _search(api_key, kw, per_page=20)
            print(f"[info] Pixabay q='{kw}' hits={len(hits)}")
            sel = _select_from_hits(hits, int(quote_duration or 0), seed=f"{seed}|{kw}")
            if not sel:
                continue
            bg = _hit_to_bginfo(sel["hit"], sel["file"], kw, sel.get("_stage") or "")
            _download(bg["file_url"], out)
            # probe actual duration
            actual = _probe_duration(out)
            if actual:
                bg["duration_actual"] = round(actual, 3)
            else:
                bg["duration_actual"] = float(bg.get("duration_meta") or 0)
            # update cache
            if cache_path:
                cache_items.append({k: v for k, v in bg.items() if k != "_stage"})
                _save_cache(cache_path, cache_items)
            print(f"[ok] Pixabay dipilih: id={bg.get('id')} user={bg.get('user')} dur_meta={bg.get('duration_meta')} dur_actual={bg.get('duration_actual')} stage={sel.get('_stage')}")
            return bg
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"[warn] Pixabay gagal untuk keyword '{kw}': {exc}")

    # fallback: cache
    if cache_items:
        print("[warn] Pencarian Pixabay kosong/gagal, mencoba cache latar yang pernah berhasil...")
        rng = random.Random(hashlib.sha256((seed + "|cache").encode("utf-8")).hexdigest())
        candidates = list(cache_items)
        rng.shuffle(candidates)
        for item in candidates[:20]:
            try:
                link = item.get("file_url")
                if not link:
                    continue
                _download(link, out)
                actual = _probe_duration(out)
                bg = dict(item)
                bg["source"] = "pixabay_cache"
                if actual:
                    bg["duration_actual"] = round(actual, 3)
                elif bg.get("duration_actual") is None:
                    bg["duration_actual"] = float(bg.get("duration_meta") or 0)
                print(f"[ok] Fallback cache Pixabay: id={bg.get('id')} user={bg.get('user')}")
                return bg
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                continue

    raise SystemExit(
        "Tidak ada video Pixabay yang cocok dan cache kosong/tidak bisa dipakai. "
        f"Terakhir: {last_err}"
    )
