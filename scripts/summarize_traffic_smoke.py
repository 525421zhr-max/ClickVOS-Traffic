"""Verify saved smoke masks and create a local inspection sheet; no quality scoring."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--frames", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads((args.run / "result.json").read_text(encoding="utf-8"))
    count = result["frame_count"]
    if count < 1 or not result["objects"]:
        raise ValueError("empty run")
    expected = [f"{i:05d}.png" for i in range(count)]
    frame_names = [f"{i:05d}.jpg" for i in range(count)]
    if sorted(p.name for p in args.frames.glob("*.jpg")) != frame_names:
        raise ValueError("input frame names/count mismatch")
    digest = hashlib.sha256()
    for name in frame_names:
        frame = args.frames / name
        with Image.open(frame) as image:
            if list(image.size) != result["frame_size_wh"]:
                raise ValueError(f"input size mismatch: {name}")
        digest.update(name.encode("utf-8") + b"\0" + hashlib.sha256(frame.read_bytes()).digest())
    summary = {"status": "passed", "frame_count": count,
               "frame_size_wh": result["frame_size_wh"], "input_collection_sha256": digest.hexdigest(),
               "ground_truth_available": False, "quality_metrics_reported": [], "objects": []}
    sample = sorted({0, count // 2, count - 1})
    sheet = Image.new("RGB", (480 * len(sample), 294 * len(result["objects"])), "white")
    draw = ImageDraw.Draw(sheet)
    for row, obj in enumerate(result["objects"]):
        root = args.run / f"object_{obj['object_id']:03d}"
        if sorted(p.name for p in (root / "masks").glob("*.png")) != expected:
            raise ValueError("mask names/count mismatch")
        areas = []
        for name in expected:
            with Image.open(root / "masks" / name) as image:
                if image.mode != "L" or list(image.size) != result["frame_size_wh"]:
                    raise ValueError(f"mask format/size mismatch: {name}")
                mask = np.asarray(image)
                if not set(np.unique(mask)).issubset({0, 255}):
                    raise ValueError("non-binary mask")
                area = int(np.count_nonzero(mask))
            if area != obj["mask_foreground_pixels"][name]:
                raise ValueError("reported area mismatch")
            areas.append(area)
        empty = [i for i, area in enumerate(areas) if area == 0]
        summary["objects"].append({"object_id": obj["object_id"], "saved_mask_count": len(areas),
                                    "empty_frames": empty, "area_min": min(areas), "area_max": max(areas)})
        for column, index in enumerate(sample):
            with Image.open(root / "overlays" / f"{index:05d}.jpg") as overlay:
                overlay.thumbnail((480, 270))
                sheet.paste(overlay, (480 * column, 294 * row + 24))
            draw.text((480 * column + 5, 294 * row + 5), f"Object {obj['object_id']} / frame {index}", fill="black")
    sheet.save(args.run / "inspection.jpg")
    (args.run / "verification.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
