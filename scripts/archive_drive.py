#!/usr/bin/env python3
"""Arsipkan isi folder out/ ke Google Drive lewat OAuth user (bukan service account)."""
import os
from datetime import date
from pathlib import Path

import requests

from gauth import get_access_token

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
API_URL = "https://www.googleapis.com/drive/v3/files"
CHUNK = 8 * 1024 * 1024


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _find_or_create_folder(token: str, parent: str, name: str) -> str:
    query = (
        f"name='{name}' and '{parent}' in parents and "
        "mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    r = requests.get(
        API_URL,
        params={"q": query, "fields": "files(id,name)", "pageSize": 10},
        headers=_headers(token),
        timeout=30,
    )
    r.raise_for_status()
    existing = r.json().get("files", [])
    if existing:
        return existing[0]["id"]

    r = requests.post(
        API_URL,
        params={"fields": "id,name"},
        headers={**_headers(token), "Content-Type": "application/json; charset=UTF-8"},
        json={"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent]},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def _upload(token: str, path: Path, parent: str) -> None:
    size = path.stat().st_size
    init = requests.post(
        UPLOAD_URL,
        params={"uploadType": "resumable", "fields": "id,name"},
        headers={
            **_headers(token),
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "application/octet-stream",
            "X-Upload-Content-Length": str(size),
        },
        json={"name": path.name, "parents": [parent]},
        timeout=60,
    )
    init.raise_for_status()
    session_url = init.headers["Location"]
    data = path.read_bytes()

    start = 0
    while start < size:
        end = min(start + CHUNK, size) - 1
        part = data[start : end + 1]
        r = requests.put(
            session_url,
            headers={
                **_headers(token),
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(part)),
                "Content-Range": f"bytes {start}-{end}/{size}",
            },
            data=part,
            timeout=300,
        )
        if r.status_code in (200, 201):
            return
        if r.status_code == 308:
            rng = r.headers.get("Range", "")
            try:
                next_start = int(rng.split("=", 1)[1].split("-", 1)[1]) + 1
            except (IndexError, ValueError):
                next_start = end + 1
            if next_start <= start:
                raise SystemExit(f"Upload tidak maju: {rng}")
            start = next_start
            continue
        raise SystemExit(f"Gagal upload {path.name}: {r.status_code} {r.text[:400]}")


def main() -> None:
    if not OUT.is_dir():
        raise SystemExit(f"Folder {OUT} tidak ada.")
    files = sorted(p for p in OUT.iterdir() if p.is_file())
    if not files:
        raise SystemExit(f"Tidak ada file di {OUT}.")

    day = os.getenv("RUN_DATE") or date.today().isoformat()
    parent = os.environ["GDRIVE_OUTPUTS_FOLDER_ID"]
    token = get_access_token()
    folder_id = _find_or_create_folder(token, parent, day)

    for path in files:
        _upload(token, path, folder_id)
        print(f"[ok] Drive: {day}/{path.name}")

    print(f"[ok] Arsip Drive selesai: {parent}/{day} ({len(files)} file)")


if __name__ == "__main__":
    main()
