from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

from clickvos.config import load_config
from clickvos.sam2_engine import ObjectPrompt, PromptPoint, Sam2Engine


def test_prompt_accepts_positive_and_negative_points() -> None:
    prompt = ObjectPrompt(1, "vehicle", 0, (PromptPoint(10, 20), PromptPoint(30, 40, False)))
    prompt.validate(100, 100, {"vehicle"})


def test_prompt_requires_positive_point() -> None:
    prompt = ObjectPrompt(1, "vehicle", 0, (PromptPoint(10, 20, False),))
    with pytest.raises(ValueError, match="positive"):
        prompt.validate(100, 100, {"vehicle"})


def test_correction_prompt_may_use_only_negative_points() -> None:
    prompt = ObjectPrompt(1, "vehicle", 2, (PromptPoint(10, 20, False),))
    prompt.validate(100, 100, {"vehicle"}, require_positive=False)


def test_prompt_rejects_out_of_bounds_point() -> None:
    prompt = ObjectPrompt(1, "vehicle", 0, (PromptPoint(100, 20),))
    with pytest.raises(ValueError, match="outside"):
        prompt.validate(100, 100, {"vehicle"})


def test_default_model_hash_is_locked() -> None:
    config = load_config(Path("configs/default.json"))
    assert config.model.checkpoint_sha256 == "7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69"


class FakePredictor:
    def __init__(self) -> None:
        self.ids: list[int] = []
        self.prompt_frames: list[int] = []

    def init_state(self, video_path: str, **kwargs: object) -> dict[str, object]:
        return {"video_path": video_path}

    def add_new_points_or_box(self, state: object, **kwargs: object):
        object_id = int(kwargs["obj_id"])
        if object_id not in self.ids:
            self.ids.append(object_id)
        self.prompt_frames.append(int(kwargs["frame_idx"]))
        logits = torch.ones((len(self.ids), 1, 8, 8))
        return None, list(self.ids), logits

    def propagate_in_video(self, state: object, **kwargs: object):
        start = kwargs.get("start_frame_idx")
        start = 0 if start is None else int(start)
        yield start, list(self.ids), torch.ones((len(self.ids), 1, 8, 8))


def test_session_supports_multiple_objects_and_correction_frame(tmp_path: Path) -> None:
    frames = []
    for index in range(3):
        path = tmp_path / f"{index:05d}.jpg"
        Image.new("RGB", (8, 8)).save(path)
        frames.append(path)
    predictor = FakePredictor()
    session = Sam2Engine(load_config(Path("configs/default.json")), predictor).start_session(frames)
    first = session.add_prompt(ObjectPrompt(1, "vehicle", 0, (PromptPoint(2, 2),)))
    second = session.add_prompt(ObjectPrompt(2, "pedestrian", 0, (PromptPoint(6, 6),)))
    correction = session.add_prompt(ObjectPrompt(1, "vehicle", 2, (PromptPoint(3, 3),)))
    propagated = list(session.propagate(start_frame_idx=2))
    assert first.object_ids == (1,)
    assert second.object_ids == (1, 2)
    assert correction.frame_index == 2
    assert predictor.prompt_frames == [0, 0, 2]
    assert propagated[0].object_ids == (1, 2)
    assert all(mask.dtype == np.bool_ for mask in propagated[0].masks)
