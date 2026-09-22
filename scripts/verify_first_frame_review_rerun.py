"""Verify result-area first-frame prompting and same-task SAM2 rerun on real frames."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

from clickvos.web_app import _add_first_frame_review_click, _run_multi_for_web


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames-dir", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--config", default="configs/default.json")
    parser.add_argument("--frame-limit", default=10, type=int)
    args = parser.parse_args()

    source_frames = sorted(args.frames_dir.glob("*.jpg"))[: args.frame_limit]
    if not source_frames or len(source_frames) != args.frame_limit:
        raise SystemExit(
            f"expected {args.frame_limit} JPEG frames, found {len(source_frames)} in {args.frames_dir}"
        )
    expected = [f"{index:05d}.jpg" for index in range(len(source_frames))]
    if [frame.name for frame in source_frames] != expected:
        raise SystemExit("frames must be named contiguously from 00000.jpg")

    for name in ("input_frames", "masks", "overlays", "exports"):
        directory = args.output / name
        directory.mkdir(parents=True, exist_ok=True)
        if any(directory.iterdir()):
            raise SystemExit(f"output directory is not empty: {directory}")
    staged_frames = args.output / "input_frames"
    for frame in source_frames:
        shutil.copy2(frame, staged_frames / frame.name)
    frames = sorted(staged_frames.glob("*.jpg"))

    task_state = {
        "task_root": str(args.output),
        "frames": [str(frame) for frame in frames],
        "fps": 10.0,
    }
    objects = [
        {
            "object_id": 1,
            "category": "vehicle",
            "points": [
                {"x": 430, "y": 270, "positive": True},
                {"x": 155, "y": 235, "positive": False},
            ],
        }
    ]
    run_args = (task_state, objects, args.checkpoint, args.config, False, False)
    first_outputs = _run_multi_for_web(*run_args)
    first_report = first_outputs[1]
    first_overlay = first_outputs[7]

    updated_objects = objects
    additions: list[dict[str, object]] = []
    for point in ((305, 270), (560, 285), (320, 320)):
        event = SimpleNamespace(index=point)
        _, updated_objects, _, additions, _ = _add_first_frame_review_click(
            first_overlay,
            "正点",
            1,
            updated_objects,
            additions,
            event,
        )

    second_outputs = _run_multi_for_web(
        task_state,
        updated_objects,
        args.checkpoint,
        args.config,
        False,
        False,
    )
    second_report = second_outputs[1]
    first_pixels = int(
        first_report["objects"][0]["model_mask_foreground_pixels"]["00000.png"]
    )
    second_pixels = int(
        second_report["objects"][0]["model_mask_foreground_pixels"]["00000.png"]
    )
    summary = {
        "schema_version": 1,
        "frame_count": len(frames),
        "initial_positive_points": 1,
        "review_positive_points_added": len(additions),
        "final_positive_points": sum(
            bool(point["positive"]) for point in updated_objects[0]["points"]
        ),
        "negative_points": sum(
            not bool(point["positive"]) for point in updated_objects[0]["points"]
        ),
        "first_run_first_frame_pixels": first_pixels,
        "rerun_first_frame_pixels": second_pixels,
        "first_run_inference_seconds": first_report["initial_inference_seconds"],
        "rerun_inference_seconds": second_report["initial_inference_seconds"],
        "rerun_preview": second_outputs[0],
        "same_task_root": str(args.output),
    }
    result_path = args.output / "review-rerun-result.json"
    result_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
