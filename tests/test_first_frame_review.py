import copy
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from PIL import Image

from clickvos.config import load_config
from clickvos.first_frame_review import append_review_event, preview_first_frame, read_review_history


class PreviewPredictor:
    def __init__(self):
        self.states = []

    def init_state(self, video_path, **kwargs):
        assert [p.name for p in Path(video_path).iterdir()] == ["00000.jpg"]
        state = {"ids": [], "points": []}
        self.states.append(state)
        return state

    def add_new_points_or_box(self, state, **kwargs):
        assert kwargs["obj_id"] not in state["ids"]
        state["ids"].append(kwargs["obj_id"])
        state["points"].append(kwargs["points"].copy())
        logits = torch.full((len(state["ids"]), 1, 8, 8), -1.0)
        logits[:, :, 1:3, 1:3] = 1
        logits[:, :, 6, 6] = 1
        return 0, state["ids"], logits

    def propagate_in_video(self, *args, **kwargs):
        raise AssertionError("preview must not propagate")


@pytest.fixture
def setup(tmp_path):
    source = tmp_path / "frames"
    source.mkdir()
    for index in range(2):
        Image.new("RGB", (8, 8), "white").save(source / f"{index:05d}.jpg")
    for relative in ["result.json", "masks/object_001/00000.png", "overlays/00000.jpg", "exports/preview.mp4"]:
        p = tmp_path / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"existing-result")
    config = load_config(Path("configs/default.json"))
    config = replace(config, model=replace(config.model, device="cpu"))
    predictor = PreviewPredictor()
    active = SimpleNamespace(config=config, predictor=predictor, frames=sorted(source.glob("*.jpg")), state={"original": True})
    objects = [{"object_id": 1, "category": "vehicle", "points": [{"x": 1, "y": 1, "positive": True}]}]
    return tmp_path, active, objects


def test_preview_isolates_state_files_and_postprocessing(setup):
    task, active, objects = setup
    before = {p: p.read_bytes() for p in task.rglob("*") if p.is_file()}
    original_state = copy.deepcopy(active.state)
    first = preview_first_frame(active, objects, task, False)
    second = preview_first_frame(active, objects, task, True)
    assert first["preview_id"] != second["preview_id"]
    assert len(active.predictor.states) == 2
    assert active.predictor.states[0] is not active.predictor.states[1]
    assert active.state == original_state
    assert all(p.read_bytes() == content for p, content in before.items())
    assert first["report"]["objects"][0]["mask_pixels"] == 5
    assert second["report"]["objects"][0]["mask_pixels"] == 4
    assert second["report"]["objects"][0]["raw_mask_pixels"] == 5
    assert second["report"]["temporal_propagation_count"] == 0
    mask = task / "first_frame_previews" / second["preview_id"] / second["report"]["objects"][0]["mask"]
    assert np.count_nonzero(np.asarray(Image.open(mask))) == 4


@pytest.mark.parametrize("change", ["outside", "nan", "duplicate", "negative_only"])
def test_invalid_prompts_rejected_before_inference_or_output(setup, change):
    task, active, objects = setup
    if change == "outside":
        objects[0]["points"][0]["x"] = 8
    elif change == "nan":
        objects[0]["points"][0]["x"] = float("nan")
    elif change == "duplicate":
        objects.append(copy.deepcopy(objects[0]))
    else:
        objects[0]["points"][0]["positive"] = False
    with pytest.raises(ValueError):
        preview_first_frame(active, objects, task)
    assert not active.predictor.states
    assert not (task / "first_frame_previews").exists()


def test_journal_preserves_independent_snapshots_and_serializes_appends(setup):
    task, _, objects = setup
    append_review_event(task, "add", objects, point=objects[0]["points"][0])
    objects[0]["points"].append({"x": 5, "y": 5, "positive": False})
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: append_review_event(task, "preview", objects), range(6)))
    events = read_review_history(task)["events"]
    assert [e["event_id"] for e in events] == list(range(1, 8))
    assert len(events[0]["objects"][0]["points"]) == 1
    assert all(len(e["objects"][0]["points"]) == 2 for e in events[1:])


def test_bad_journal_is_not_overwritten(setup):
    task, _, objects = setup
    p = task / "first_frame_review.json"
    p.write_text('{"schema_version":1,"events":"broken"}', encoding="utf-8")
    before = p.read_bytes()
    with pytest.raises(ValueError, match="记录损坏"):
        append_review_event(task, "add", objects)
    assert p.read_bytes() == before
