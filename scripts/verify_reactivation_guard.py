"""Run the Web reactivation guard against the registered CP-02 regression video."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from clickvos.web_app import _prepare_video, _run_segmentation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    _, task_state, _, _ = _prepare_video(args.video, "configs/default.json")
    _, report, status, _ = _run_segmentation(
        task_state,
        [{"x": 520, "y": 370, "positive": True}],
        "vehicle",
        args.checkpoint,
        "configs/default.json",
        True,
        True,
    )
    names = [f"{index:05d}.png" for index in range(46, 50)]
    summary = {
        "task_root": task_state["task_root"],
        "source_id": "traffic-001",
        "reactivation_guard_enabled": report["reactivation_guard_enabled"],
        "minimum_empty_frames": report["reactivation_guard_minimum_empty_frames"],
        "model_pixels_frames_46_to_49": [
            report["model_mask_foreground_pixels"][name] for name in names
        ],
        "final_pixels_frames_46_to_49": [
            report["mask_foreground_pixels"][name] for name in names
        ],
        "guarded_frames": report["guarded_frames"],
        "anomalies": report["anomalies"],
        "status": status,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
