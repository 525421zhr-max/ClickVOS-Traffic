from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from scripts import evaluate_davis_masks as evaluator


def write_sequence(tmp_path: Path, labels: list[np.ndarray], predictions: list[np.ndarray]):
    gt_dir, pred_dir = tmp_path / "gt", tmp_path / "pred"
    gt_dir.mkdir()
    pred_dir.mkdir()
    for index, label in enumerate(labels):
        Image.fromarray(label.astype(np.uint8)).save(gt_dir / f"{index:05d}.png")
    for index, prediction in enumerate(predictions):
        Image.fromarray(prediction.astype(np.uint8)).save(pred_dir / f"{index:05d}.png")
    return gt_dir, pred_dir


@pytest.fixture
def metric_calls(monkeypatch):
    """Capture the official API boundary without installing DAVIS in the app venv."""
    calls = []

    def metric(gt, prediction, *, void_pixels):
        calls.append((gt.copy(), prediction.copy(), void_pixels.copy()))
        # Sentinel scores make frame selection and aggregation observable.
        return 0.75 if np.any(gt) else 1.0

    monkeypatch.setattr(evaluator, "_load_official_metrics", lambda: (metric, metric, "test"))
    return calls


@pytest.mark.parametrize("object_id", [0, 255, -1, 256, True, 1.5])
def test_rejects_non_object_ids_before_loading_metrics(tmp_path, object_id):
    with pytest.raises(ValueError, match="object_id must be an integer from 1 to 254"):
        evaluator.evaluate_davis_masks(tmp_path, tmp_path, object_id, "test")


def test_rejects_globally_absent_object(tmp_path):
    mask = np.zeros((8, 8), dtype=np.uint8)
    gt, pred = write_sequence(tmp_path, [mask] * 3, [mask] * 3)
    with pytest.raises(ValueError, match="object_id 1 does not exist"):
        evaluator.evaluate_davis_masks(gt, pred, 1, "test")


@pytest.mark.parametrize("count", [1, 2])
def test_rejects_empty_evaluation_interval(tmp_path, count):
    mask = np.ones((8, 8), dtype=np.uint8)
    gt, pred = write_sequence(tmp_path, [mask] * count, [mask] * count)
    with pytest.raises(ValueError, match="empty evaluation interval"):
        evaluator.evaluate_davis_masks(gt, pred, 1, "test")


@pytest.mark.parametrize("present_index", [0, 1, 2])
def test_checks_object_existence_across_whole_sequence(tmp_path, metric_calls, present_index):
    present = np.ones((8, 8), dtype=np.uint8)
    absent = np.zeros_like(present)
    masks = [absent] * 3
    masks[present_index] = present
    gt, pred = write_sequence(tmp_path, masks, masks)
    report = evaluator.evaluate_davis_masks(gt, pred, 1, "test")
    expected = 0.75 if present_index == 1 else 1.0
    assert report["evaluated_frame_count"] == 1
    assert report["per_frame"] == [{"frame": "00001.png", "j": expected, "f": expected}]
    assert report["mean_j_and_f"] == expected


def test_allows_one_frame_when_endpoints_are_included(tmp_path, metric_calls):
    mask = np.ones((8, 8), dtype=np.uint8)
    gt, pred = write_sequence(tmp_path, [mask], [mask])
    report = evaluator.evaluate_davis_masks(gt, pred, 1, "test", include_endpoints=True)
    assert report["evaluated_frame_count"] == 1
    assert report["excluded_endpoints"] is False
    assert report["mean_j_and_f"] == 0.75


@pytest.mark.parametrize("include_endpoints, expected_frames", [(False, ["00001.png"]), (True, ["00000.png", "00001.png", "00002.png"])])
def test_passes_void_mask_to_both_official_metrics(tmp_path, metric_calls, include_endpoints, expected_frames):
    labels = np.zeros((8, 8), dtype=np.uint8)
    labels[1:4, 1:4] = 1
    labels[6:, 6:] = 255
    prediction = ((labels == 1) | (labels == 255)).astype(np.uint8) * 255
    gt, pred = write_sequence(tmp_path, [labels] * 3, [prediction] * 3)
    report = evaluator.evaluate_davis_masks(gt, pred, 1, "test", include_endpoints=include_endpoints)
    assert [frame["frame"] for frame in report["per_frame"]] == expected_frames
    assert report["mean_j"] == report["mean_f"] == report["mean_j_and_f"] == 0.75
    assert report["void_policy"] == "ignore_ground_truth_label_255"
    assert len(metric_calls) == 2 * len(expected_frames)
    for actual_gt, actual_pred, actual_void in metric_calls:
        np.testing.assert_array_equal(actual_gt, labels == 1)
        np.testing.assert_array_equal(actual_pred, prediction > 0)
        np.testing.assert_array_equal(actual_void, labels == 255)


@pytest.mark.parametrize("invalid", ["rgb_prediction", "rgb_ground_truth", "nonbinary", "mixed_binary_encodings", "dimensions", "filename", "count"])
def test_rejects_invalid_sequence_including_excluded_endpoint(tmp_path, invalid):
    mask = np.ones((8, 8), dtype=np.uint8)
    gt, pred = write_sequence(tmp_path, [mask] * 3, [mask] * 3)
    if invalid.startswith("rgb_"):
        target = gt if invalid == "rgb_ground_truth" else pred
        Image.fromarray(np.repeat(mask[:, :, None], 3, axis=2)).save(target / "00000.png")
        match = "single-channel"
    elif invalid in {"nonbinary", "mixed_binary_encodings"}:
        bad = mask.copy()
        bad[0, 0] = 2 if invalid == "nonbinary" else 255
        Image.fromarray(bad).save(pred / "00000.png")
        match = "prediction must be binary"
    elif invalid == "dimensions":
        Image.fromarray(mask[:-1]).save(pred / "00000.png")
        match = "shape mismatch"
    elif invalid == "filename":
        (pred / "00000.png").rename(pred / "wrong.png")
        match = "filenames do not match"
    else:
        (pred / "00000.png").unlink()
        match = "mask count mismatch"
    with pytest.raises(ValueError, match=match):
        evaluator.evaluate_davis_masks(gt, pred, 1, "test")


@pytest.mark.parametrize("failure", ["absent_object", "nonfinite_metric"])
def test_failed_cli_preserves_previous_report(tmp_path, monkeypatch, failure):
    mask = np.ones((8, 8), dtype=np.uint8)
    gt, pred = write_sequence(tmp_path, [mask] * 3, [mask] * 3)
    output = tmp_path / "report.json"
    output.write_text("previous accepted report", encoding="utf-8")
    if failure == "nonfinite_metric":
        def invalid_metric(*args, **kwargs):
            return float("nan")
        monkeypatch.setattr(evaluator, "_load_official_metrics", lambda: (invalid_metric, invalid_metric, "test"))
    with pytest.raises(SystemExit, match="non-finite" if failure == "nonfinite_metric" else "does not exist"):
        evaluator.main([
            "--ground-truth-dir", str(gt), "--prediction-dir", str(pred),
            "--object-id", "1" if failure == "nonfinite_metric" else "2",
            "--sequence", "test", "--output", str(output),
        ])
    assert output.read_text(encoding="utf-8") == "previous accepted report"
