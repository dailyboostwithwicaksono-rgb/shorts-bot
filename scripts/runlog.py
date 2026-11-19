"""Penulisan log/metadata run (skema & perilaku setara)."""
from pathlib import Path

from common import append_jsonl


def append_used_entry(path: Path, entry: dict) -> None:
    append_jsonl(path, entry)


def log_run(ts: str, day: str, run_seed: str, mode: str, source: str,
            selected_id, language: str, quote_text: str, author_name: str,
            quote_lines: list[str], title: str, duration: int,
            bg: dict, music: dict,
            used_path: Path, used_videos_path: Path, used_music_path: Path) -> None:
    log_entry = {
        "ts": ts,
        "date": day,
        "mode": mode,
        "source": source,
        "id": selected_id,
        "language": language,
        "quote": quote_text,
        "author": author_name,
        "lines": quote_lines,
        "title": title,
        "background": {
            "source": bg.get("source"),
            "id": bg.get("id"),
            "user": bg.get("user") or bg.get("photographer"),
            "url": bg.get("pageURL") or bg.get("url"),
            "keyword": bg.get("keyword"),
        },
        "music": {
            "source": music.get("source"),
            "id": music.get("id"),
            "title": music.get("title"),
            "artist": music.get("artist"),
            "url": music.get("url"),
        },
    }
    append_used_entry(used_path, log_entry)

    video_meta_log = {
        "ts": ts,
        "date": day,
        "run_seed": run_seed,
        "quote_id": selected_id,
        "quote": quote_text,
        "duration_target": duration,
        "background": bg,
    }
    append_jsonl(used_videos_path, video_meta_log)

    music_meta_log = {
        "ts": ts,
        "date": day,
        "run_seed": run_seed,
        "quote_id": selected_id,
        "duration_target": duration,
        "music": music,
    }
    append_jsonl(used_music_path, music_meta_log)