"""Read finished ClickVOS tasks without restoring a live SAM2 session."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
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


@dataclass(frozen=True)
class CleanupPreview:
    task_id: str
    file_count: int
    size_bytes: int
    latest_mtime_ns: int
    trash_root: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArchivedTask:
    task_id: str
    archived_root: Path
    file_count: int
    size_bytes: int


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


def _task_usage(root: Path) -> tuple[int, int, int]:
    file_count = 0
    size_bytes = 0
    latest_mtime_ns = root.stat().st_mtime_ns
    for current_root, directories, files in os.walk(root, followlinks=False):
        current = Path(current_root)
        directories[:] = [name for name in directories if not (current / name).is_symlink()]
        for name in files:
            path = current / name
            try:
                stat = path.lstat()
            except OSError as exc:
                raise TaskStoreError(
                    ErrorCode.TASK_INVALID,
                    "无法完整读取任务占用空间，请稍后重试。",
                    str(path),
                ) from exc
            file_count += 1
            size_bytes += stat.st_size
            latest_mtime_ns = max(latest_mtime_ns, stat.st_mtime_ns)
    return file_count, size_bytes, latest_mtime_ns


def preview_task_cleanup(tasks_root: Path, task_id: str) -> CleanupPreview:
    root = resolve_task_root(tasks_root, task_id)
    file_count, size_bytes, latest_mtime_ns = _task_usage(root)
    trash_root = tasks_root.expanduser().resolve().parent / "task_trash"
    return CleanupPreview(
        task_id=task_id,
        file_count=file_count,
        size_bytes=size_bytes,
        latest_mtime_ns=latest_mtime_ns,
        trash_root=str(trash_root),
    )


def archive_task(
    tasks_root: Path,
    task_id: str,
    confirmation: str,
    expected: CleanupPreview,
    *,
    active_task_ids: set[str] | None = None,
) -> ArchivedTask:
    if confirmation != task_id:
        raise TaskStoreError(
            ErrorCode.TASK_INVALID,
            "确认文字不匹配，请完整输入任务编号。",
            task_id,
        )
    if expected.task_id != task_id:
        raise TaskStoreError(
            ErrorCode.TASK_INVALID,
            "当前选择与清理预览不一致，请重新预览。",
            task_id,
        )
    if task_id in (active_task_ids or set()):
        raise TaskStoreError(
            ErrorCode.TASK_CONFLICT,
            "当前任务仍在活动推理会话中，不能清理。",
            task_id,
        )

    root = resolve_task_root(tasks_root, task_id)
    actual = preview_task_cleanup(tasks_root, task_id)
    if (
        actual.file_count != expected.file_count
        or actual.size_bytes != expected.size_bytes
        or actual.latest_mtime_ns != expected.latest_mtime_ns
    ):
        raise TaskStoreError(
            ErrorCode.TASK_CONFLICT,
            "任务内容在预览后发生变化，请重新预览再确认。",
            task_id,
        )

    trash_root = Path(expected.trash_root).resolve()
    expected_trash = tasks_root.expanduser().resolve().parent / "task_trash"
    if trash_root != expected_trash:
        raise TaskStoreError(
            ErrorCode.TASK_INVALID,
            "任务回收区路径无效，请重新预览。",
            str(trash_root),
        )
    trash_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = trash_root / f"{task_id}-{timestamp}"
    root.replace(destination)
    archive_record = {
        "schema_version": 1,
        "task_id": task_id,
        "archived_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "original_tasks_root": str(tasks_root.expanduser().resolve()),
        "file_count_before_archive": actual.file_count,
        "size_bytes_before_archive": actual.size_bytes,
    }
    (destination / ".archive.json").write_text(
        json.dumps(archive_record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return ArchivedTask(task_id, destination, actual.file_count, actual.size_bytes)
