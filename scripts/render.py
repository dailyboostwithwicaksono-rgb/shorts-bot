#!/usr/bin/env python3
"""Render Shorts 1080x1920: bg grayscale + overlay + feathered band + teks progresif + musik."""
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "render_plan.json"
OUT = ROOT / "out"
FONTS_DIR = ROOT / "assets" / "fonts"

W, H = 1080, 1920


def font_path(name: str) -> str:
    p = FONTS_DIR / name
    if not p.exists():
        raise FileNotFoundError(f"Font tidak ditemukan: {p}")
    return str(p)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = (value or "#FFFFFF").strip().lstrip("#")
    if len(v) == 3:
        v = "".join(ch * 2 for ch in v)
    return tuple(int(v[i : i + 2], 16) for i in (0, 2, 4))


def fade_in_time(text: str, p: dict) -> float:
    words = max(1, len(str(text or "").split()))
    v = float(p.get("fade_in_min", 0.7)) + words * float(p.get("fade_in_per_word", 0.12))
    v = max(float(p.get("fade_in_min", 0.7)), min(float(p.get("fade_in_max", 1.4)), v))
    return round(v, 2)


def load_quote_font(size: int):
    return ImageFont.truetype(font_path("Montserrat-LightItalic.ttf"), size)


def load_emphasis_font(size: int):
    return ImageFont.truetype(font_path("Montserrat-SemiBoldItalic.ttf"), size)


def load_author_font(size: int):
    return ImageFont.truetype(font_path("Montserrat-Italic.ttf"), size)


def text_width(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    if not text:
        return 0.0
    try:
        return float(draw.textlength(text, font=font))
    except Exception:
        bbox = draw.textbbox((0, 0), text, font=font)
        return float(bbox[2] - bbox[0])


def measure_segments(segments: list[dict], size: int) -> float:
    img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    qf = load_quote_font(size)
    ef = load_emphasis_font(size)
    total = 0.0
    for seg in segments:
        font = ef if seg.get("emphasis") else qf
        total += text_width(draw, seg.get("text", ""), font)
    return total


def fit_quote_size(segments: list[dict], base_size: int, max_width: int) -> int:
    size = int(base_size)
    while size > 20 and measure_segments(segments, size) > max_width:
        size -= 2
    return size


def line_height(size: int, spacing: float) -> int:
    return max(1, int(round(size * spacing)))


def render_quote_line(segments: list[dict], y_center: int, p: dict, out_path: Path) -> None:
    base_size = int(p.get("quote_font_size", 51))
    max_w = int(p.get("max_text_width", 920))
    spacing = float(p.get("line_spacing", 1.3))
    color = hex_to_rgb(p.get("quote_color", "#FFFFFF"))
    size = fit_quote_size(segments, base_size, max_w)
    qf = load_quote_font(size)
    ef = load_emphasis_font(size)

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    total_w = measure_segments(segments, size)
    x = (W - total_w) / 2.0
    bbox = draw.textbbox((0, 0), "Ag", font=qf)
    text_h = bbox[3] - bbox[1]
    y = int(round(y_center - text_h / 2.0))

    for seg in segments:
        text = seg.get("text", "")
        if not text:
            continue
        font = ef if seg.get("emphasis") else qf
        draw.text((x, y), text, font=font, fill=(*color, 255))
        x += text_width(draw, text, font)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def render_author_line(text: str, y_center: int, p: dict, out_path: Path) -> None:
    size = int(p.get("author_font_size", 28))
    color = hex_to_rgb(p.get("author_color", "#DDDDDD"))
    font = load_author_font(size)

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    tw = text_width(draw, text, font)
    while size > 14 and tw > int(p.get("max_text_width", 920)):
        size -= 1
        font = load_author_font(size)
        tw = text_width(draw, text, font)

    bbox = draw.textbbox((0, 0), text or "Ag", font=font)
    text_h = bbox[3] - bbox[1]
    x = (W - tw) / 2.0
    y = int(round(y_center - text_h / 2.0))
    draw.text((x, y), text, font=font, fill=(*color, 255))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def render_dash_line(y_center: int, p: dict, out_path: Path) -> None:
    dash_w = int(p.get("dash_width", 100))
    dash_h = int(p.get("dash_height", 2))
    color = hex_to_rgb(p.get("author_color", "#DDDDDD"))
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    x0 = int(round((W - dash_w) / 2.0))
    y0 = int(round(y_center - dash_h / 2.0))
    draw.rectangle([x0, y0, x0 + dash_w, y0 + dash_h], fill=(*color, 255))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def render_band_overlay(p: dict, out_path: Path) -> None:
    band_top = int(p.get("band_top", 560))
    band_h = int(p.get("band_height", 800))
    band_opacity = float(p.get("overlay_opacity", 0.55))
    feather = max(0, int(p.get("band_feather", 140)))
    feather = min(feather, band_h // 2)

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if band_h <= 0:
        img.save(out_path)
        return
    max_a = int(round(max(0.0, min(1.0, band_opacity)) * 255))
    px = img.load()
    y0 = max(0, band_top)
    y1 = min(H, band_top + band_h)
    for y in range(y0, y1):
        # distance inside band
        dt = y - band_top
        db = (band_top + band_h - 1) - y
        d = min(dt, db)
        if feather > 0 and d < feather:
            a = int(round(max_a * (d + 1) / feather))
        else:
            a = max_a
        if a <= 0:
            continue
        for x in range(W):
            px[x, y] = (0, 0, 0, a)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def compute_centers(p: dict, n_quote: int, has_trailing: bool) -> tuple[list[int], int | None]:
    band_top = int(p.get("band_top", 560))
    band_h = int(p.get("band_height", 800))
    spacing = float(p.get("line_spacing", 1.3))
    q_size = int(p.get("quote_font_size", 51))
    a_size = int(p.get("author_font_size", 28))

    q_step = line_height(q_size, spacing)
    gap_before_author = int(round(q_step * 0.9))

    total_h = 0
    if n_quote > 0:
        total_h += q_size + (n_quote - 1) * q_step
    if has_trailing:
        if n_quote > 0:
            total_h += gap_before_author
        total_h += a_size

    block_top = band_top + max(0, (band_h - total_h) // 2)
    q_centers: list[int] = []
    y = block_top + q_size // 2
    for _ in range(n_quote):
        q_centers.append(int(y))
        y += q_step

    trailing_center = None
    if has_trailing:
        if n_quote > 0:
            y = block_top + q_size + (n_quote - 1) * q_step + gap_before_author + a_size // 2
        else:
            y = block_top + a_size // 2
        trailing_center = int(y)
    return q_centers, trailing_center


def probe_duration(path: str) -> float | None:
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


def ensure_ffmpeg_tools() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        raise SystemExit(f"Tool render tidak ditemukan di PATH: {', '.join(missing)}. Pastikan ffmpeg/ffprobe terpasang.")


def build_and_render(p: dict) -> tuple[Path, dict]:
    dur = int(p.get("duration", 30))
    bg = p["background"]
    music = p["music"]

    q_lines = list(p.get("quote_line_segments") or [])
    author_text = (p.get("author_display") or "").strip()
    show_dash = bool(p.get("author_is_dash"))
    has_trailing = bool(author_text) or show_dash
    if not q_lines and not has_trailing:
        raise ValueError("Tidak ada konten teks untuk dirender")

    q_centers, trailing_center = compute_centers(p, len(q_lines), has_trailing)

    # detect bg duration for slow-down if shorter
    bg_meta = p.get("background_meta") or {}
    src_dur = probe_duration(bg)
    if not src_dur or src_dur <= 0:
        try:
            src_dur = float(bg_meta.get("duration_actual") or bg_meta.get("duration_meta") or 0) or None
        except Exception:
            src_dur = None
    slow_factor = 1.0
    if src_dur and src_dur > 0 and src_dur < dur:
        slow_factor = dur / src_dur  # stretch to fill target duration (no loop jump)

    tmpdir = Path(tempfile.mkdtemp(prefix="shorts-lines-", dir=str(OUT)))
    try:
        elements = []  # (png_path, plain_text)
        for i, (segments, y_center) in enumerate(zip(q_lines, q_centers)):
            png = tmpdir / f"line_{i:02d}.png"
            render_quote_line(segments, y_center, p, png)
            plain = "".join(seg.get("text", "") for seg in segments).strip()
            elements.append((png, plain))
        if has_trailing and trailing_center is not None:
            png = tmpdir / f"line_{len(q_lines):02d}.png"
            if show_dash:
                render_dash_line(trailing_center, p, png)
                elements.append((png, "-"))
            else:
                render_author_line(author_text, trailing_center, p, png)
                elements.append((png, author_text))

        band_png = tmpdir / "band.png"
        render_band_overlay(p, band_png)

        # timing
        timed = []
        t = 1.0
        line_gap = float(p.get("line_gap", 0.7))
        for _, plain in elements:
            fi = fade_in_time(plain, p)
            start = min(round(t, 2), float(max(1, dur - 2)))
            timed.append((start, fi))
            t = round(start + fi + line_gap, 2)

        # ffmpeg filter graph
        brightness = float(p.get("brightness", -0.08))
        saturation = float(p.get("saturation", 0.0))
        full_overlay = float(p.get("full_overlay_opacity", 0.3))
        music_vol = float(p.get("music_volume", 0.28))

        vf = [
            f"setpts={slow_factor}*PTS" if slow_factor > 1.001 else "setpts=PTS-STARTPTS",
            f"trim=duration={dur}",
            "setpts=PTS-STARTPTS",
            "scale=1080:1920:force_original_aspect_ratio=increase",
            "crop=1080:1920",
            "fps=30,setsar=1",
            f"eq=brightness={brightness}:saturation={saturation}:contrast=1.05",
            f"drawbox=x=0:y=0:w=1080:h=1920:color=black@{full_overlay}:t=fill",
        ]

        parts = ["[0:v]" + ",".join(vf) + "[base]"]
        # band overlay (input index 2)
        parts.append("[2:v]format=rgba[band]")
        parts.append("[base][band]overlay=0:0:format=auto[v0]")

        current = "v0"
        # text overlays start at input index 3
        for i, (start, fi) in enumerate(timed):
            in_idx = 3 + i
            parts.append(f"[{in_idx}:v]format=rgba,fade=t=in:st={start}:d={fi}:alpha=1[t{i}]")
            out_label = "vout" if i == len(timed) - 1 else f"v{i+1}"
            parts.append(f"[{current}][t{i}]overlay=0:0:format=auto[{out_label}]")
            current = out_label

        parts.append(
            f"[1:a]atrim=duration={dur},asetpts=PTS-STARTPTS,"
            f"volume={music_vol},afade=t=out:st={max(0, dur-2)}:d=2[a]"
        )
        filter_complex = ";".join(parts)

        final = OUT / "final.mp4"
        cmd = [
            "ffmpeg", "-y", "-v", "error", "-stats",
            "-stream_loop", "-1", "-i", str(bg),
            "-stream_loop", "-1", "-i", str(music),
            "-loop", "1", "-t", str(dur), "-i", str(band_png),
        ]
        for (png, _plain), _t in zip(elements, timed):
            cmd += ["-loop", "1", "-t", str(dur), "-i", str(png)]
        cmd += [
            "-filter_complex", filter_complex,
            "-map", f"[{current}]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart",
            "-map_metadata", "-1", "-map_chapters", "-1",
            "-t", str(dur),
            str(final),
        ]
        subprocess.run(cmd, check=True)
        info = {"timed": [(elements[i][0].name, timed[i][0], timed[i][1]) for i in range(len(timed))],
                "bg_src_dur": src_dur, "slow_factor": slow_factor}
        return final, info
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main() -> None:
    t0 = time.perf_counter()
    ensure_ffmpeg_tools()
    p = json.loads(PLAN.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    t_render = time.perf_counter()
    final, meta = build_and_render(p)
    render_elapsed = time.perf_counter() - t_render

    raw = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", str(final)],
        check=True, capture_output=True, text=True,
    ).stdout
    info = json.loads(raw)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    duration = round(float(info["format"].get("duration", 0)), 2)

    # Title kanonik; caption.txt dipertahankan sebagai nama file legacy.
    _title = str(p.get("title") or p.get("caption") or "")
    (OUT / "caption.txt").write_text(_title, encoding="utf-8")
    (OUT / "description.txt").write_text(p.get("description", ""), encoding="utf-8")
    manifest = {
        "file": "final.mp4",
        "duration": duration,
        "width": video.get("width"),
        "height": video.get("height"),
        "size_bytes": final.stat().st_size,
        "theme": p.get("theme"),
        "mode": p.get("mode"),
        "quote": p.get("quote"),
        "author": p.get("author"),
        "language": p.get("language"),
        "lines": p.get("lines"),
        "title": _title,
        "caption": _title,  # alias legacy; selalu mirror title
        "hashtags": p.get("hashtags", []),
        "description": p.get("description", ""),
        "privacy": p.get("privacy", "public"),
        "background_meta": p.get("background_meta", {}),
        "render": meta,
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[ok] render selesai: {final} ({duration}s, {manifest['size_bytes']} bytes, slow={meta.get('slow_factor')})")
    print(f"[info] waktu render: compose={render_elapsed:.2f}s total={time.perf_counter()-t0:.2f}s")


if __name__ == "__main__":
    main()
