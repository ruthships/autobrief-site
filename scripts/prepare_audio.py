#!/usr/bin/env python3
"""Ensure every episode audio file fits Cloudflare's 25 MiB per-asset limit.

Any file in public/episodes/ larger than the safe threshold is re-encoded in
place to 128 kbps (mp3 -> libmp3lame, m4a -> aac). 128 kbps is plenty for a
spoken-word podcast and keeps a typical ~15-20 min episode well under 25 MiB.
Idempotent: files already under the threshold are left untouched.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EPISODES_DIR = os.path.join(ROOT, "public", "episodes")

# Cloudflare limit is 25 MiB; leave headroom.
LIMIT_BYTES = 24 * 1024 * 1024
TARGET_BITRATE = "128k"


def reencode(path: str) -> None:
    ext = os.path.splitext(path)[1].lower()
    codec = "aac" if ext == ".m4a" else "libmp3lame"
    tmp = path + ".reencode" + ext
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", path,
            "-map", "0:a",
            "-c:a", codec,
            "-b:a", TARGET_BITRATE,
            tmp,
        ],
        check=True,
    )
    os.replace(tmp, path)


def main() -> int:
    if not os.path.isdir(EPISODES_DIR):
        print(f"No episodes dir at {EPISODES_DIR}")
        return 0

    changed = 0
    for name in sorted(os.listdir(EPISODES_DIR)):
        if name.startswith(".") or not name.lower().endswith((".mp3", ".m4a")):
            continue
        path = os.path.join(EPISODES_DIR, name)
        size = os.path.getsize(path)
        if size > LIMIT_BYTES:
            mib = size / (1024 * 1024)
            print(f"Re-encoding (>{LIMIT_BYTES // (1024*1024)} MiB, was {mib:.1f} MiB): {name}")
            reencode(path)
            new_mib = os.path.getsize(path) / (1024 * 1024)
            print(f"  -> {new_mib:.1f} MiB")
            changed += 1
        else:
            mib = size / (1024 * 1024)
            print(f"OK ({mib:.1f} MiB): {name}")

    print(f"\nDone. {changed} file(s) re-encoded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
