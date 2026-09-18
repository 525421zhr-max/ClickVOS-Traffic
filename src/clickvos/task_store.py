"""Read finished ClickVOS tasks without restoring a live SAM2 session."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from clickvos.errors import ClickVOSError, ErrorCode
from clickvos.video_io import TASK_ID_PATTERN


class TaskStoreError(ClickVOSError):
    """Task history cannot be read safely."""


@dataclass(frozen=True)
class TaskSummary:
    task_id: str
    status: str
    updated_at: str
    video_name: str
    frame_count: int
    object_count: int | None
    anomaly_count: int | None
    has_result: bool
    has_preview: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def choice_label(self) -> str:
        timestamp = datetime.fromisoformat(self.updated_at).strftime("%m-%d %H:%M")
        details = [f"{self.frame_count} 帧"]
        if self.object_count is not None:
            details.append(f"{self.object_count} 个目标")
        if self.anomaly_count is not None:
            details.append(f"{self.anomaly_count} 个待复核")
        return f"{self.task_id} · {timestamp} · {' · '.join(details)}"


@dataclass(frozen=True)
class StoredTask:
    root: Path
    metadata: dict[str, Any]
    result: dict[str, Any] | None
    preview: Path | None
    summary: TaskSummary


def resolve_task_root(tasks_root: Path, task_id: str) -> Path:
    if not TASK_ID_PATTERN.fullmatch(task_id):
        raise TaskStoreError(
            ErrorCode.TASK_INVALID,
            "任务编号无效，请刷新历史任务列表。",
            task_id,
        )
    root = tasks_root.expanduser().resolve()
    candidate = (root / task_id).resolve()
    if candidate.parent != root:
        raise TaskStoreError(
            ErrorCode.TASK_INVALID,
            "任务路径无效，请刷新历史任务列表。",
            str(candidate),
        )
    if not candidate.is_dir():
        raise TaskStoreError(
            ErrorCode.TASK_NOT_FOUND,
            "找不到该历史任务，可能已被移动或清理。",
            str(candidate),
        )
    return candidate


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TaskStoreError(
            ErrorCode.TASK_NOT_FOUND,
            f"历史任务缺少{label}。",
            str(path),
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskStoreError(
            ErrorCode.TASK_INVALID,
            f"历史任务的{label}无法读取。",
            str(path),
        ) from exc
    if not isinstance(payload, dict):
        raise TaskStoreError(
            ErrorCode.TASK_INVALID,
            f"历史任务的{label}格式无效。",
            str(path),
        )
    return payload


def load_task(tasks_root: Path, task_id: str) -> StoredTask:
    root = resolve_task_root(tasks_root, task_id)
    metadata_path = root / "task.json"
    metadata = _read_json(metadata_path, "任务信息")
    if str(metadata.get("task_id")) != task_id:
        raise TaskStoreError(
            ErrorCode.TASK_INVALID,
            "任务目录与任务信息不一致。",
            str(metadata_path),
        )

    result_path = root / "result.json"
    result = _read_json(result_path, "运行结果") if result_path.is_file() else None
    preview_path = root / "exports" / "preview.mp4"
    preview = preview_path if preview_path.is_file() else None
    video = metadata.get("video") if isinstance(metadata.get("video"), dict) else {}
    frame_count = int(metadata.get("extracted_frame_count", video.get("frame_count", 0)) or 0)
    updated_at = datetime.fromtimestamp(metadata_path.stat().st_mtime).astimezone().isoformat(
        timespec="seconds"
    )
    summary = TaskSummary(
        task_id=task_id,
        status="completed" if result is not None else str(metadata.get("status", "unknown")),
        updated_at=updated_at,
        video_name=Path(str(video.get("path", "unknown")).replace("\\", "/")).name,
        frame_count=frame_count,
        object_count=int(result["object_count"]) if result and "object_count" in result else None,
        anomaly_count=int(result["anomaly_count"]) if result and "anomaly_count" in result else None,
        has_result=result is not None,
        has_preview=preview is not None,
    )
    return StoredTask(root, metadata, result, preview, summary)


def list_tasks(tasks_root: Path, maximum: int = 200) -> tuple[list[TaskSummary], int]:
    if maximum < 1:
        raise ValueError("maximum must be positive")
    root = tasks_root.expanduser().resolve()
    if not root.exists():
        return [], 0
    if not root.is_dir():
        raise TaskStoreError(
            ErrorCode.TASK_INVALID,
            "任务目录不是有效文件夹。",
            str(root),
        )

    candidates: list[tuple[float, Path]] = []
    skipped = 0
    for path in root.iterdir():
        try:
            if path.is_dir():
                candidates.append((path.stat().st_mtime, path))
        except OSError:
            skipped += 1
    directories = [
        path for _, path in sorted(candidates, key=lambda item: item[0], reverse=True)
    ]
    summaries: list[TaskSummary] = []
    for directory in directories:
        if len(summaries) >= maximum:
            break
        try:
            summaries.append(load_task(root, directory.name).summary)
        except (TaskStoreError, OSError, TypeError, ValueError):
            skipped += 1
    return summaries, skipped
