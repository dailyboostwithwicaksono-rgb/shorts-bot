#!/usr/bin/env python3
"""Shorts 1080x1920: latar gelap + shape hitam + 3 baris teks bertahap + musik."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "render_plan.json"
OUT = ROOT / "out"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def esc(text: str) -> str:
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace("%", "\\%")
        .replace(",", "\\,")
    )


def main() -> None:
    p = json.loads(PLAN.read_text(encoding="utf-8"))
    dur = int(p["duration"])
    lines = p["lines"]
    top = int(p["band_top"])
    band_h = int(p["band_height"])

    OUT.mkdir(parents=True, exist_ok=True)
    final = OUT / "final.mp4"

    cmd = [
        "ffmpeg", "-y", "-v", "error", "-stats",
        "-stream_loop", "-1", "-i", p["background"],
        "-stream_loop", "-1", "-i", p["music"],
    ]

    video_filters = [
        f"trim=duration={dur},setpts=PTS-STARTPTS",
        "scale=1080:1920:force_original_aspect_ratio=increase",
        "crop=1080:1920",
        "fps=30,setsar=1",
        f"eq=brightness={p['brightness']}:saturation={p['saturation']}:contrast=1.05",
        f"drawbox=x=0:y={top}:w=1080:h={band_h}:"
        f"color=black@{p['overlay_opacity']}:t=fill",
    ]

    starts = [1.0, 2.2, 3.4]
    ys = [top + 90, top + band_h // 2 - 45, top + band_h - 135]
    for i, line in enumerate(lines[:3]):
        video_filters.append(
            f"drawtext=fontfile='{FONT}':text='{esc(line)}':"
            f"fontcolor=white:fontsize={p['font_size']}:"
            f"shadowcolor=black@0.8:shadowx=2:shadowy=2:"
            f"x=(w-text_w)/2:y={ys[i]}:enable='gte(t,{starts[i]})'"
        )

    audio_filter = (
        f"[1:a]atrim=duration={dur},volume={p['music_volume']},"
        f"afade=t=out:st={dur - 2}:d=2[a]"
    )
    graph = "[0:v]" + ",".join(video_filters) + "[v];" + audio_filter

    cmd += [
        "-filter_complex", graph,
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
        "lines": lines,
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
