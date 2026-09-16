from __future__ import annotations

import json
from pathlib import Path

import pytest

from clickvos.config import load_config
from clickvos.errors import ClickVOSError, ErrorCode


def test_default_config_is_valid() -> None:
    config = load_config(Path("configs/default.json"))
    assert config.schema_version == 1
    assert config.video.max_upload_bytes == 200 * 1024 * 1024
    assert [category.key for category in config.categories] == [
        "vehicle", "pedestrian", "non_motorized"
    ]


def test_config_rejects_missing_category(tmp_path: Path) -> None:
    raw = json.loads(Path("configs/default.json").read_text(encoding="utf-8"))
    raw["categories"].pop()
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ClickVOSError) as captured:
        load_config(path)
    assert captured.value.code == ErrorCode.CONFIG_INVALID
    assert captured.value.as_dict()["message"] == "项目配置无效，请检查配置文件。"


def test_config_error_has_stable_machine_code(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    with pytest.raises(ClickVOSError) as captured:
        load_config(path)
    assert captured.value.as_dict()["code"] == "config_invalid"
