"""Load and validate the dependency-free ClickVOS application configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clickvos.errors import ClickVOSError, ErrorCode


REQUIRED_CATEGORY_KEYS = {"vehicle", "pedestrian", "non_motorized"}


@dataclass(frozen=True)
class CategoryConfig:
    id: int
    key: str
    label_zh: str


@dataclass(frozen=True)
class VideoConfig:
    max_upload_bytes: int
    frame_format: str
    jpeg_quality: int


@dataclass(frozen=True)
class ModelConfig:
    name: str
    config: str
    checkpoint_sha256: str
    device: str
    offload_video_to_cpu: bool
    offload_state_to_cpu: bool


@dataclass(frozen=True)
class AppConfig:
    schema_version: int
    tasks_root: Path
    video: VideoConfig
    model: ModelConfig
    categories: tuple[CategoryConfig, ...]


def _invalid(detail: str) -> ClickVOSError:
    return ClickVOSError(ErrorCode.CONFIG_INVALID, "项目配置无效，请检查配置文件。", detail)


def load_config(path: Path) -> AppConfig:
    try:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        categories = tuple(CategoryConfig(**item) for item in raw["categories"])
        config = AppConfig(
            schema_version=int(raw["schema_version"]),
            tasks_root=Path(raw["task"]["tasks_root"]),
            video=VideoConfig(**raw["video"]),
            model=ModelConfig(**raw["model"]),
            categories=categories,
        )
    except FileNotFoundError as exc:
        raise _invalid(f"配置文件不存在：{path}") from exc
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise _invalid(str(exc)) from exc

    if config.schema_version != 1:
        raise _invalid(f"不支持 schema_version={config.schema_version}")
    if config.video.max_upload_bytes <= 0:
        raise _invalid("max_upload_bytes 必须大于 0")
    if config.video.frame_format != "jpg":
        raise _invalid("当前只支持 jpg 抽帧格式")
    if not 2 <= config.video.jpeg_quality <= 31:
        raise _invalid("jpeg_quality 必须在 2 到 31 之间")
    if config.model.device not in {"cuda", "cpu"}:
        raise _invalid("model.device 只能是 cuda 或 cpu")
    if len(config.model.checkpoint_sha256) != 64:
        raise _invalid("checkpoint_sha256 必须是 64 位十六进制摘要")

    category_ids = [category.id for category in config.categories]
    category_keys = {category.key for category in config.categories}
    if len(category_ids) != len(set(category_ids)):
        raise _invalid("类别 ID 不得重复")
    if category_keys != REQUIRED_CATEGORY_KEYS:
        raise _invalid("类别必须且只能包含 vehicle、pedestrian、non_motorized")
    return config
