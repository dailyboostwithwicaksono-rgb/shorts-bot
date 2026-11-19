#!/usr/bin/env python3
"""Dispatcher distribusi/upload konten ke platform aktif (default: YouTube, paritas)."""
import os
import sys

from content import load_canonical_content
from publish_youtube import publish_youtube, PublishResult


def _parse_targets(raw: str | None) -> list[str]:
    if raw is None or not str(raw).strip():
        return ["youtube"]
    parts = [p.strip().lower() for p in str(raw).replace(";", ",").split(",")]
    targets = [p for p in parts if p]
    return targets or ["youtube"]


def main() -> None:
    targets = _parse_targets(os.getenv("PUBLISH_TARGETS"))
    dry_run = (os.getenv("PUBLISH_DRY_RUN") or "").strip().lower() in ("1", "true", "yes", "on")
    fail_fast = (os.getenv("PUBLISH_FAIL_FAST") or "1").strip().lower() not in ("0", "false", "no", "off")

    content = load_canonical_content()
    results: list[PublishResult] = []
    failures = 0

    for target in targets:
        try:
            if target == "youtube":
                res = publish_youtube(content, dry_run=dry_run)
            elif target in ("tiktok", "meta", "x"):
                # Fase 4: stub/dry-run terbatas bila akses/API belum siap
                try:
                    from publish_platforms import publish_platform
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(f"modul publisher platform tidak tersedia: {exc}") from exc
                res = publish_platform(target, content, dry_run=dry_run)
            else:
                print(f"[warn] Target publish tidak dikenal: {target} (dilewati)")
                res = PublishResult(target=target, status="skipped", message="target tidak dikenal")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            res = PublishResult(target=target, status="failed", message=str(exc))
            print(f"[error] Publish {target} gagal: {exc}")
            if fail_fast:
                results.append(res)
                print(f"[info] Ringkasan publish: {len(results)} target, {failures} gagal")
                raise SystemExit(1)
        results.append(res)
        if res.status == "skipped":
            print(f"[info] Publish {target}: dilewati ({res.message or ''})")
        elif res.status == "dry_run":
            print(f"[info] Publish {target}: dry-run ({res.message or ''})")

    print(f"[info] Ringkasan publish: {len(results)} target, {failures} gagal")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
