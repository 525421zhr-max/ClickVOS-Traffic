"""Check a browser-downloaded ZIP against the task and independently decode its RLE."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify(task: Path, downloaded: Path) -> dict:
    result = json.loads((task / "result.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(downloaded.read_bytes()).hexdigest()
    require(digest == hashlib.sha256((task / "exports" / downloaded.name).read_bytes()).hexdigest(),
            "download differs from generated bundle")
    expected_masks = {f"masks/object_{obj['object_id']:03d}/{i:05d}.png"
                      for obj in result["objects"] for i in range(result["frame_count"])}
    with zipfile.ZipFile(downloaded) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "duplicate ZIP entries")
        expected = expected_masks | {"project.json", "annotations/coco_rle.json", "preview.mp4"}
        if (task / "first_frame_review.json").exists():
            expected.add("first_frame_review.json")
        require(set(names) == expected, "unexpected or missing ZIP files")
        project = json.loads(archive.read("project.json"))
        coco = json.loads(archive.read("annotations/coco_rle.json"))
        require(project["task_id"] == task.name, "wrong task ID")
        require(project["corrections"] == result.get("corrections", []), "lost correction record")
        require(project["video"]["frame_count"] == result["frame_count"], "wrong frame count")
        require(len(coco["images"]) == result["frame_count"], "wrong COCO image count")
        masks = {}
        for obj in result["objects"]:
            for index in range(result["frame_count"]):
                name = f"masks/object_{obj['object_id']:03d}/{index:05d}.png"
                payload = archive.read(name)
                require(payload == (task / name).read_bytes(), "downloaded mask differs from task")
                with Image.open(io.BytesIO(payload)) as image:
                    raw = np.asarray(image)
                    require(raw.ndim == 2 and set(np.unique(raw)).issubset({0, 255}), "non-binary mask")
                    mask = raw > 0
                require(mask.shape == (project["video"]["height"], project["video"]["width"]), "wrong mask size")
                require(int(mask.sum()) == obj["mask_foreground_pixels"][f"{index:05d}.png"], "area mismatch")
                masks[(index + 1, obj["object_id"])] = mask
        seen = set()
        for annotation in coco["annotations"]:
            key = (annotation["image_id"], annotation["object_id"])
            require(key not in seen and key in masks, "invalid/duplicate annotation")
            seen.add(key)
            mask = masks[key]
            rle = annotation["segmentation"]
            counts = rle["counts"]
            require(rle["size"] == list(mask.shape), "RLE size mismatch")
            require(all(type(n) is int and n >= 0 for n in counts), "invalid RLE counts")
            require(sum(counts) == mask.size, "RLE length mismatch")
            decoded = np.repeat(np.arange(len(counts)) % 2, counts).reshape(mask.shape, order="F").astype(bool)
            require(np.array_equal(mask, decoded), "RLE and PNG differ")
            ys, xs = np.nonzero(mask)
            require(annotation["area"] == len(xs), "COCO area mismatch")
            require(annotation["bbox"] == [int(xs.min()), int(ys.min()), int(xs.max()-xs.min()+1), int(ys.max()-ys.min()+1)], "COCO bbox mismatch")
        require(seen == {key for key, mask in masks.items() if mask.any()}, "missing nonempty annotations")
        actions = []
        if "first_frame_review.json" in names:
            history = json.loads(archive.read("first_frame_review.json"))
            require(history == json.loads((task / "first_frame_review.json").read_text(encoding="utf-8")), "lost review history")
            actions = [event["action"] for event in history["events"]]
        require(archive.read("preview.mp4") == (task / "exports" / "preview.mp4").read_bytes(), "preview differs")
    return {"status": "passed", "download_sha256": digest, "download_bytes": downloaded.stat().st_size,
            "zip_entries": len(names), "masks_verified": len(masks), "rle_annotations_verified": len(seen),
            "review_actions": actions, "corrections": project["corrections"],
            "source_media_and_draft_previews_excluded": True, "download_matches_generated_bundle": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--downloaded", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = verify(args.task, args.downloaded)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
