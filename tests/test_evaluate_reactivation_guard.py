from pathlib import Path

import numpy as np
from PIL import Image

from scripts.evaluate_reactivation_guard import evaluate


def test_guard_audit_distinguishes_correct_reappearance_from_empty_gap(tmp_path: Path) -> None:
    gt_dir = tmp_path / "truth"
    pred_dir = tmp_path / "prediction"
    gt_dir.mkdir()
    pred_dir.mkdir()
    for index in range(6):
        gt = np.zeros((6, 6), dtype=np.uint8)
        pred = np.zeros((6, 6), dtype=np.uint8)
        if index in (0, 4, 5):
            gt[1:4, 1:4] = 1
            pred[1:4, 1:4] = 255
        Image.fromarray(gt).save(gt_dir / f"{index:05d}.png")
        Image.fromarray(pred).save(pred_dir / f"{index:05d}.png")

    report = evaluate(gt_dir, pred_dir, object_id=1)

    assert report["prompt_gate_passed"] is True
    assert report["trigger_count"] == 1
    assert report["events"][0]["frame_index"] == 4
    assert report["events"][0]["preceding_empty_frames"] == 3
    assert report["events"][0]["candidate_iou"] == 1.0
    assert report["correct_object_blocked_trigger_count"] == 1
    assert report["guard_false_block_status"] == "correct_object_suppressed_on_this_sequence"
    assert report["suppressed_frame_count"] == 2


def test_guard_audit_rejects_missing_prediction_frame(tmp_path: Path) -> None:
    gt_dir = tmp_path / "truth"
    pred_dir = tmp_path / "prediction"
    gt_dir.mkdir()
    pred_dir.mkdir()
    Image.fromarray(np.zeros((2, 2), dtype=np.uint8)).save(gt_dir / "00000.png")
    try:
        evaluate(gt_dir, pred_dir, object_id=1)
    except ValueError as exc:
        assert "frame names" in str(exc)
    else:
        raise AssertionError("missing prediction was not rejected")
