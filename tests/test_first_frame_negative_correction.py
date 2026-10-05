import json
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

from clickvos.sam2_engine import Sam2Engine
from scripts import verify_first_frame_negative_correction as experiment


@pytest.fixture
def inputs(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    frame = source / "00000.jpg"
    Image.new("RGB", (6, 6), "white").save(frame)
    Image.new("RGB", (6, 6), "red").save(source / "00001.jpg")
    labels = np.zeros((6, 6), dtype=np.uint8)
    labels[:2, :2] = 1
    labels[4:, 4:] = 2
    ground_truth = tmp_path / "00000.png"
    Image.fromarray(labels).save(ground_truth)
    baseline = tmp_path / "baseline"
    masks = {1: labels == 1, 2: labels == 2}
    masks[1][0, 3:6] = True
    for object_id, mask in masks.items():
        directory = baseline / f"object_{object_id:03d}" / "masks"
        directory.mkdir(parents=True)
        Image.fromarray(mask.astype(np.uint8) * 255).save(directory / "00000.png")
    prompt_path = tmp_path / "prompts.json"
    prompt_path.write_text(json.dumps({
        "sequence": "test",
        "objects": [
            {"object_id": 1, "category": "vehicle", "positive": [[0, 0]], "negative": [[5, 5]]},
            {"object_id": 2, "category": "pedestrian", "positive": [[5, 5]], "negative": [[0, 0]]},
        ],
    }), encoding="utf-8")
    experiment_path = tmp_path / "experiment.json"
    experiment_path.write_text(json.dumps({
        "sequence": "test",
        "baseline_prompt_config": str(prompt_path),
        "target_object_id": 1,
        "negative_points": [[3, 0], [4, 0], [5, 0]],
        "first_frame_iou_gate": 0.7,
        "baseline_iou_tolerance": 0.01,
        "seed": 0,
    }), encoding="utf-8")
    app = json.loads(Path("configs/default.json").read_text(encoding="utf-8"))
    app["model"]["device"] = "cpu"
    app_path = tmp_path / "app.json"
    app_path.write_text(json.dumps(app), encoding="utf-8")
    return {
        "frame": frame,
        "ground_truth": ground_truth,
        "baseline_run": baseline,
        "experiment_config": experiment_path,
        "checkpoint": tmp_path / "fake.pt",
        "output": tmp_path / "run",
        "app_config": app_path,
    }


class NoPropagationPredictor:
    def __init__(self, masks, improve=True, mismatch_object=None):
        self.masks = masks
        self.improve = improve
        self.mismatch_object = mismatch_object
        self.sessions = []
        self.propagation_calls = 0

    def init_state(self, video_path, **kwargs):
        # This catches the historical bug where slicing a frame list still loads
        # every JPEG in the original SAM2 input directory.
        assert [path.name for path in Path(video_path).iterdir()] == ["00000.jpg"]
        state = {"prompts": {}}
        self.sessions.append(state)
        return state

    def add_new_points_or_box(self, state, **kwargs):
        object_id = kwargs["obj_id"]
        assert kwargs["frame_idx"] == 0
        assert kwargs["clear_old_points"] is True
        # Each object must get the complete point set only once per fresh state;
        # otherwise SAM2's prior mask logits would change rerun semantics.
        assert object_id not in state["prompts"]
        state["prompts"][object_id] = kwargs
        masks = []
        for current_id, prompt in state["prompts"].items():
            mask = self.masks[current_id].copy()
            if current_id == 1 and self.improve:
                for x, y in prompt["points"][2:].astype(int):
                    mask[y, x] = False
            if current_id == self.mismatch_object:
                mask[:] = False
            masks.append(mask)
        logits = torch.from_numpy(np.stack(masks)[:, None].astype(np.float32) * 2 - 1)
        return 0, list(state["prompts"]), logits

    def propagate_in_video(self, *args, **kwargs):
        self.propagation_calls += 1
        raise AssertionError("first-frame correction must never propagate")


def install_predictor(monkeypatch, inputs, **options):
    masks = {}
    for object_id in (1, 2):
        path = inputs["baseline_run"] / f"object_{object_id:03d}" / "masks" / "00000.png"
        masks[object_id] = np.asarray(Image.open(path)) > 0
    predictor = NoPropagationPredictor(masks, **options)
    loads = []

    def load(config, checkpoint):
        loads.append(checkpoint)
        return Sam2Engine(config, predictor), 0.01

    monkeypatch.setattr(experiment.Sam2Engine, "load", load)
    monkeypatch.setattr(experiment, "_environment", lambda device: {"test_device": device})
    return predictor, loads


def change_experiment(inputs, **updates):
    path = inputs["experiment_config"]
    content = json.loads(path.read_text(encoding="utf-8"))
    content.update(updates)
    path.write_text(json.dumps(content), encoding="utf-8")


def test_fresh_single_frame_stages_accumulate_clicks_and_stop_at_first_pass(inputs, monkeypatch):
    predictor, loads = install_predictor(monkeypatch, inputs)
    original_hashes = {
        path: experiment.file_sha256(path) for path in inputs["baseline_run"].rglob("*.png")
    }
    report = experiment.run_experiment(**inputs)
    assert report["status"] == "gate_passed"
    assert report["completed_stage_count"] == 3
    assert report["added_negative_click_count"] == 2
    assert report["final_click_count"] == 6
    assert len(loads) == 1
    assert len(predictor.sessions) == 3
    assert predictor.propagation_calls == report["temporal_propagation_count"] == 0
    assert [len(state["prompts"][1]["points"]) for state in predictor.sessions] == [2, 3, 4]
    assert [state["prompts"][1]["labels"].tolist() for state in predictor.sessions] == [
        [1, 0], [1, 0, 0], [1, 0, 0, 0],
    ]
    assert [stage["objects"][0]["false_positive_pixels"] for stage in report["stages"]] == [3, 2, 1]
    assert report["stages"][0]["objects"][0]["pixel_difference_from_dev28"] == 0
    assert report["stages"][-1]["objects"][0]["iou"] == pytest.approx(0.8)
    assert not (inputs["output"] / "stage_03").exists()
    assert json.loads((inputs["output"] / "result.json").read_text()) == report
    for stage in report["stages"]:
        for item in stage["objects"]:
            assert (inputs["output"] / item["mask"]).is_file()
            assert (inputs["output"] / item["overlay"]).is_file()
    assert all(experiment.file_sha256(path) == digest for path, digest in original_hashes.items())


def test_budget_exhaustion_does_not_retry_or_propagate(inputs, monkeypatch):
    predictor, _ = install_predictor(monkeypatch, inputs, improve=False)
    report = experiment.run_experiment(**inputs)
    assert report["status"] == "budget_exhausted"
    assert report["completed_stage_count"] == 4
    assert report["added_negative_click_count"] == 3
    assert len(predictor.sessions) == 4
    assert predictor.propagation_calls == 0


@pytest.mark.parametrize("mismatch_object", [1, 2])
def test_baseline_mismatch_of_either_object_stops_and_preserves_report(inputs, monkeypatch, mismatch_object):
    predictor, _ = install_predictor(monkeypatch, inputs, mismatch_object=mismatch_object)
    report = experiment.run_experiment(**inputs)
    assert report["status"] == "baseline_mismatch"
    assert len(predictor.sessions) == 1
    assert report["added_negative_click_count"] == 0
    assert (inputs["output"] / "result.json").is_file()


def test_already_passing_baseline_stops_without_corrections(inputs, monkeypatch):
    change_experiment(inputs, first_frame_iou_gate=0.5)
    predictor, _ = install_predictor(monkeypatch, inputs)
    report = experiment.run_experiment(**inputs)
    assert report["status"] == "gate_passed"
    assert len(predictor.sessions) == 1
    assert report["added_negative_click_count"] == 0


def test_existing_output_is_never_modified(inputs, monkeypatch):
    predictor, loads = install_predictor(monkeypatch, inputs)
    inputs["output"].mkdir()
    sentinel = inputs["output"] / "result.json"
    sentinel.write_text("preserve this result", encoding="utf-8")
    with pytest.raises(ValueError, match="output already exists"):
        experiment.run_experiment(**inputs)
    assert sentinel.read_text() == "preserve this result"
    assert not loads and not predictor.sessions


@pytest.mark.parametrize("points", [
    [[3, 0], [4, 0], [5, 0], [3, 1]],  # Exceeds the frozen budget.
    [[0, 1]],  # Target foreground.
    [[4, 4]],  # Another object.
    [[2, 2]],  # Background outside the old false-positive mask.
    [[6, 0]],  # Out of bounds.
    [[3, 0], [3, 0]],  # Repeated click.
    [[3.0, 0]],  # Not an integer pixel specification.
])
def test_invalid_new_points_fail_before_model_load_and_output_creation(inputs, monkeypatch, points):
    _, loads = install_predictor(monkeypatch, inputs)
    change_experiment(inputs, negative_points=points)
    with pytest.raises(ValueError):
        experiment.run_experiment(**inputs)
    assert not loads
    assert not inputs["output"].exists()


def test_incorrect_baseline_point_label_is_rejected_before_model_load(inputs, monkeypatch):
    _, loads = install_predictor(monkeypatch, inputs)
    content = json.loads(inputs["experiment_config"].read_text())
    path = Path(content["baseline_prompt_config"])
    prompts = json.loads(path.read_text())
    prompts["objects"][0]["positive"] = [[2, 2]]
    path.write_text(json.dumps(prompts), encoding="utf-8")
    with pytest.raises(ValueError, match="baseline point label"):
        experiment.run_experiment(**inputs)
    assert not loads


def test_ground_truth_shape_mismatch_fails_before_model_load(inputs, monkeypatch):
    _, loads = install_predictor(monkeypatch, inputs)
    Image.new("L", (3, 3)).save(inputs["ground_truth"])
    with pytest.raises(ValueError, match="matching the frame"):
        experiment.run_experiment(**inputs)
    assert not loads


def test_partial_inference_failure_retains_a_failure_report(inputs, monkeypatch):
    predictor, _ = install_predictor(monkeypatch, inputs)

    def fail(*args, **kwargs):
        raise RuntimeError("simulated decoder failure")

    monkeypatch.setattr(predictor, "add_new_points_or_box", fail)
    with pytest.raises(RuntimeError, match="simulated decoder failure"):
        experiment.run_experiment(**inputs)
    report = json.loads((inputs["output"] / "result.json").read_text())
    assert report["status"] == "execution_failed"
    assert report["temporal_propagation_count"] == 0
