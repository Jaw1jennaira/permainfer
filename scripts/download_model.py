#!/usr/bin/env python3
"""Download the default open-weight model (free, Hugging Face).

Model: Qwen2.5-0.5B-Instruct, Q4_K_M GGUF (~491 MB).
License: Apache 2.0 (Qwen). No account, no payment, no key needed.

Usage:
    python scripts/download_model.py [--out models/qwen2.5-0.5b-instruct-q4_k_m.gguf]

After download, verify the SHA-256 and print it — the server records
this hash in every receipt, so anyone can check the exact weights
that produced a given completion.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

URL = (
    "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/"
    "qwen2.5-0.5b-instruct-q4_k_m.gguf"
)
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "models" / "qwen2.5-0.5b-instruct-q4_k_m.gguf"


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the default GGUF model")
    parser.add_argument("--url", default=URL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {args.url}")
    print(f"       -> {args.out}")
    hasher = hashlib.sha256()
    downloaded = 0
    with urllib.request.urlopen(args.url) as resp, args.out.open("wb") as f:
        total = int(resp.headers.get("Content-Length", "0") or 0)
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            hasher.update(chunk)
            downloaded += len(chunk)
            if total:
                print(f"\r  {downloaded / 1e6:7.1f} / {total / 1e6:7.1f} MB "
                      f"({100 * downloaded / total:5.1f}%)", end="", flush=True)
    print()
    print(f"Done. SHA-256: {hasher.hexdigest()}")
    print(f"Size: {downloaded / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
