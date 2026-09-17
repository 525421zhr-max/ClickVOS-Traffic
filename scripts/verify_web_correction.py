"""Exercise the same initial-run and correction callbacks used by the Web UI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from clickvos.web_app import _apply_correction, _prepare_video, _run_segmentation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    _, task_state, _, _ = _prepare_video(args.video, "configs/default.json")
    _, initial_report, _, session_key = _run_segmentation(
        task_state,
        [{"x": 520, "y": 370, "positive": True}],
        "vehicle",
        args.checkpoint,
        "configs/default.json",
        True,
    )
    initial_pixels = initial_report["mask_foreground_pixels"]["00046.png"]
    _, corrected_report, status, _, _, _ = _apply_correction(
        session_key,
        46,
        [{"x": 480, "y": 350, "positive": False}],
    )
    summary = {
        "task_root": task_state["task_root"],
        "correction_frame": 46,
        "correction_prompt": {"x": 480, "y": 350, "positive": False},
        "pixels_before": initial_pixels,
        "pixels_after": corrected_report["mask_foreground_pixels"]["00046.png"],
        "correction_count": len(corrected_report["corrections"]),
        "status": status,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
