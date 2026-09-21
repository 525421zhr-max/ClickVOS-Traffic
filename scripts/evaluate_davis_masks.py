"""Evaluate one DAVIS object with the official DAVIS J and F implementations."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path

import numpy as np
from PIL import Image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ground-truth-dir", required=True, type=Path)
    parser.add_argument("--prediction-dir", required=True, type=Path)
    parser.add_argument("--object-id", required=True, type=int)
    parser.add_argument("--sequence", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--include-endpoints", action="store_true")
    args = parser.parse_args()

    try:
        from davis2017.metrics import db_eval_boundary, db_eval_iou
    except ImportError as exc:
        raise SystemExit(
            "Install the pinned official davis2017-evaluation package in a separate environment."
        ) from exc

    ground_truth = sorted(args.ground_truth_dir.glob("*.png"))
    predictions = sorted(args.prediction_dir.glob("*.png"))
    if not ground_truth or len(ground_truth) != len(predictions):
        raise SystemExit(
            f"mask count mismatch: ground_truth={len(ground_truth)}, predictions={len(predictions)}"
        )
    if [path.name for path in ground_truth] != [path.name for path in predictions]:
        raise SystemExit("ground-truth and prediction filenames do not match")

    frame_indices = list(range(len(ground_truth)))
    if not args.include_endpoints:
        frame_indices = frame_indices[1:-1]
    j_scores: list[float] = []
    f_scores: list[float] = []
    per_frame: list[dict[str, float | int | str]] = []
    for index in frame_indices:
        gt = np.asarray(Image.open(ground_truth[index])) == args.object_id
        prediction = np.asarray(Image.open(predictions[index])) > 0
        if gt.shape != prediction.shape:
            raise SystemExit(
                f"shape mismatch at {ground_truth[index].name}: gt={gt.shape}, pred={prediction.shape}"
            )
        j_score = float(db_eval_iou(gt, prediction))
        f_score = float(db_eval_boundary(gt, prediction))
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
    report = {
        "schema_version": 1,
        "sequence": args.sequence,
        "object_id": args.object_id,
        "evaluated_frame_count": len(frame_indices),
        "excluded_endpoints": not args.include_endpoints,
        "official_davis_package_version": importlib.metadata.version("davis2017"),
        "mean_j": mean_j,
        "mean_f": mean_f,
        "mean_j_and_f": (mean_j + mean_f) / 2,
        "per_frame": per_frame,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
