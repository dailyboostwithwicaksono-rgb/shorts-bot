"""Kontrak konten kanonik berbasis artefak render (out/)."""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common import ROOT

OUT_DIR = ROOT / "out"
MANIFEST_PATH = OUT_DIR / "manifest.json"


@dataclass
class CanonicalContent:
    manifest_path: Path
    manifest: dict[str, Any]
    video_path: Path
    caption_path: Path | None = None

    @property
    def file(self) -> str:
        return str(self.manifest.get("file") or "final.mp4")

    @property
    def title(self) -> str:
        return str(self.manifest.get("title") or "")

    @property
    def caption(self) -> str:
        return str(self.manifest.get("caption") or "")

    @property
    def description(self) -> str:
        desc = self.manifest.get("description")
        if desc:
            return str(desc)
        hashtags = self.manifest.get("hashtags") or []
        return f"{self.caption}\n\n{' '.join(str(h) for h in hashtags)}".strip()

    @property
    def hashtags(self) -> list[str]:
        hs = self.manifest.get("hashtags") or []
        return [str(h) for h in hs if h]

    @property
    def privacy(self) -> str:
        return str(self.manifest.get("privacy") or "public")


def load_canonical_content(out_dir: Path | None = None) -> CanonicalContent:
    out = out_dir or OUT_DIR
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    video = out / str(manifest.get("file") or "final.mp4")
    caption_path = out / "caption.txt"
    return CanonicalContent(
        manifest_path=manifest_path,
        manifest=manifest,
        video_path=video,
        caption_path=caption_path if caption_path.exists() else None,
    )