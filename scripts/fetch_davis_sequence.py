"""Fetch one DAVIS 2017 sequence from the official archive using HTTP ranges."""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

from remotezip import RemoteIOError, RemoteZip


DAVIS_URL = "https://data.vision.ee.ethz.ch/csergi/share/davis/DAVIS-2017-trainval-480p.zip"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sequence", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--frame", action="append", type=int, default=[])
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.sequence):
        parser.error("invalid DAVIS sequence name")
    if any(index < 0 for index in args.frame):
        parser.error("frame indices must be non-negative")

    prefix = "DAVIS/"
    subdirs = ("JPEGImages", "Annotations")
    selected = set(args.frame)
    with RemoteZip(DAVIS_URL) as archive:
        members: dict[str, list[str]] = {}
        for subdir, suffix in (("JPEGImages", ".jpg"), ("Annotations", ".png")):
            folder = f"{prefix}{subdir}/480p/{args.sequence}/"
            names = sorted(
                name for name in archive.namelist()
                if name.startswith(folder) and name.endswith(suffix)
            )
            if not names:
                raise SystemExit(f"sequence not found in official archive: {args.sequence}/{subdir}")
            members[subdir] = names
        frame_names = [{Path(name).stem for name in names} for names in members.values()]
        if frame_names[0] != frame_names[1]:
            raise SystemExit("official image/annotation frame lists do not match")
        available = {int(name) for name in frame_names[0]}
        if selected and not selected <= available:
            raise SystemExit(f"frame indices not found: {sorted(selected - available)}")
        total = 0
        downloaded = 0
        for subdir in subdirs:
            for name in members[subdir]:
                if selected and int(Path(name).stem) not in selected:
                    continue
                destination = args.output_root / name
                info = archive.getinfo(name)
                if destination.exists() and destination.stat().st_size == info.file_size:
                    total += 1
                    continue
                if destination.exists():
                    raise SystemExit(f"existing file has unexpected size: {destination}")
                for attempt in range(4):
                    try:
                        data = archive.read(name)
                        break
                    except RemoteIOError:
                        if attempt == 3:
                            raise
                        print(f"retry {attempt + 1}/3: {name}", flush=True)
                        time.sleep(2 ** attempt)
                if len(data) != info.file_size:
                    raise SystemExit(f"incomplete download: {name}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                total += 1
                downloaded += 1
                if downloaded % 10 == 0:
                    print(f"downloaded {downloaded} files", flush=True)
    print(f"sequence={args.sequence} files={total} new_files={downloaded} root={args.output_root}")


if __name__ == "__main__":
    main()
