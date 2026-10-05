"""Evaluate a frozen, at-most-three-negative-click first-frame correction budget.

Every stage starts a fresh session with the complete prompt list, matching the
Web first-frame rerun semantics. No temporal propagation is performed.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import platform
import shutil
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image

from clickvos.config import load_config
from clickvos.sam2_engine import (
    ObjectPrompt,
    PromptPoint,
    Sam2Engine,
    file_sha256,
    save_boolean_mask_and_overlay,
)
if __package__ in (None, ""):
    from run_sam2_multi_frames import load_prompts
else:
    from scripts.run_sam2_multi_frames import load_prompts


def mask_metrics(mask: np.ndarray, labels: np.ndarray, object_id: int) -> dict[str, Any]:
    valid = labels != 255
    truth = labels == object_id
    tp = int(np.count_nonzero(mask & truth & valid))
    fp = int(np.count_nonzero(mask & ~truth & valid))
    fn = int(np.count_nonzero(~mask & truth & valid))
    union = tp + fp + fn
    return {
        "true_positive_pixels": tp,
        "false_positive_pixels": fp,
        "false_negative_pixels": fn,
        "ground_truth_pixels": int(truth.sum()),
        "prediction_pixels": int(mask.sum()),
        "iou": tp / union if union else 1.0,
    }


def _read_mask(path: Path, shape: tuple[int, int]) -> np.ndarray:
    with Image.open(path) as image:
        values = np.asarray(image)
    if values.shape != shape or values.ndim != 2:
        raise ValueError(f"baseline mask shape mismatch: {path}")
    if not set(np.unique(values)).issubset({0, 1, 255}):
        raise ValueError(f"baseline mask must be binary: {path}")
    if 1 in values and 255 in values:
        raise ValueError(f"baseline mask mixes binary encodings: {path}")
    return values > 0


def _git_head(directory: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(directory), "rev-parse", "HEAD"],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _environment(device: str) -> dict[str, Any]:
    try:
        sam2_version = importlib.metadata.version("SAM-2")
    except importlib.metadata.PackageNotFoundError:
        sam2_version = None
    spec = importlib.util.find_spec("sam2")
    source = Path(spec.origin).parent if spec is not None and spec.origin else None
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "torch": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0) if device == "cuda" else None,
        "sam2_version": sam2_version,
        "sam2_source_commit": _git_head(source) if source else None,
        "repository_commit": _git_head(Path(__file__).resolve().parents[1]),
        "strict_cuda_determinism_requested": False,
    }


def _prompt_record(prompt: ObjectPrompt, initial_count: int) -> dict[str, Any]:
    points = [asdict(point) for point in prompt.points]
    return {
        "object_id": prompt.object_id,
        "category": prompt.category,
        "frame_index": prompt.frame_index,
        "points": points,
        "initial_click_count": initial_count,
        "added_negative_click_count": len(points) - initial_count,
        "final_click_count": len(points),
        "positive_click_count": sum(point["positive"] for point in points),
        "negative_click_count": sum(not point["positive"] for point in points),
    }


def run_experiment(
    *,
    frame: Path,
    ground_truth: Path,
    baseline_run: Path,
    experiment_config: Path,
    checkpoint: Path,
    output: Path,
    app_config: Path = Path("configs/default.json"),
) -> dict[str, Any]:
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    if frame.name != "00000.jpg" or ground_truth.name != "00000.png":
        raise ValueError("this experiment requires first-frame 00000.jpg and 00000.png")
    experiment = json.loads(experiment_config.read_text(encoding="utf-8"))
    config = load_config(app_config)
    prompt_config = Path(experiment["baseline_prompt_config"])
    sequence, prompts = load_prompts(prompt_config)
    if sequence != experiment["sequence"]:
        raise ValueError("experiment and baseline prompt sequences do not match")
    target_id = experiment["target_object_id"]
    if type(target_id) is not int or target_id not in {p.object_id for p in prompts}:
        raise ValueError("target_object_id must identify one baseline object")
    added_points = experiment["negative_points"]
    if not isinstance(added_points, list) or not 1 <= len(added_points) <= 3:
        raise ValueError("negative point budget must contain 1 to 3 frozen points")
    if any(
        not isinstance(point, list) or len(point) != 2
        or any(type(value) is not int for value in point)
        for point in added_points
    ):
        raise ValueError("negative points must contain integer [x, y] pairs")
    if len({tuple(point) for point in added_points}) != len(added_points):
        raise ValueError("negative points must be distinct")
    gate = experiment["first_frame_iou_gate"]
    tolerance = experiment["baseline_iou_tolerance"]
    if type(gate) not in (int, float) or not 0 < gate <= 1:
        raise ValueError("first_frame_iou_gate must lie in (0, 1]")
    if type(tolerance) not in (int, float) or not 0 <= tolerance <= 0.01:
        raise ValueError("baseline_iou_tolerance must lie in [0, 0.01]")
    seed = experiment["seed"]
    if type(seed) is not int or not 0 <= seed < 2**63:
        raise ValueError("seed must be a nonnegative integer below 2**63")
    with Image.open(frame) as image:
        if image.mode != "RGB":
            raise ValueError("first frame must be RGB")
        width, height = image.size
    with Image.open(ground_truth) as image:
        labels = np.asarray(image)
    if labels.ndim != 2 or labels.shape != (height, width):
        raise ValueError("ground truth must be a single-channel label image matching the frame")
    if not np.issubdtype(labels.dtype, np.integer):
        raise ValueError("ground truth must contain integer labels")
    baseline_masks: dict[int, np.ndarray] = {}
    baseline_records = []
    for prompt in prompts:
        prompt.validate(width, height, {category.key for category in config.categories})
        if prompt.object_id == 255 or not np.any(labels == prompt.object_id):
            raise ValueError("every baseline object must occur in the first-frame ground truth")
        for point in prompt.points:
            if not float(point.x).is_integer() or not float(point.y).is_integer():
                raise ValueError("baseline points must use integer pixel coordinates")
            label = int(labels[int(point.y), int(point.x)])
            if label == 255 or (label == prompt.object_id) != point.positive:
                raise ValueError(f"baseline point label disagrees with ground truth for object {prompt.object_id}")
        mask_path = baseline_run / f"object_{prompt.object_id:03d}" / "masks" / "00000.png"
        mask = _read_mask(mask_path, labels.shape)
        baseline_masks[prompt.object_id] = mask
        baseline_records.append({
            "object_id": prompt.object_id,
            "mask_path": str(mask_path),
            "mask_sha256": file_sha256(mask_path),
            **mask_metrics(mask, labels, prompt.object_id),
        })
    target_prompt = next(prompt for prompt in prompts if prompt.object_id == target_id)
    existing_points = {(point.x, point.y) for point in target_prompt.points}
    for x, y in added_points:
        if not 0 <= x < width or not 0 <= y < height:
            raise ValueError("negative point lies outside the first frame")
        if (x, y) in existing_points:
            raise ValueError("new negative point duplicates an existing target prompt")
        if labels[y, x] != 0 or not baseline_masks[target_id][y, x]:
            raise ValueError("new negative point must be GT background inside the old target false-positive mask")

    # SAM2 enumerates a directory, so slicing a list of original frames is unsafe.
    output.mkdir(parents=True, exist_ok=False)
    staged_directory = output / "input_frames"
    staged_directory.mkdir()
    staged_frame = staged_directory / "00000.jpg"
    shutil.copy2(frame, staged_frame)
    initial_counts = {prompt.object_id: len(prompt.points) for prompt in prompts}
    report: dict[str, Any] = {
        "schema_version": 1,
        "experiment_kind": "gt_assisted_first_frame_negative_correction",
        "sequence": sequence,
        "frame_count": 1,
        "frame_size_wh": [width, height],
        "temporal_propagation_count": 0,
        "postprocessing": "none",
        "void_policy": "ignore_ground_truth_label_255_in_iou",
        "session_policy": "fresh_session_per_stage_complete_prompts_once_per_object",
        "status": "running",
        "experiment_config": experiment,
        "experiment_config_sha256": file_sha256(experiment_config),
        "baseline_prompt_config_sha256": file_sha256(prompt_config),
        "frame_sha256": file_sha256(frame),
        "ground_truth_sha256": file_sha256(ground_truth),
        "model": asdict(config.model),
        "baseline_objects": baseline_records,
        "stages": [],
        "maximum_added_negative_clicks": len(added_points),
        "maximum_stage_count": 1 + len(added_points),
        "initial_click_count": sum(initial_counts.values()),
        "added_negative_click_count": 0,
        "final_click_count": sum(initial_counts.values()),
    }
    result_path = output / "result.json"

    def write_report() -> None:
        result_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")

    write_report()
    try:
        torch.manual_seed(seed)
        engine, load_seconds = Sam2Engine.load(config, checkpoint)
        report["model_load_seconds"] = load_seconds
        report["environment"] = _environment(config.model.device)
        if config.model.device == "cuda":
            torch.cuda.reset_peak_memory_stats()
        for added_count in range(1 + len(added_points)):
            stage_prompts = tuple(
                ObjectPrompt(
                    prompt.object_id, prompt.category, 0,
                    prompt.points + tuple(
                        PromptPoint(x, y, False) for x, y in added_points[:added_count]
                    ) if prompt.object_id == target_id else prompt.points,
                )
                for prompt in prompts
            )
            stage_root = output / f"stage_{added_count:02d}"
            stage_root.mkdir()
            started = time.perf_counter()
            with torch.inference_mode():
                session = engine.start_session([staged_frame])
                for prompt in stage_prompts:
                    prediction = session.add_prompt(prompt)
                expected_ids = set(initial_counts)
                if (
                    prediction.frame_index != 0
                    or set(prediction.object_ids) != expected_ids
                    or len(prediction.object_ids) != len(expected_ids)
                    or len(prediction.masks) != len(expected_ids)
                ):
                    raise RuntimeError("predictor returned unexpected first-frame object IDs or mask count")
                objects = []
                for object_id, mask in zip(prediction.object_ids, prediction.masks, strict=True):
                    if mask.shape != labels.shape or mask.dtype != np.bool_:
                        raise RuntimeError("predictor returned an invalid first-frame mask")
                    object_root = stage_root / f"object_{object_id:03d}"
                    mask_path = object_root / "masks" / "00000.png"
                    overlay_path = object_root / "overlays" / "00000.jpg"
                    mask_path.parent.mkdir(parents=True)
                    overlay_path.parent.mkdir()
                    save_boolean_mask_and_overlay(mask, staged_frame, mask_path, overlay_path)
                    metrics = mask_metrics(mask, labels, object_id)
                    original = next(item for item in baseline_records if item["object_id"] == object_id)
                    prompt = next(item for item in stage_prompts if item.object_id == object_id)
                    objects.append({
                        **_prompt_record(prompt, initial_counts[object_id]),
                        **metrics,
                        "iou_change_from_dev28": metrics["iou"] - original["iou"],
                        "pixel_difference_from_dev28": int(np.count_nonzero(mask != baseline_masks[object_id])),
                        "mask": mask_path.relative_to(output).as_posix(),
                        "overlay": overlay_path.relative_to(output).as_posix(),
                    })
                del session, prediction
            stage = {
                "stage_index": added_count,
                "added_negative_click_count": added_count,
                "added_negative_points": added_points[:added_count],
                "initial_click_count": sum(initial_counts.values()),
                "final_click_count": sum(initial_counts.values()) + added_count,
                "elapsed_seconds_including_session_init_and_save": time.perf_counter() - started,
                "all_objects_pass_first_frame_gate": all(item["iou"] >= gate for item in objects),
                "objects": objects,
            }
            report["stages"].append(stage)
            report["added_negative_click_count"] = added_count
            report["final_click_count"] = stage["final_click_count"]
            report["final_prompts"] = [_prompt_record(prompt, initial_counts[prompt.object_id]) for prompt in stage_prompts]
            report["final_stage_index"] = added_count
            if added_count == 0 and any(abs(item["iou_change_from_dev28"]) > tolerance for item in objects):
                report["status"] = "baseline_mismatch"
                report["stop_reason"] = "fresh first-frame baseline exceeded frozen IoU tolerance"
                write_report()
                break
            if stage["all_objects_pass_first_frame_gate"]:
                report["status"] = "gate_passed"
                report["stop_reason"] = "all first-frame objects reached the frozen IoU gate"
                write_report()
                break
            write_report()
        else:
            report["status"] = "budget_exhausted"
            report["stop_reason"] = "frozen negative-click budget exhausted before all objects passed"
        report["completed_stage_count"] = len(report["stages"])
        report["peak_cuda_memory_bytes"] = (
            int(torch.cuda.max_memory_allocated()) if config.model.device == "cuda" else None
        )
        write_report()
    except Exception as exc:
        report["status"] = "execution_failed"
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        write_report()
        raise
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("frame", "ground-truth", "baseline-run", "experiment-config", "checkpoint", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--app-config", type=Path, default=Path("configs/default.json"))
    report = run_experiment(**vars(parser.parse_args()))
    print(json.dumps({key: report[key] for key in (
        "status", "completed_stage_count", "added_negative_click_count", "temporal_propagation_count"
    )}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
