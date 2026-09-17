"""Exercise the Web multi-object path with the registered CP-02 traffic video."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from clickvos.web_app import _prepare_video, _run_multi_segmentation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    _, task_state, _, _ = _prepare_video(args.video, "configs/default.json")
    objects = [
        {
            "object_id": 1,
            "category": "vehicle",
            "points": [{"x": 520, "y": 370, "positive": True}],
        },
        {
            "object_id": 2,
            "category": "vehicle",
            "points": [{"x": 700, "y": 440, "positive": True}],
        },
    ]
    preview, report, status, _ = _run_multi_segmentation(
        task_state,
        objects,
        args.checkpoint,
        "configs/default.json",
        True,
        True,
    )
    task_root = Path(task_state["task_root"])
    summary = {
        "task_root": str(task_root),
        "source_id": "traffic-001",
        "object_count": report["object_count"],
        "object_ids": [item["object_id"] for item in report["objects"]],
        "categories": [item["category"] for item in report["objects"]],
        "frame_count": report["frame_count"],
        "first_six_pixels_by_object": {
            str(item["object_id"]): [
                item["mask_foreground_pixels"][f"{index:05d}.png"] for index in range(6)
            ]
            for item in report["objects"]
        },
        "object_mask_directories_exist": {
            str(item["object_id"]): (
                task_root / "masks" / f"object_{item['object_id']:03d}"
            ).is_dir()
            for item in report["objects"]
        },
        "preview_exists": Path(preview).is_file(),
        "anomaly_count": report["anomaly_count"],
        "status": status,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
