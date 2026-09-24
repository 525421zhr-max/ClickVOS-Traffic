import json
from pathlib import Path

import pytest

from scripts.run_sam2_multi_frames import load_prompts


def test_crossing_prompts_keep_distinct_ids_and_point_labels() -> None:
    sequence, prompts = load_prompts(
        Path("configs/experiments/davis-crossing-three-objects.json")
    )
    assert sequence == "crossing"
    assert [prompt.object_id for prompt in prompts] == [1, 2, 3]
    assert [prompt.category for prompt in prompts] == ["pedestrian", "pedestrian", "vehicle"]
    assert [[point.positive for point in prompt.points] for prompt in prompts] == [
        [True, True, True, False],
        [True, True, True, False],
        [True, True, True, False],
    ]


def test_multi_prompt_config_rejects_duplicate_object_ids(tmp_path: Path) -> None:
    path = tmp_path / "prompts.json"
    path.write_text(json.dumps({
        "sequence": "test",
        "objects": [
            {"object_id": 1, "category": "vehicle", "positive": [[1, 1]]},
            {"object_id": 1, "category": "vehicle", "positive": [[2, 2]]},
        ],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="distinct object IDs"):
        load_prompts(path)
