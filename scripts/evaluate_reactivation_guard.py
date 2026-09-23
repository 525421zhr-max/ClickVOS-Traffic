"""Audit one raw mask sequence against DAVIS instance truth and the fixed guard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from clickvos.anomaly import ReactivationGuard


def evaluate(
    ground_truth_dir: Path,
    prediction_dir: Path,
    object_id: int,
    minimum_empty_frames: int = 3,
) -> dict[str, object]:
    ground_truth = sorted(ground_truth_dir.glob("*.png"))
    predictions = sorted(prediction_dir.glob("*.png"))
    if not ground_truth or [path.name for path in ground_truth] != [path.name for path in predictions]:
        raise ValueError("ground truth and prediction frame names must match")
    expected_names = [f"{index:05d}.png" for index in range(len(predictions))]
    if [path.name for path in predictions] != expected_names:
        raise ValueError("frames must be numbered contiguously from 00000.png")

    guard = ReactivationGuard(minimum_empty_frames)
    events: list[dict[str, object]] = []
    suppressed_frame_count = 0
    correct_candidate_suppressed_frames = 0
    first_frame_iou: float | None = None
    for frame_index, (gt_path, pred_path) in enumerate(zip(ground_truth, predictions)):
        gt = np.asarray(Image.open(gt_path)) == object_id
        pred = np.asarray(Image.open(pred_path)) > 0
        if gt.shape != pred.shape:
            raise ValueError(f"mask size mismatch at {gt_path.name}")
        intersection = int(np.logical_and(gt, pred).sum())
        union = int(np.logical_or(gt, pred).sum())
        iou = intersection / union if union else 1.0
        if frame_index == 0:
            first_frame_iou = iou if gt.any() else 0.0
        decision = guard.observe(frame_index, int(pred.sum()))
        if decision.suppress:
            suppressed_frame_count += 1
            if int(gt.sum()) > 0 and iou >= 0.5:
                correct_candidate_suppressed_frames += 1
        if decision.triggered:
            events.append(
                {
                    "frame_index": frame_index,
                    "preceding_empty_frames": decision.empty_frame_count,
                    "ground_truth_visible": bool(gt.any()),
                    "candidate_pixels": int(pred.sum()),
                    "ground_truth_pixels": int(gt.sum()),
                    "candidate_iou": iou,
                    "correct_object_blocked": bool(gt.any()) and iou >= 0.5,
                }
            )
    prompt_gate_passed = first_frame_iou is not None and first_frame_iou >= 0.7
    correct_trigger_count = sum(bool(event["correct_object_blocked"]) for event in events)
    if not prompt_gate_passed:
        status = "invalid_initial_prompt"
    elif not events:
        status = "inconclusive_no_reactivation_event"
    elif correct_trigger_count:
        status = "correct_object_suppressed_on_this_sequence"
    else:
        status = "no_correct_object_suppression_observed_on_this_sequence"
    return {
        "schema_version": 1,
        "object_id": object_id,
        "frame_count": len(predictions),
        "minimum_empty_frames": minimum_empty_frames,
        "first_frame_iou": first_frame_iou,
        "prompt_gate_passed": prompt_gate_passed,
        "guard_false_block_status": status,
        "trigger_count": len(events),
        "correct_object_blocked_trigger_count": correct_trigger_count,
        "suppressed_frame_count": suppressed_frame_count,
        "correct_candidate_suppressed_frame_count": correct_candidate_suppressed_frames,
        "events": events,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ground-truth-dir", required=True, type=Path)
    parser.add_argument("--prediction-dir", required=True, type=Path)
    parser.add_argument("--object-id", required=True, type=int)
    parser.add_argument("--minimum-empty-frames", type=int, default=3)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = evaluate(
        args.ground_truth_dir,
        args.prediction_dir,
        args.object_id,
        args.minimum_empty_frames,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
