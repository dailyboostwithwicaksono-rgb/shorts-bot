"""Ubah service account JSON jadi satu baris base64 untuk GitHub Secret.

Cara pakai di laptop:
    python scripts/encode_sa.py sa.json
"""
import base64
import sys
from pathlib import Path


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "sa.json")
    raw = path.read_bytes()
    print(base64.b64encode(raw).decode("ascii"))


if __name__ == "__main__":
    main()
