"""Evaluate one DAVIS object with the official DAVIS J and F implementations."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def _load_official_metrics():
    try:
        from davis2017.metrics import db_eval_boundary, db_eval_iou
    except ImportError as exc:
        raise RuntimeError(
            "Install the pinned official davis2017-evaluation package in a separate environment."
        ) from exc
    return db_eval_iou, db_eval_boundary, importlib.metadata.version("davis2017")


def _read_mask(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        mask = np.array(image)
    if mask.ndim != 2:
        raise ValueError(f"mask must be single-channel: {path} has shape {mask.shape}")
    return mask


def evaluate_davis_masks(
    ground_truth_dir: Path,
    prediction_dir: Path,
    object_id: int,
    sequence: str,
    *,
    include_endpoints: bool = False,
) -> dict[str, Any]:
    """Evaluate a validated single-object sequence using the official J/F functions.

    Predictions must be single-channel binary PNGs encoded as 0/1 or 0/255.
    Object existence is checked across the complete ground-truth sequence, even
    when endpoints are excluded. An object may legitimately be absent in a frame.
    DAVIS label 255 is passed as void_pixels to both official metric functions.
    """
    if (
        isinstance(object_id, bool)
        or not isinstance(object_id, int)
        or not 1 <= object_id <= 254
    ):
        raise ValueError(
            "object_id must be an integer from 1 to 254; 0 is background and 255 is void"
        )

    ground_truth = sorted(Path(ground_truth_dir).glob("*.png"))
    predictions = sorted(Path(prediction_dir).glob("*.png"))
    if not ground_truth or len(ground_truth) != len(predictions):
        raise ValueError(
            f"mask count mismatch: ground_truth={len(ground_truth)}, predictions={len(predictions)}"
        )
    if [path.name for path in ground_truth] != [path.name for path in predictions]:
        raise ValueError("ground-truth and prediction filenames do not match")

    frame_indices = list(range(len(ground_truth)))
    if not include_endpoints:
        frame_indices = frame_indices[1:-1]
    if not frame_indices:
        raise ValueError("empty evaluation interval: excluding endpoints requires at least 3 frames")

    # Validate the entire supplied sequence, including excluded endpoints, before
    # computing scores. Keep memory bounded by reading one pair at a time.
    object_exists = False
    for gt_path, prediction_path in zip(ground_truth, predictions):
        gt_labels = _read_mask(gt_path)
        prediction = _read_mask(prediction_path)
        if gt_labels.shape != prediction.shape:
            raise ValueError(
                f"shape mismatch at {gt_path.name}: gt={gt_labels.shape}, pred={prediction.shape}"
            )
        values = set(np.unique(prediction).tolist())
        if not (values <= {0, 1} or values <= {0, 255}):
            raise ValueError(
                f"prediction must be binary 0/1 or 0/255 at {prediction_path.name}; found {sorted(values)}"
            )
        object_exists = object_exists or bool(np.any(gt_labels == object_id))
    if not object_exists:
        raise ValueError(f"object_id {object_id} does not exist in the ground-truth sequence")

    db_eval_iou, db_eval_boundary, package_version = _load_official_metrics()
    j_scores: list[float] = []
    f_scores: list[float] = []
    per_frame: list[dict[str, float | int | str]] = []
    for index in frame_indices:
        gt_labels = _read_mask(ground_truth[index])
        gt = gt_labels == object_id
        prediction = _read_mask(predictions[index]) > 0
        void_pixels = gt_labels == 255
        # Official IoU returns 1 for an empty union after an internal 0/0;
        # suppress that expected warning without accepting non-finite scores.
        with np.errstate(invalid="ignore", divide="ignore"):
            j_score = float(db_eval_iou(gt, prediction, void_pixels=void_pixels))
            f_score = float(db_eval_boundary(gt, prediction, void_pixels=void_pixels))
        if not np.isfinite(j_score) or not np.isfinite(f_score):
            raise ValueError(f"non-finite DAVIS score at {ground_truth[index].name}")
        j_scores.append(j_score)
        f_scores.append(f_score)
        per_frame.append(
            {
                "frame": ground_truth[index].name,
                "j": j_score,
                "f": f_score,
            }
        )

    mean_j = float(np.mean(j_scores))
    mean_f = float(np.mean(f_scores))
    return {
        "schema_version": 1,
        "sequence": sequence,
        "object_id": object_id,
        "evaluated_frame_count": len(frame_indices),
        "excluded_endpoints": not include_endpoints,
        "void_policy": "ignore_ground_truth_label_255",
        "official_davis_package_version": package_version,
        "mean_j": mean_j,
        "mean_f": mean_f,
        "mean_j_and_f": (mean_j + mean_f) / 2,
        "per_frame": per_frame,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ground-truth-dir", required=True, type=Path)
    parser.add_argument("--prediction-dir", required=True, type=Path)
    parser.add_argument("--object-id", required=True, type=int)
    parser.add_argument("--sequence", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--include-endpoints", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = evaluate_davis_masks(
            args.ground_truth_dir,
            args.prediction_dir,
            args.object_id,
            args.sequence,
            include_endpoints=args.include_endpoints,
        )
        serialized_report = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    except (ValueError, OSError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc

    # Complete validation and strict JSON serialization before touching output.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialized_report, encoding="utf-8")
    print(serialized_report)


if __name__ == "__main__":
    main()
