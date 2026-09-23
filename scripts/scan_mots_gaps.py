"""Screen official KITTI MOTS txt annotations for internal track gaps.

This is a candidate search, not evidence of physical occlusion or tracker failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from collections import defaultdict
from pathlib import Path


def scan_annotations(archive: Path, minimum_gap: int = 3) -> dict:
    if minimum_gap < 1:
        raise ValueError("minimum_gap must be at least 1")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    candidates: list[dict] = []
    sequences = 0
    tracks = 0
    frame_count = 0
    with zipfile.ZipFile(archive) as bundle:
        names = sorted(name for name in bundle.namelist() if name.startswith("instances_txt/") and name.endswith(".txt"))
        if not names:
            raise ValueError("No instances_txt/*.txt files found in archive")
        for name in names:
            sequence = Path(name).stem
            appearances: dict[tuple[int, int], set[int]] = defaultdict(set)
            frames: set[int] = set()
            for raw_line in bundle.read(name).decode("utf-8").splitlines():
                parts = raw_line.split(" ", 5)
                if len(parts) != 6:
                    raise ValueError(f"Malformed MOTS line in {name}: {raw_line[:80]}")
                frame, object_id, class_id = map(int, parts[:3])
                frames.add(frame)
                if object_id == 10000:
                    continue
                if object_id // 1000 != class_id:
                    raise ValueError(f"Object/class mismatch in {name} frame {frame}")
                appearances[(object_id, class_id)].add(frame)
            sequences += 1
            frame_count += len(frames)
            tracks += len(appearances)
            for (object_id, class_id), visible in sorted(appearances.items()):
                ordered = sorted(visible)
                for previous, current in zip(ordered, ordered[1:]):
                    gap = current - previous - 1
                    if gap >= minimum_gap:
                        candidates.append({
                            "sequence": sequence,
                            "object_id": object_id,
                            "class_id": class_id,
                            "last_visible_frame": previous,
                            "first_visible_again_frame": current,
                            "first_missing_frame": previous + 1,
                            "last_missing_frame": current - 1,
                            "missing_frames": gap,
                        })
    by_class = {"car": 0, "pedestrian": 0, "other": 0}
    for candidate in candidates:
        key = {1: "car", 2: "pedestrian"}.get(candidate["class_id"], "other")
        by_class[key] += 1
    return {
        "source": "https://www.vision.rwth-aachen.de/media/resource_files/instances_txt.zip",
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": digest,
        "minimum_gap": minimum_gap,
        "sequences": sequences,
        "annotated_frames": frame_count,
        "tracks": tracks,
        "candidate_count": len(candidates),
        "candidate_count_by_class": by_class,
        "candidates": candidates,
        "interpretation": "annotation gaps only; RGB review needed before calling any case occlusion or reappearance",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--minimum-gap", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = scan_annotations(args.archive, args.minimum_gap)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
