"""Verify anomaly localization data and guarded-candidate confirmation on CP-02."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from clickvos.web_app import (
    _anomaly_selector_update,
    _confirm_guarded_candidate,
    _prepare_video,
    _run_segmentation,
)


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
        True,
    )
    selector = _anomaly_selector_update(initial_report)
    _, confirmed_report, status, _, _ = _confirm_guarded_candidate(session_key, 1, 46)
    summary = {
        "task_root": task_state["task_root"],
        "source_id": "traffic-001",
        "initial_selector_value": selector.get("value"),
        "initial_pending_anomalies": initial_report["anomaly_count"],
        "frame_46_pixels_before_confirmation": initial_report["mask_foreground_pixels"]["00046.png"],
        "frame_46_pixels_after_confirmation": confirmed_report["mask_foreground_pixels"]["00046.png"],
        "confirmed_reactivations": confirmed_report["confirmed_reactivations"],
        "pending_anomalies_after_confirmation": confirmed_report["anomaly_count"],
        "status": status,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
