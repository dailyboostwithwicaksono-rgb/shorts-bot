#!/usr/bin/env python3
"""Local (non-GitHub) video workflow: prepare media, caption/metadata, deterministic render, archive/reset.

- prepare: resolve/download media into execution/work (seed keywords first; optional AI fallback like GitHub plan).
- caption: generate caption from caption_styles metadata when missing (AI). If provided, use as-is. May run before/after render.
- render:  deterministic, NO AI. Reads all required data from execution folder and renders video.
- archive: move execution to archive/<ts>_<label>/ and reset execution from template.
- reset:   replace execution with template (destructive, no archive).

Run from repo root: python scripts/local_workflow.py <command> [--dir local/execution]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from common import load_dotenv, read_json  # noqa: E402

load_dotenv(ROOT / ".env")

DEFAULT_EXEC_DIR = ROOT / "local" / "execution"
TEMPLATE_DIR = ROOT / "local" / "template"
ARCHIVE_DIR = ROOT / "local" / "archive"
THEMES_PATH = ROOT / "config" / "themes.json"
FONTS_DIR = ROOT / "assets" / "fonts"


def log(msg: str) -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    print(f"[warn] {msg}", flush=True)


def info(msg: str) -> None:
    print(f"[info] {msg}", flush=True)


def ok(msg: str) -> None:
    print(f"[ok] {msg}", flush=True)


def fail(msg: str) -> None:
    raise SystemExit(f"[error] {msg}")


def read_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def which_or_none(name: str) -> str | None:
    return shutil.which(name)


def find_ffmpeg(cfg: dict) -> tuple[str, str]:
    render_cfg = cfg.get("render") or {}
    ffmpeg = render_cfg.get("ffmpeg")
    ffprobe = render_cfg.get("ffprobe")
    if not ffmpeg:
        ffmpeg = which_or_none("ffmpeg")
    if not ffprobe:
        ffprobe = which_or_none("ffprobe")
    # common Windows WinGet location fallback
    winget_bin = Path(
        r"C:\Users\LENOVO\AppData\Local\Microsoft\WinGet\Packages"
        r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin"
    )
    if not ffmpeg and (winget_bin / "ffmpeg.exe").exists():
        ffmpeg = str(winget_bin / "ffmpeg.exe")
    if not ffprobe and (winget_bin / "ffprobe.exe").exists():
        ffprobe = str(winget_bin / "ffprobe.exe")
    if not ffmpeg or not Path(ffmpeg).exists():
        fail("ffmpeg tidak ditemukan. Set config.render.ffmpeg atau tambahkan ffmpeg ke PATH.")
    if not ffprobe or not Path(ffprobe).exists():
        fail("ffprobe tidak ditemukan. Set config.render.ffprobe atau tambahkan ffprobe ke PATH.")
    return str(ffmpeg), str(ffprobe)


def probe_duration(ffprobe: str, path: Path) -> float | None:
    try:
        r = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            check=True, capture_output=True, text=True, timeout=30,
        )
        val = float((r.stdout or "").strip() or 0)
        return val if val > 0 else None
    except Exception:
        return None


def ffprobe_json(ffprobe: str, path: Path) -> dict:
    r = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        check=True, capture_output=True, text=True, timeout=60,
    )
    return json.loads(r.stdout or "{}")


def resolve_exec_path(exec_dir: Path, p: str | None) -> Path | None:
    if not p:
        return None
    pp = Path(p)
    if pp.is_absolute():
        return pp
    return (exec_dir / pp).resolve()


def load_theme_defaults() -> dict:
    if not THEMES_PATH.exists():
        return {}
    try:
        return (read_json(THEMES_PATH) or {}).get("defaults") or {}
    except Exception:
        return {}


# ---------- text / image rendering (deterministic) ----------

def font_path(name: str) -> str:
    p = FONTS_DIR / name
    if not p.exists():
        fail(f"Font tidak ditemukan: {p}")
    return str(p)


def hex_to_rgb(v: str | None) -> tuple[int, int, int]:
    s = (v or "#FFFFFF").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> float:
    if not text:
        return 0.0
    try:
        return float(draw.textlength(text, font=font))
    except Exception:
        b = draw.textbbox((0, 0), text, font=font)
        return float(b[2] - b[0])


def normalize_line(line: Any) -> list[dict]:
    """Line -> list of {text, emphasis} parts. Accepts [[{text,emphasis},...]] or [str,...] or str."""
    if isinstance(line, str):
        return [{"text": line, "emphasis": False}] if line else []
    if isinstance(line, list):
        parts: list[dict] = []
        for item in line:
            if isinstance(item, str):
                if item:
                    parts.append({"text": item, "emphasis": False})
            elif isinstance(item, dict):
                txt = str(item.get("text", ""))
                if txt:
                    parts.append({"text": txt, "emphasis": bool(item.get("emphasis"))})
        return parts or []
    return []


def line_plain_text(parts: list[dict]) -> str:
    return "".join(p.get("text", "") for p in parts)


def segs_for_plain(text: str, emphasis_phrases: list[str] | None = None) -> list[dict]:
    phrases = [e for e in (emphasis_phrases or []) if e and e in text]
    if not phrases:
        return [{"text": text, "emphasis": False}] if text else []
    used = [False] * len(text)
    spans: list[tuple[int, int]] = []
    for ph in phrases:
        i = text.find(ph)
        while i != -1:
            if not any(used[i:i + len(ph)]):
                for k in range(i, i + len(ph)):
                    used[k] = True
                spans.append((i, i + len(ph)))
                break
            i = text.find(ph, i + 1)
    spans.sort()
    out: list[dict] = []
    pos = 0
    for s, e in spans:
        if s > pos:
            out.append({"text": text[pos:s], "emphasis": False})
        out.append({"text": text[s:e], "emphasis": True})
        pos = e
    if pos < len(text):
        out.append({"text": text[pos:], "emphasis": False})
    return out or [{"text": text, "emphasis": False}]


def measure_parts(parts: list[dict], size: int) -> float:
    img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    qf = ImageFont.truetype(font_path("Montserrat-LightItalic.ttf"), size)
    ef = ImageFont.truetype(font_path("Montserrat-SemiBoldItalic.ttf"), size)
    total = 0.0
    for p in parts:
        f = ef if p.get("emphasis") else qf
        total += text_width(d, p.get("text", ""), f)
    return total


def fit_size(parts: list[dict], base: int, max_w: int) -> int:
    size = int(base)
    while size > 20 and measure_parts(parts, size) > max_w:
        size -= 2
    return size


def render_text_block(lines_parts: list[list[dict]], author_text: str | None, y_center: int,
                      out_path: Path, style: dict, w: int, h: int) -> None:
    q_size = int(style.get("quote_font_size", 51))
    a_size = int(style.get("author_font_size", 28))
    max_w = int(style.get("max_text_width", 920))
    spacing = float(style.get("line_spacing", 1.3))
    q_color = hex_to_rgb(style.get("quote_color", "#FFFFFF"))
    a_color = hex_to_rgb(style.get("author_color", "#DDDDDD"))
    line_h = max(1, int(round(q_size * spacing)))
    has_author = bool(author_text)

    total_h = q_size + (len(lines_parts) - 1) * line_h if lines_parts else 0
    gap = int(round(line_h * 0.9))
    if has_author and lines_parts:
        total_h += gap + a_size
    elif has_author:
        total_h = a_size
    top = int(round(y_center - total_h / 2))

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    y = top + q_size // 2
    for parts in lines_parts:
        size = fit_size(parts, q_size, max_w)
        qf = ImageFont.truetype(font_path("Montserrat-LightItalic.ttf"), size)
        ef = ImageFont.truetype(font_path("Montserrat-SemiBoldItalic.ttf"), size)
        tw = measure_parts(parts, size)
        x = (w - tw) / 2.0
        bbox = draw.textbbox((0, 0), "Ag", font=qf)
        th = bbox[3] - bbox[1]
        yy = int(round(y - th / 2))
        for part in parts:
            txt = part.get("text", "")
            if not txt:
                continue
            f = ef if part.get("emphasis") else qf
            draw.text((x, yy), txt, font=f, fill=(*q_color, 255))
            x += text_width(draw, txt, f)
        y += line_h

    if has_author:
        if lines_parts:
            ay = top + q_size + (len(lines_parts) - 1) * line_h + gap + a_size // 2
        else:
            ay = top + a_size // 2
        sz = a_size
        af = ImageFont.truetype(font_path("Montserrat-Italic.ttf"), sz)
        tw = text_width(draw, author_text or "", af)
        while sz > 14 and tw > max_w:
            sz -= 1
            af = ImageFont.truetype(font_path("Montserrat-Italic.ttf"), sz)
            tw = text_width(draw, author_text or "", af)
        bbox = draw.textbbox((0, 0), (author_text or "Ag"), font=af)
        th = bbox[3] - bbox[1]
        draw.text(((w - tw) / 2.0, int(round(ay - th / 2))), author_text or "", font=af, fill=(*a_color, 255))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def render_band(style: dict, out_path: Path, w: int, h: int) -> None:
    band_top = int(style.get("band_top", 560))
    band_h = int(style.get("band_height", 800))
    band_opacity = float(style.get("overlay_opacity", 0.55))
    feather = max(0, int(style.get("band_feather", 140)))
    feather = min(feather, band_h // 2) if band_h > 0 else 0
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if band_h > 0:
        max_a = int(round(max(0.0, min(1.0, band_opacity)) * 255))
        px = img.load()
        y0 = max(0, band_top)
        y1 = min(h, band_top + band_h)
        for y in range(y0, y1):
            dt = y - band_top
            db = (band_top + band_h - 1) - y
            d = min(dt, db)
            a = int(round(max_a * (d + 1) / feather)) if feather > 0 and d < feather else max_a
            if a <= 0:
                continue
            for x in range(w):
                px[x, y] = (0, 0, 0, a)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


# ---------- render (deterministic, no AI) ----------

def cmd_render(exec_dir: Path) -> None:
    for name in ["quote.json", "transcript.json", "config.json", "youtube.json"]:
        if not (exec_dir / name).exists():
            fail(f"File wajib tidak ditemukan: {exec_dir / name}")

    quote = read_json_file(exec_dir / "quote.json")
    transcript = read_json_file(exec_dir / "transcript.json")
    cfg = read_json_file(exec_dir / "config.json")
    yt = read_json_file(exec_dir / "youtube.json")

    theme = load_theme_defaults()
    style = dict(theme)
    ffmpeg, ffprobe = find_ffmpeg(cfg)

    rcfg = cfg.get("render") or {}
    W = int(rcfg.get("width", 1080))
    H = int(rcfg.get("height", 1920))
    fps = int(rcfg.get("fps", 30))
    crf = int(rcfg.get("crf", 20))
    preset = str(rcfg.get("preset", "medium"))
    abitrate = str(rcfg.get("audio_bitrate", "192k"))

    vcfg = cfg.get("visual") or {}
    acfg = cfg.get("audio") or {}
    paths_cfg = cfg.get("paths") or {}

    vo_path = resolve_exec_path(exec_dir, transcript.get("voiceover_file") or paths_cfg.get("voiceover") or "vo/vo.mp3")
    if not vo_path or not vo_path.exists():
        fail(f"File VO tidak ditemukan: {vo_path}")
    vo_dur = probe_duration(ffprobe, vo_path)
    if not vo_dur:
        fail(f"Tidak bisa membaca durasi VO: {vo_path}")
    info(f"VO: {vo_path} ({vo_dur:.3f}s)")

    intro = float(transcript.get("intro_backsound_seconds", 1.0) or 0.0)
    if intro < 0:
        intro = 0.0

    segs_in = transcript.get("segments") or []
    if not isinstance(segs_in, list) or not segs_in:
        fail("transcript.segments kosong atau tidak valid")
    segments: list[dict] = []
    for s in segs_in:
        st = float(s.get("start", 0.0))
        en = float(s.get("end", st))
        if en <= st:
            continue
        raw_lines = s.get("lines") or []
        lines_parts = [normalize_line(ln) for ln in raw_lines]
        lines_parts = [lp for lp in lines_parts if lp]
        segments.append({
            "start": st,
            "end": en,
            "d_start": st + intro,
            "d_end": en + intro,
            "lines_parts": lines_parts,
            "author": s.get("author"),
            "video_keyword": str(s.get("video_keyword") or "").strip(),
            "raw_lines": raw_lines,
        })
    if not segments:
        fail("Tidak ada segmen narasi valid di transcript.json")

    card_cfg = transcript.get("card") or {}
    card_enabled = bool(card_cfg.get("enabled", True))
    card_start = vo_dur + intro + float(card_cfg.get("start_offset_after_vo", 0.4)) if card_enabled else (vo_dur + intro)
    card_fi = float(card_cfg.get("fade_in", 0.6))
    card_hold = float(card_cfg.get("hold", 3.0))
    card_fo = float(card_cfg.get("fade_out", 0.6))
    tail = float(card_cfg.get("tail", 1.0))
    card_end = card_start + card_fi + card_hold + card_fo if card_enabled else (vo_dur + intro)
    total_dur = round(card_end + tail + 0.01, 2) if card_enabled else round(vo_dur + intro + tail + 0.01, 2)
    info(f"Timeline: intro={intro:.2f}s vo={vo_dur:.2f}s card={card_start:.2f}-{card_end:.2f}s total={total_dur:.2f}s")

    media = cfg.get("media") or {}
    bg_cfg = media.get("backgrounds") or {}
    music_cfg = media.get("music") or {}
    bg_mode_cfg = str(bg_cfg.get("mode") or "legacy").lower()
    bg_count = int(vcfg.get("background_count", bg_cfg.get("count", 3)) or 3)
    resolved_bgs = bg_cfg.get("resolved_files") or []
    bg_paths: list[Path] = []
    bg_slice = resolved_bgs if bg_mode_cfg == "per_segment" else resolved_bgs[:bg_count]
    for p in bg_slice:
        rp = resolve_exec_path(exec_dir, str(p))
        if rp and rp.exists():
            bg_paths.append(rp)
    if not bg_paths:
        fail("Tidak ada background resolved. Jalankan 'prepare' atau isi config.media.backgrounds.resolved_files di folder eksekusi.")
    info(f"Backgrounds: {len(bg_paths)} file")

    music_path = resolve_exec_path(exec_dir, music_cfg.get("resolved_file") or (paths_cfg.get("work_dir", "work") + "/music.mp3"))
    if not music_path or not music_path.exists():
        fail(f"File musik tidak ditemukan: {music_path}. Jalankan 'prepare' atau isi config.media.music.resolved_file.")
    info(f"Music: {music_path}")

    out_dir = resolve_exec_path(exec_dir, paths_cfg.get("out_dir", "out")) or (exec_dir / "out")
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="localrender-", dir=str(out_dir)))

    try:
        # overlays
        band_png = tmp / "band.png"
        render_band(style, band_png, W, H)

        text_fade = float(transcript.get("text_fade_seconds", 0.35))
        text_inputs: list[dict] = []
        for i, seg in enumerate(segments):
            png = tmp / f"seg_{i:03d}.png"
            render_text_block(seg["lines_parts"], seg.get("author"), 960, png, style, W, H)
            st = max(0.0, float(seg.get("d_start", seg["start"])))
            en = min(total_dur, float(seg.get("d_end", seg["end"])))
            text_inputs.append({"png": str(png), "start": st, "end": en, "fi": text_fade, "fo": text_fade})

        card_png = tmp / "card.png"
        card_lines_parts: list[list[dict]] = []
        card_author = ""
        if card_enabled:
            q_lines = quote.get("lines") or []
            emph = quote.get("emphasis") or []
            for ln in q_lines:
                card_lines_parts.append(segs_for_plain(str(ln), emph))
            qa = str(quote.get("author") or "").strip()
            card_author = f"- {qa.lower()} -" if qa else ""
            card_style = {**style, "author_font_size": int(style.get("author_font_size", 28)) * 2}
            render_text_block(card_lines_parts, card_author or None, 960, card_png, card_style, W, H)
        else:
            Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(card_png)

        # pass 1: bg_base
        slowdown = float(vcfg.get("slowdown", 1.3))
        xfade = float(vcfg.get("xfade_duration", 0.5))
        brightness = float(vcfg.get("brightness", -0.1))
        saturation = float(vcfg.get("saturation", 0.0))
        contrast = float(vcfg.get("contrast", 1.05))
        darken = float(vcfg.get("darken", 0.32))

        bg_mode = str(bg_cfg.get("mode") or "legacy").lower()
        nseg = len(segments)
        if bg_mode == "per_segment" and nseg >= 1:
            # titik ganti klip: segmen 0 selalu mulai klip baru; segmen 1..nseg-2 mulai klip baru
            # kecuali video_keyword="keep/continue/same/hold" (lanjutkan klip sebelumnya). Segmen terakhir selalu lanjut.
            change_points = [0]
            if nseg > 2:
                for i in range(1, nseg - 1):
                    if not is_video_keep(segments[i]):
                        change_points.append(i)
            clip_count = len(change_points)
            boundaries = [0.0]
            for j in range(1, clip_count):
                si = change_points[j]
                boundaries.append(max(0.0, float(segments[si].get("d_start", segments[si]["start"]))))
            boundaries.append(float(total_dur))
            for i in range(1, len(boundaries)):
                if boundaries[i] <= boundaries[i - 1] + 0.05:
                    boundaries[i] = boundaries[i - 1] + 0.05
            if boundaries[-1] < total_dur:
                boundaries[-1] = float(total_dur)
            if len(bg_paths) < clip_count:
                fail(f"Background per-segment kurang: butuh {clip_count} klip, tersedia {len(bg_paths)}. Jalankan 'prepare'.")
            clip_paths = list(bg_paths[:clip_count])
        else:
            clip_count = len(bg_paths)
            clip_paths = list(bg_paths)
            boundaries = None

        bg_base = tmp / "bg_base.mp4"
        cmd1 = [ffmpeg, "-y", "-v", "error", "-stats"]
        for b in clip_paths:
            cmd1 += ["-stream_loop", "-1", "-i", str(b)]
        fc1: list[str] = []
        for i in range(clip_count):
            trim_src = total_dur / max(0.1, slowdown) + 2
            fc1.append(
                f"[{i}:v]setpts={slowdown}*PTS,trim=duration={trim_src:.3f},setpts=PTS-STARTPTS,"
                f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps},setsar=1,"
                f"eq=brightness={brightness}:saturation={saturation}:contrast={contrast},"
                f"drawbox=x=0:y=0:w={W}:h={H}:color=black@{darken}:t=fill[b{i}]"
            )
        if bg_mode == "per_segment" and boundaries is not None:
            m = clip_count
            x = float(xfade)
            if m > 1:
                min_seg = min((boundaries[i + 1] - boundaries[i]) for i in range(m))
                x = min(x, max(0.0, min_seg - 0.05))
            else:
                x = 0.0
            for i in range(m):
                seg_dur = boundaries[i + 1] - boundaries[i]
                extra_in = x if i > 0 else 0.0
                extra_out = x if i < m - 1 else 0.0
                td = max(0.1, seg_dur + extra_in + extra_out)
                fc1.append(f"[b{i}]trim=duration={td:.3f},setpts=PTS-STARTPTS[bs{i}]")
            if m == 1:
                fc1.append(f"[bs0]trim=duration={total_dur:.3f},setpts=PTS-STARTPTS[bgx2]")
                bg_label = "bgx2"
            else:
                prev = "bs0"
                for i in range(1, m):
                    out_label = "bgx2" if i == m - 1 else f"bx{i}"
                    offset = max(0.0, boundaries[i] - x)
                    fc1.append(f"[{prev}][bs{i}]xfade=transition=fade:duration={x:.3f}:offset={offset:.3f}[{out_label}]")
                    prev = out_label
                fc1.append(f"[bgx2]trim=duration={total_dur:.3f},setpts=PTS-STARTPTS[bgx]")
                bg_label = "bgx"
        else:
            # legacy: distribusi merata
            nbg = clip_count
            seg_len = (total_dur + xfade * (nbg - 1)) / nbg if nbg else total_dur
            for i in range(nbg):
                fc1.append(f"[b{i}]trim=duration={seg_len:.3f},setpts=PTS-STARTPTS[bs{i}]")
            if nbg == 1:
                fc1.append(f"[bs0]trim=duration={total_dur:.3f},setpts=PTS-STARTPTS[bgx]")
                bg_label = "bgx"
            else:
                prev = "bs0"
                cum = seg_len
                for i in range(1, nbg):
                    out_label = "bgx" if i == nbg - 1 else f"bx{i}"
                    offset = cum - xfade
                    fc1.append(f"[{prev}][bs{i}]xfade=transition=fade:duration={xfade}:offset={offset:.3f}[{out_label}]")
                    prev = out_label
                    cum = offset + seg_len
                fc1.append(f"[bgx]trim=duration={total_dur:.3f},setpts=PTS-STARTPTS[bgx2]")
                bg_label = "bgx2"
        cmd1 += [
            "-filter_complex", ";".join(fc1),
            "-map", f"[{bg_label}]",
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-r", str(fps),
            "-t", f"{total_dur:.3f}", str(bg_base),
        ]
        info(f"pass 1: rendering background ({'per-segment' if bg_mode == 'per_segment' and boundaries is not None else 'legacy'}, {clip_count} klip)...")
        subprocess.run(cmd1, check=True)

        # pass 2: overlays + audio
        cmd2 = [ffmpeg, "-y", "-v", "error", "-stats",
                "-i", str(bg_base), "-i", str(vo_path), "-i", str(music_path),
                "-loop", "1", "-t", str(total_dur), "-i", str(band_png)]
        text_start = 4
        for ti in text_inputs:
            cmd2 += ["-loop", "1", "-t", str(total_dur), "-i", ti["png"]]
        card_in = text_start + len(text_inputs)
        cmd2 += ["-loop", "1", "-t", str(total_dur), "-i", str(card_png)]

        fc2: list[str] = []
        fc2.append("[3:v]format=rgba[band]")
        fc2.append("[0:v][band]overlay=0:0:format=auto[v0]")
        cur = "v0"
        for idx, ti in enumerate(text_inputs):
            st = ti["start"]; en = ti["end"]
            fi = min(ti["fi"], max(0.1, (en - st) / 2))
            fo = min(ti["fo"], max(0.1, (en - st) / 2))
            fo_st = max(st + fi, en - fo)
            fc2.append(
                f"[{text_start + idx}:v]format=rgba,"
                f"fade=t=in:st={st:.3f}:d={fi:.3f}:alpha=1,"
                f"fade=t=out:st={fo_st:.3f}:d={fo:.3f}:alpha=1[t{idx}]"
            )
            out_l = f"v{idx + 1}"
            fc2.append(f"[{cur}][t{idx}]overlay=0:0:format=auto:enable='between(t,{st:.3f},{en:.3f})'[{out_l}]")
            cur = out_l

        if card_enabled:
            cst = card_start
            c_hold_end = cst + card_fi + card_hold
            fc2.append(
                f"[{card_in}:v]format=rgba,"
                f"fade=t=in:st={cst:.3f}:d={card_fi:.3f}:alpha=1,"
                f"fade=t=out:st={c_hold_end:.3f}:d={card_fo:.3f}:alpha=1[tcard]"
            )
            fc2.append(f"[{cur}][tcard]overlay=0:0:format=auto:enable='between(t,{cst:.3f},{card_end:.3f})'[vout]")
        else:
            fc2.append(f"[{cur}]null[vout]")

        narr_vol = float(acfg.get("narration_music_volume", 0.1))
        card_vol = float(acfg.get("card_music_volume", 0.26))
        mfade = float(acfg.get("music_fade_out", 1.5))
        t1 = intro + vo_dur - 0.3
        t2 = card_start + 0.4 if card_enabled else intro + vo_dur + 0.4
        denom = max(0.01, t2 - t1)
        music_expr = (
            f"if(lt(t,{t1:.3f}),{narr_vol},"
            f"if(lt(t,{t2:.3f}),{narr_vol}+({card_vol - narr_vol:.3f}*(t-{t1:.3f})/{denom:.3f}),{card_vol}))"
        )
        fc2.append(
            f"[2:a]atrim=duration={total_dur:.3f},asetpts=PTS-STARTPTS,"
            f"volume='{music_expr}',afade=t=out:st={max(0, total_dur - mfade):.3f}:d={mfade:.3f}[bgm]"
        )
        delay_ms = max(0, int(round(intro * 1000)))
        if delay_ms > 0:
            vo_chain = f"[1:a]adelay={delay_ms}:all=1,apad,atrim=duration={total_dur:.3f}[voa]"
        else:
            vo_chain = f"[1:a]atrim=duration={total_dur:.3f},asetpts=PTS-STARTPTS,apad,atrim=duration={total_dur:.3f}[voa]"
        fc2.append(vo_chain)
        fc2.append("[voa][bgm]amix=inputs=2:duration=first:dropout_transition=2,alimiter=limit=0.95[aout]")

        final_path = out_dir / "final.mp4"
        cmd2 += [
            "-filter_complex", ";".join(fc2),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-r", str(fps),
            "-c:a", "aac", "-b:a", abitrate,
            "-movflags", "+faststart",
            "-t", f"{total_dur:.3f}", str(final_path),
        ]
        info("pass 2: overlay and mix...")
        subprocess.run(cmd2, check=True)

        # verify
        probe = ffprobe_json(ffprobe, final_path)
        fmt = probe.get("format") or {}
        vstream = next((s for s in (probe.get("streams") or []) if s.get("codec_type") == "video"), {})
        out_dur = float(fmt.get("duration") or 0)
        out_size = int(fmt.get("size") or final_path.stat().st_size)

        # outputs / metadata (publish-compatible)
        hashtags = yt.get("hashtags") or []
        tags = yt.get("tags") or hashtags
        title = str(yt.get("title") or "").strip()
        description = str(yt.get("description") or "").strip()
        caption = str(yt.get("caption") or description or "").strip()
        privacy = str(yt.get("privacy") or "private")

        (out_dir / "caption.txt").write_text(caption + "\n", encoding="utf-8")
        (out_dir / "description.txt").write_text(description + "\n", encoding="utf-8")

        manifest = {
            "file": "final.mp4",
            "title": title,
            "caption": caption,
            "description": description,
            "hashtags": hashtags,
            "tags": tags,
            "privacy": privacy,
            "duration": round(out_dur, 2),
            "width": vstream.get("width", W),
            "height": vstream.get("height", H),
            "size_bytes": out_size,
            "mode": "local_vo",
            "quote_id": quote.get("id"),
            "author": quote.get("author"),
            "language": quote.get("language"),
            "voiceover": str(vo_path),
            "voiceover_duration": vo_dur,
            "timing": {
                "intro_backsound_seconds": intro,
                "total": total_dur,
                "card_start": card_start if card_enabled else None,
                "card_end": card_end if card_enabled else None,
            },
            "backgrounds": [str(p) for p in clip_paths],
            "background_mode": bg_mode,
            "music": music_cfg,
            "youtube": {
                "categoryId": yt.get("categoryId"),
                "defaultLanguage": yt.get("defaultLanguage"),
                "defaultAudioLanguage": yt.get("defaultAudioLanguage"),
                "madeForKids": bool(yt.get("madeForKids", False)),
            },
        }
        write_json_file(out_dir / "manifest.json", manifest)

        render_info = {
            "quote": quote,
            "intro_backsound_seconds": intro,
            "transcript_segments": [
                {
                    "start": s["start"],
                    "end": s["end"],
                    "display_start": s.get("d_start", s["start"]),
                    "display_end": s.get("d_end", s["end"]),
                    "author": s.get("author"),
                    "video_keyword": s.get("video_keyword", ""),
                }
                for s in segments
            ],
            "card": card_cfg,
            "timeline": manifest["timing"],
            "background_mode": bg_mode,
            "backgrounds": manifest["backgrounds"],
            "music": music_cfg,
            "output": {"file": str(final_path), "duration": round(out_dur, 3), "size_bytes": out_size},
            "tmp_dir": str(tmp),
        }
        write_json_file(out_dir / "render_info.json", render_info)

        ok(f"Render selesai: {final_path} ({out_dur:.2f}s, {out_size} bytes)")
        info(f"Output: {out_dir / 'manifest.json'}, {out_dir / 'caption.txt'}, {out_dir / 'description.txt'}")
        info(f"Intermediate disimpan: {tmp}")
    except subprocess.CalledProcessError as e:
        fail(f"ffmpeg gagal (exit {e.returncode}). Cek log di atas. Intermediate: {tmp}")
    except Exception:
        warn(f"Terjadi error. Intermediate disimpan: {tmp}")
        raise


# ---------- prepare (may use AI/API like GitHub plan for media resolution) ----------

def segment_emphasis_texts(segment: dict) -> list[str]:
    texts: list[str] = []
    for ln in (segment.get("raw_lines") or segment.get("lines") or []):
        for part in normalize_line(ln):
            if part.get("emphasis"):
                t = str(part.get("text") or "").strip()
                if t:
                    texts.append(t)
    seen: set[str] = set()
    out: list[str] = []
    for t in texts:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            out.append(t)
    return out


def segment_plain_text(segment: dict) -> str:
    parts: list[str] = []
    for ln in (segment.get("raw_lines") or segment.get("lines") or []):
        line_parts = normalize_line(ln)
        txt = line_plain_text(line_parts).strip()
        if txt:
            parts.append(txt)
    return " ".join(parts).strip()


def is_video_keep(seg: dict) -> bool:
    """True jika segmen meminta melanjutkan video/klip segmen sebelumnya (tanpa ganti)."""
    v = str(seg.get("video_keyword") or "").strip().lower()
    return v in {"keep", "continue", "same", "hold"}


def ai_english_video_keyword(source_text: str, purpose: str, quote: dict) -> str:
    """Minta AI menghasilkan 1 keyword pencarian video Pixabay dalam Bahasa Inggris."""
    try:
        from ai import generate_plan  # noqa: E402
    except Exception:
        return ""
    lang = str(quote.get("language") or "")
    prompt = f"""Buat 1 keyword pencarian video stok Pixabay dalam BAHASA INGGRIS (2-5 kata), relevan secara visual, tenang/sinematik.

Tujuan: {purpose}
Teks sumber: {source_text}
Konteks bahasa konten: {lang}

Balas HANYA JSON valid: {{"keyword": "english keyword phrase"}}"""
    try:
        res = generate_plan(prompt, [])
        kw = str((res or {}).get("keyword") or "").strip()
        return " ".join(kw.split())[:80]
    except Exception:
        return ""


def cmd_prepare(exec_dir: Path) -> None:
    for name in ["config.json", "quote.json"]:
        if not (exec_dir / name).exists():
            fail(f"File wajib tidak ditemukan: {exec_dir / name}")

    cfg = read_json_file(exec_dir / "config.json")
    quote = read_json_file(exec_dir / "quote.json")
    media = cfg.setdefault("media", {})
    work_dir = resolve_exec_path(exec_dir, (cfg.get("paths") or {}).get("work_dir", "work")) or (exec_dir / "work")
    work_dir.mkdir(parents=True, exist_ok=True)

    changed = False

    # --- backgrounds (Pixabay) ---
    bg_cfg = media.setdefault("backgrounds", {})
    if (bg_cfg.get("source") or "pixabay") == "pixabay":
        bg_mode = str(bg_cfg.get("mode") or "legacy").lower()
        seeds = [str(s).strip() for s in (bg_cfg.get("seed_keywords") or []) if str(s).strip()]

        def rel_to_exec(p: Path) -> str:
            try:
                return str(p.resolve().relative_to(exec_dir.resolve())).replace("\\", "/")
            except Exception:
                return str(p)

        def download_bg_for_keyword(api_key: str, kw: str, out_path: Path, used_ids: set,
                                    label: str, ffprobe: str, seed_key: str) -> dict | None:
            from media_utils import download_file_requests, seeded_rng  # noqa: E402
            from pixabay import _search, _hit_to_bginfo  # noqa: E402
            kw = str(kw or "").strip()
            if not kw:
                return None
            try:
                hits = _search(api_key, kw, per_page=40)
            except Exception as e:
                warn(f"Pixabay search gagal ({label}) '{kw}': {e}")
                return None
            analyzed = []
            for h in hits:
                hid = h.get("id")
                if hid in used_ids:
                    continue
                if (h.get("type") or "").lower() == "animation":
                    continue
                videos = h.get("videos") or {}
                vf = None
                for q in ("large", "medium", "small", "tiny"):
                    v = videos.get(q)
                    if v and v.get("url"):
                        vf = {"label": q, **v}
                        break
                if not vf:
                    continue
                vw = int(vf.get("width") or 0); vh = int(vf.get("height") or 0)
                if vw <= 0 or vh <= 0:
                    continue
                scale = max(1080 / vw, 1920 / vh)
                analyzed.append({"hit": h, "file": vf, "dur": int(h.get("duration") or 0), "scale": scale})
            for cond in [
                lambda x: x["dur"] >= 10 and x["scale"] <= 1.3,
                lambda x: x["dur"] >= 8 and x["scale"] <= 1.6,
                lambda x: x["dur"] >= 6,
                lambda x: True,
            ]:
                pool = [x for x in analyzed if cond(x)]
                if not pool:
                    continue
                rng = seeded_rng(seed_key, f"{kw}|{label}")
                rng.shuffle(pool)
                pick = pool[0]
                bg = _hit_to_bginfo(pick["hit"], pick["file"], kw, label)
                try:
                    download_file_requests(bg["file_url"], out_path, timeout=300)
                    bg["local"] = str(out_path)
                    bg["duration_actual"] = probe_duration(ffprobe, out_path) or float(bg.get("duration_meta") or 0)
                    used_ids.add(bg["id"])
                    return bg
                except Exception as e:
                    warn(f"Download bg gagal id={bg.get('id')}: {e}")
                    continue
            return None

        if bg_mode == "per_segment":
            if not (exec_dir / "transcript.json").exists():
                fail("mode backgrounds per_segment membutuhkan transcript.json di folder eksekusi.")
            transcript = read_json_file(exec_dir / "transcript.json")
            segs = transcript.get("segments") or []
            if not isinstance(segs, list) or not segs:
                fail("transcript.segments kosong/tidak valid untuk mode per_segment.")
            change_points = [0]
            if len(segs) > 2:
                for i in range(1, len(segs) - 1):
                    if not is_video_keep(segs[i] if isinstance(segs[i], dict) else {}):
                        change_points.append(i)
            clip_count = len(change_points)
            info(f"Mode per-segment: {len(segs)} segmen teks -> {clip_count} klip background (titik ganti: segmen {[i + 1 for i in change_points]}; 'keep'/'continue'/'same' = lanjut klip sebelumnya; segmen terakhir selalu lanjut).")

            resolved = bg_cfg.get("resolved_files") or []
            resolved_paths = [resolve_exec_path(exec_dir, p) for p in resolved]
            if len(resolved_paths) >= clip_count and all(p and p.exists() for p in resolved_paths[:clip_count]):
                ok(f"Backgrounds per-segment sudah resolved ({clip_count} file)")
            else:
                api_key = (os.getenv("PIXABAY_API_KEY") or "").strip()
                if not api_key:
                    fail("PIXABAY_API_KEY tidak ditemukan (env/.env). Dibutuhkan untuk resolve background Pixabay.")
                ffprobe = find_ffmpeg(cfg)[1]
                allow_ai = bool(bg_cfg.get("allow_ai_keywords_fallback", True))
                used_ids: set = set()
                rel_files: list[str] = []
                fallback_pool = seeds[:] or ["cinematic inspiration bokeh", "calm nature", "cinematic bokeh"]

                for slot, seg_idx in enumerate(change_points):
                    seg = segs[seg_idx] if seg_idx < len(segs) and isinstance(segs[seg_idx], dict) else {}
                    seg_text = segment_plain_text(seg)
                    emph = segment_emphasis_texts(seg)
                    manual_kw = str(seg.get("video_keyword") or "").strip()
                    if is_video_keep(seg):
                        manual_kw = ""  # segmen 0 tidak boleh keep; jaga-jaga

                    candidates: list[tuple[str, str]] = []  # (keyword, label)
                    if manual_kw:
                        # prioritas utama: frasa spesifik video_keyword -> AI terjemahkan/cari keyword visual EN
                        if allow_ai:
                            kw_m = ai_english_video_keyword(
                                manual_kw,
                                "terjemahkan dan utamakan frasa spesifik video_keyword ini menjadi 1 keyword visual video stok (Bahasa Inggris, 2-5 kata); ini instruksi visual spesifik yang diprioritaskan di atas tafsir transkrip",
                                quote,
                            )
                            if kw_m:
                                candidates.append((kw_m, "video_keyword-ai"))
                        # fallback: pakai teks asli jika AI tidak tersedia/gagal
                        if not candidates:
                            candidates.append((manual_kw, "video_keyword-raw"))
                    elif emph and allow_ai:
                        kw_e = ai_english_video_keyword(
                            "; ".join(emph),
                            "terjemahkan/ubah frasa emphasis menjadi keyword visual video stok (Bahasa Inggris)",
                            quote,
                        )
                        if kw_e:
                            candidates.append((kw_e, "emphasis-ai"))
                    elif emph:
                        # tanpa AI, pakai emphasis mentah (best-effort) lalu fallback pool
                        candidates.append((" ".join(emph)[:80], "emphasis-raw"))

                    if not manual_kw and allow_ai:
                        # langkah 3: tafsir AI dari transkrip segmen (jika belum ter-cover / sebagai fallback bermakna)
                        if seg_text:
                            kw_t = ai_english_video_keyword(
                                seg_text,
                                "tafsirkan makna/visual segmen narasi menjadi keyword visual video stok (Bahasa Inggris)",
                                quote,
                            )
                            if kw_t and all(kw_t.lower() != c[0].lower() for c in candidates):
                                candidates.append((kw_t, "segment-ai"))

                    # fallback global seeds hanya jika tidak ada keyword sama sekali (manual/emphasis/tafsir)
                    if not candidates:
                        for sk in fallback_pool:
                            candidates.append((sk, "seed"))

                    out_path = work_dir / f"seg_bg_{slot + 1}.mp4"
                    if out_path.exists() and out_path.stat().st_size > 0:
                        ok(f"Klip {slot + 1}/{clip_count} (segmen {seg_idx + 1}): seg_bg_{slot + 1}.mp4 sudah ada, lewati unduh (resume).")
                        rel_files.append(rel_to_exec(out_path))
                        continue

                    info(f"Klip {slot + 1}/{clip_count} (segmen {seg_idx + 1}): keyword candidates = {[c[0] for c in candidates[:4]]}{' ...' if len(candidates) > 4 else ''}")
                    bg = None
                    for kw, label in candidates:
                        bg = download_bg_for_keyword(api_key, kw, out_path, used_ids, label, ffprobe, str(quote.get("id") or "local"))
                        if bg:
                            ok(f"seg_bg_{slot + 1} id={bg.get('id')} kw='{kw}' ({label}) -> {out_path.name}")
                            break
                    if not bg:
                        fail(f"Gagal menyiapkan background untuk klip {slot + 1} (segmen {seg_idx + 1}). Coba isi video_keyword (EN) manual atau ubah seed_keywords/cek koneksi.")
                    rel_files.append(rel_to_exec(out_path))

                bg_cfg["resolved_files"] = rel_files
                bg_cfg["mode"] = "per_segment"
                changed = True
                ok(f"Backgrounds per-segment resolved: {rel_files}")
        else:
            # legacy: N klip global (seed keywords + AI fallback)
            bg_count = int((cfg.get("visual") or {}).get("background_count", bg_cfg.get("count", 3)) or 3)
            resolved = bg_cfg.get("resolved_files") or []
            resolved_paths = [resolve_exec_path(exec_dir, p) for p in resolved]
            if resolved_paths and all(p and p.exists() for p in resolved_paths[:bg_count]):
                ok(f"Backgrounds sudah resolved ({min(len(resolved_paths), bg_count)} file)")
            else:
                api_key = (os.getenv("PIXABAY_API_KEY") or "").strip()
                if not api_key:
                    fail("PIXABAY_API_KEY tidak ditemukan (env/.env). Dibutuhkan untuk resolve background Pixabay.")
                from pixabay import generate_keywords  # noqa: E402
                ffprobe = find_ffmpeg(cfg)[1]
                chosen: list[dict] = []
                used_ids: set = set()

                def try_keywords(keywords: list[str], label: str) -> None:
                    nonlocal chosen, used_ids
                    for kw in keywords:
                        if len(chosen) >= bg_count:
                            break
                        out_path = work_dir / f"bg_{len(chosen) + 1}.mp4"
                        bg = download_bg_for_keyword(api_key, kw, out_path, used_ids, label, ffprobe, str(quote.get("id") or "local"))
                        if bg:
                            chosen.append(bg)
                            ok(f"bg {len(chosen)} id={bg['id']} kw='{kw}' -> {out_path.name}")

                if seeds:
                    info(f"Mencoba seed keywords: {seeds}")
                    try_keywords(seeds, "seed")

                need_ai = len(chosen) < bg_count and bool(bg_cfg.get("allow_ai_keywords_fallback", True))
                if need_ai:
                    info("Seed kurang, mencoba fallback AI keyword (seperti alur GitHub)...")
                    theme_stub = {"pixabay_query": (seeds[0] if seeds else "cinematic inspiration bokeh")}
                    q_lines = [str(x) for x in (quote.get("lines") or [])]
                    try:
                        ai_kws = generate_keywords(q_lines, " ".join(q_lines), theme_stub)
                    except Exception as e:
                        warn(f"AI keyword fallback gagal: {e}")
                        ai_kws = []
                    extra = [k for k in (ai_kws or []) if k not in seeds]
                    if extra:
                        info(f"AI keywords: {extra}")
                        try_keywords(extra, "ai")

                if len(chosen) < 1:
                    fail("Gagal menyiapkan background (tidak ada hasil). Coba ubah seed_keywords atau cek PIXABAY_API_KEY/koneksi.")
                rel = [rel_to_exec(Path(b["local"])) for b in chosen[:bg_count] if b.get("local")]
                bg_cfg["resolved_files"] = rel
                changed = True
                ok(f"Backgrounds resolved: {rel}")

    # --- music (Freetouse) ---
    music_cfg = media.setdefault("music", {})
    if (music_cfg.get("source") or "freetouse") == "freetouse":
        m_resolved = music_cfg.get("resolved_file")
        m_path = resolve_exec_path(exec_dir, m_resolved) if m_resolved else None
        if m_path and m_path.exists():
            ok(f"Music sudah resolved: {m_path}")
        else:
            try:
                from freetouse import pick_music as pick_freetouse_music  # noqa: E402
            except Exception as e:
                fail(f"Modul freetouse tidak tersedia: {e}")
            out_music = work_dir / "music.mp3"
            seed = music_cfg.get("seed_query") or str(quote.get("id") or "local")
            try:
                meta = pick_freetouse_music(str(seed), out_music, 60)
            except Exception as e:
                fail(f"Gagal resolve musik Freetouse: {e}")
            try:
                relm = str(out_music.resolve().relative_to(exec_dir.resolve())).replace("\\", "/")
            except Exception:
                relm = str(out_music)
            music_cfg["resolved_file"] = relm
            if meta.get("title"):
                music_cfg["title"] = meta.get("title")
            if meta.get("artist"):
                music_cfg["artist"] = meta.get("artist")
            if meta.get("url"):
                music_cfg["url"] = meta.get("url")
            if meta.get("license"):
                music_cfg["license_note"] = meta.get("license")
            changed = True
            ok(f"Music resolved: {relm} ({music_cfg.get('title','')})")

    if changed:
        write_json_file(exec_dir / "config.json", cfg)
        ok(f"config.json diperbarui: {exec_dir / 'config.json'}")
    else:
        info("Tidak ada perubahan config (sudah resolved).")


# ---------- caption / metadata (local, AI-assisted when missing) ----------

def is_provided_text(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


from caption_meta import build_caption_prompt, load_caption_styles, select_caption_style



def cmd_caption(exec_dir: Path) -> None:
    for name in ["quote.json", "youtube.json"]:
        if not (exec_dir / name).exists():
            fail(f"File wajib tidak ditemukan: {exec_dir / name}")

    yt_path = exec_dir / "youtube.json"
    quote = read_json_file(exec_dir / "quote.json")
    yt = read_json_file(yt_path)
    transcript = read_json_file(exec_dir / "transcript.json") if (exec_dir / "transcript.json").exists() else None

    # Pemeriksaan: jika caption disediakan, langsung gunakan (tidak diubah)
    if is_provided_text(yt.get("caption")):
        ok(f"Caption sudah disediakan di youtube.json (caption_source={yt.get('caption_source','user/existing')}), tidak diubah.")
        return

    try:
        styles = load_caption_styles(exec_dir)
    except Exception as e:
        fail(f"Gagal memuat caption styles: {e}")

    preferred = str(yt.get("caption_style") or yt.get("preferred_caption_style") or "").strip()
    try:
        selected_style = select_caption_style(styles, yt)
    except Exception as e:
        fail(f"Gagal memilih gaya caption: {e}")
    if preferred:
        pref = preferred.lower()
        sid = str(selected_style.get("id") or "").strip().lower()
        sname = str(selected_style.get("name") or "").strip().lower()
        if pref != sid and pref != sname:
            warn(f"Preferred caption style '{preferred}' tidak ditemukan, memilih gaya secara acak.")
    info(f"Caption belum disediakan. Menghasilkan caption dengan AI (gaya: {selected_style.get('id','?')} — dipilih acak/preferensi, 1 gaya)...")
    try:
        from ai import generate_plan  # noqa: E402
    except Exception as e:
        fail(f"Modul AI tidak tersedia: {e}")

    prompt = build_caption_prompt(styles, selected_style, quote, transcript, yt)
    try:
        result = generate_plan(prompt, [])
    except Exception as e:
        fail(f"Gagal generate caption (AI): {e}")

    caption = str((result or {}).get("caption") or "").strip()
    if not caption:
        fail("AI tidak mengembalikan caption yang valid.")

    style_id = str((result or {}).get("style_id") or "").strip()
    style_name = str((result or {}).get("style_name") or "").strip()
    reason = str((result or {}).get("reason") or "").strip()

    yt["caption"] = caption
    yt["caption_source"] = "ai"
    if style_id:
        yt["caption_style_id"] = style_id
    if style_name:
        yt["caption_style_name"] = style_name
    if reason:
        yt["caption_reason"] = reason
    write_json_file(yt_path, yt)
    ok(f"Caption (AI, style={style_id or '?'}) ditulis ke {yt_path}")

    # Jika output sudah ada (post-render), sinkronkan
    out_dir = resolve_exec_path(exec_dir, (read_json_file(exec_dir / "config.json").get("paths") or {}).get("out_dir", "out")) if (exec_dir / "config.json").exists() else (exec_dir / "out")
    out_dir = out_dir or (exec_dir / "out")
    try:
        if (out_dir / "caption.txt").exists() or (out_dir / "manifest.json").exists() or (out_dir / "description.txt").exists():
            (out_dir / "caption.txt").write_text(caption + "\n", encoding="utf-8")
            description = str(yt.get("description") or "").strip()
            (out_dir / "description.txt").write_text(description + "\n", encoding="utf-8")
            if (out_dir / "manifest.json").exists():
                manifest = read_json_file(out_dir / "manifest.json")
                manifest["caption"] = caption
                manifest["caption_source"] = "ai"
                if style_id:
                    manifest["caption_style_id"] = style_id
                if style_name:
                    manifest["caption_style_name"] = style_name
                write_json_file(out_dir / "manifest.json", manifest)
            info(f"Output diperbarui: {out_dir / 'caption.txt'}, {out_dir / 'description.txt'}, {out_dir / 'manifest.json'}")
    except Exception as e:
        warn(f"Gagal sinkronkan output: {e}")


# ---------- archive / reset ----------

def copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst)


def cmd_archive(exec_dir: Path, label: str | None = None) -> None:
    if not exec_dir.exists():
        fail(f"Folder eksekusi tidak ditemukan: {exec_dir}")
    if not TEMPLATE_DIR.exists():
        fail(f"Folder template tidak ditemukan: {TEMPLATE_DIR}")
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = "".join(ch for ch in (label or "") if ch.isalnum() or ch in ("-", "_"))[:40]
    qid = None
    try:
        q = read_json_file(exec_dir / "quote.json")
        qid = q.get("id")
    except Exception:
        pass
    parts = [ts]
    if qid is not None:
        parts.append(f"q{qid}")
    if safe_label:
        parts.append(safe_label)
    dest = ARCHIVE_DIR / "_".join(parts)
    i = 2
    base_dest = dest
    while dest.exists():
        dest = Path(str(base_dest) + f"_{i}")
        i += 1

    info(f"Mengarsipkan {exec_dir} -> {dest}")
    shutil.move(str(exec_dir), str(dest))
    info(f"Reset eksekusi dari template -> {exec_dir}")
    copy_tree(TEMPLATE_DIR, exec_dir)
    ok(f"Arsip selesai: {dest}")
    ok(f"Execution direset dari template: {exec_dir}")


def cmd_reset(exec_dir: Path) -> None:
    if not TEMPLATE_DIR.exists():
        fail(f"Folder template tidak ditemukan: {TEMPLATE_DIR}")
    if exec_dir.exists():
        info(f"Menghapus isi eksekusi: {exec_dir}")
        shutil.rmtree(exec_dir)
    copy_tree(TEMPLATE_DIR, exec_dir)
    ok(f"Execution direset dari template: {exec_dir}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Local video workflow (prepare/caption/render/archive/reset)")
    ap.add_argument("command", choices=["prepare", "caption", "render", "archive", "reset"], help="Perintah")
    ap.add_argument("--dir", default=str(DEFAULT_EXEC_DIR), help="Folder eksekusi (default: local/execution)")
    ap.add_argument("--label", default=None, help="Label arsip (untuk archive)")
    args = ap.parse_args()

    exec_dir = Path(args.dir)
    if not exec_dir.is_absolute():
        exec_dir = (ROOT / exec_dir).resolve()

    if args.command == "prepare":
        if not exec_dir.exists():
            fail(f"Folder eksekusi tidak ditemukan: {exec_dir}")
        cmd_prepare(exec_dir)
    elif args.command == "caption":
        if not exec_dir.exists():
            fail(f"Folder eksekusi tidak ditemukan: {exec_dir}")
        cmd_caption(exec_dir)
    elif args.command == "render":
        if not exec_dir.exists():
            fail(f"Folder eksekusi tidak ditemukan: {exec_dir}")
        cmd_render(exec_dir)
    elif args.command == "archive":
        cmd_archive(exec_dir, label=args.label)
    elif args.command == "reset":
        cmd_reset(exec_dir)


if __name__ == "__main__":
    main()
