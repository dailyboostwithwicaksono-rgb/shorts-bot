#!/usr/bin/env python3
"""Shorts 1080x1920: latar gelap + shape hitam + 3 baris teks fade + musik."""
import json
import subprocess
from pathlib import Path

from PIL import ImageFont

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "render_plan.json"
OUT = ROOT / "out"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
MAX_TEXT_WIDTH = 920  # 1080 - margin 80 px di tiap sisi


def esc(text: str) -> str:
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace("%", "\\%")
        .replace(",", "\\,")
    )


def fit_font_size(text: str, p: dict) -> int:
    """Turunkan font sampai teks muat di MAX_TEXT_WIDTH."""
    max_size = int(p.get("font_size", 72))
    min_size = int(p.get("min_font_size", 34))
    for size in range(max_size, min_size - 1, -2):
        font = ImageFont.truetype(FONT, size)
        bbox = font.getbbox(text)
        if bbox[2] - bbox[0] <= MAX_TEXT_WIDTH:
            return size
    return min_size


def _text_layer(
    index: int,
    text: str,
    size: int,
    y: int,
    start: float,
    fade_in: float,
    duration: int,
) -> str:
    """Layer transparan: fade in sekali, lalu teks tetap tampil sampai akhir."""
    return (
        f"color=c=black@0:s=1080x1920:r=30:d={duration},format=rgba,"
        f"drawtext=fontfile='{FONT}':text='{esc(text)}':"
        f"fontcolor=white:fontsize={size}:"
        f"x=(w-text_w)/2:y={y},"
        f"fade=t=in:st={start}:d={fade_in}:alpha=1[t{index}]"
    )


def fade_in_time(text: str, p: dict) -> float:
    """Durasi fade in dihitung dari jumlah kata, dibatasi 0,7–1,4 detik."""
    words = max(1, len(str(text).split()))
    fade_in = min(
        float(p.get("fade_in_max", 1.4)),
        max(
            float(p.get("fade_in_min", 0.7)),
            float(p.get("fade_in_min", 0.7)) + words * float(p.get("fade_in_per_word", 0.12)),
        ),
    )
    return round(fade_in, 2)


def build_graph(p: dict) -> str:
    dur = int(p["duration"])
    lines = list(p["lines"])[:3]
    top = int(p["band_top"])
    band_h = int(p["band_height"])

    video_filters = [
        "trim=duration=%d,setpts=PTS-STARTPTS" % dur,
        "scale=1080:1920:force_original_aspect_ratio=increase",
        "crop=1080:1920",
        "fps=30,setsar=1",
        "eq=brightness=%s:saturation=%s:contrast=1.05"
        % (p["brightness"], p["saturation"]),
        "drawbox=x=0:y=%d:w=1080:h=%d:color=black@%s:t=fill"
        % (top, band_h, p["overlay_opacity"]),
    ]

    parts = ["[0:v]" + ",".join(video_filters) + "[base]"]
    layers: list[str] = []
    overlays: list[str] = []
    current = "base"
    centers = [
        top + band_h * 0.22,
        top + band_h * 0.50,
        top + band_h * 0.78,
    ]

    line_gap = float(p.get("line_gap", 0.3))
    start = 1.0
    for i, line in enumerate(lines):
        size = fit_font_size(line, p)
        y = int(centers[i] - size / 2)
        fade_in = fade_in_time(line, p)
        start = min(round(start, 2), float(max(1, dur - 3)))
        layers.append(
            _text_layer(i, line, size, y, start, fade_in, dur)
        )
        next_label = "v" if i == len(lines) - 1 else f"b{i + 1}"
        overlays.append(
            f"[{current}][t{i}]overlay=0:0:format=auto[{next_label}]"
        )
        current = next_label
        start = round(start + fade_in + line_gap, 2)

    audio = (
        f"[1:a]atrim=duration={dur},volume={p['music_volume']},"
        f"afade=t=out:st={dur - 2}:d=2[a]"
    )
    parts.extend(layers)
    parts.extend(overlays)
    parts.append(audio)
    return ";".join(parts)


def main() -> None:
    p = json.loads(PLAN.read_text(encoding="utf-8"))
    dur = int(p["duration"])
    OUT.mkdir(parents=True, exist_ok=True)
    final = OUT / "final.mp4"

    cmd = [
        "ffmpeg", "-y", "-v", "error", "-stats",
        "-stream_loop", "-1", "-i", p["background"],
        "-stream_loop", "-1", "-i", p["music"],
        "-filter_complex", build_graph(p),
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        "-map_metadata", "-1", "-map_chapters", "-1",
        "-t", str(dur),
        str(final),
    ]
    subprocess.run(cmd, check=True)

    raw = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", str(final)],
        check=True, capture_output=True, text=True,
    ).stdout
    info = json.loads(raw)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    duration = round(float(info["format"].get("duration", 0)), 2)

    (OUT / "caption.txt").write_text(p["description"], encoding="utf-8")
    manifest = {
        "file": "final.mp4",
        "duration": duration,
        "width": video.get("width"),
        "height": video.get("height"),
        "size_bytes": final.stat().st_size,
        "theme": p["theme"],
        "lines": p["lines"],
        "title": p["title"],
        "caption": p["caption"],
        "hashtags": p["hashtags"],
        "description": p["description"],
        "privacy": p["privacy"],
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[ok] render selesai: {final} ({duration}s, {manifest['size_bytes']} bytes)")


if __name__ == "__main__":
    main()
