from pathlib import Path

import pytest

from clickvos.config import load_config
from clickvos.sam2_engine import ObjectPrompt, PromptPoint


def test_prompt_accepts_positive_and_negative_points() -> None:
    prompt = ObjectPrompt(1, "vehicle", 0, (PromptPoint(10, 20), PromptPoint(30, 40, False)))
    prompt.validate(100, 100, {"vehicle"})


def test_prompt_requires_positive_point() -> None:
    prompt = ObjectPrompt(1, "vehicle", 0, (PromptPoint(10, 20, False),))
    with pytest.raises(ValueError, match="positive"):
        prompt.validate(100, 100, {"vehicle"})


def test_prompt_rejects_out_of_bounds_point() -> None:
    prompt = ObjectPrompt(1, "vehicle", 0, (PromptPoint(100, 20),))
    with pytest.raises(ValueError, match="outside"):
        prompt.validate(100, 100, {"vehicle"})


def test_default_model_hash_is_locked() -> None:
    config = load_config(Path("configs/default.json"))
    assert config.model.checkpoint_sha256 == "7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69"
