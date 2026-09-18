from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from clickvos.errors import ErrorCode
from clickvos.task_store import TaskStoreError, list_tasks, load_task, resolve_task_root


def _write_task(
    tasks_root: Path,
    task_id: str,
    *,
    completed: bool = True,
    updated_at: float = 1_700_000_000,
) -> Path:
    root = tasks_root / task_id
    (root / "exports").mkdir(parents=True)
    (root / "task.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": task_id,
                "status": "frames_extracted",
                "video": {"path": "/data/traffic.mp4", "frame_count": 12},
                "extracted_frame_count": 12,
            }
        ),
        encoding="utf-8",
    )
    if completed:
        (root / "result.json").write_text(
            json.dumps(
                {
                    "object_count": 2,
                    "anomaly_count": 1,
                    "objects": [
                        {"object_id": 1, "category": "vehicle"},
                        {"object_id": 2, "category": "pedestrian"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        (root / "exports" / "preview.mp4").write_bytes(b"preview")
    os.utime(root / "task.json", (updated_at, updated_at))
    os.utime(root, (updated_at, updated_at))
    return root


def test_task_store_lists_recent_valid_tasks_and_skips_broken_ones(tmp_path: Path) -> None:
    _write_task(tmp_path, "older", completed=False, updated_at=1_700_000_000)
    _write_task(tmp_path, "newer", completed=True, updated_at=1_700_000_100)
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "task.json").write_text("not json", encoding="utf-8")

    summaries, skipped = list_tasks(tmp_path)

    assert [summary.task_id for summary in summaries] == ["newer", "older"]
    assert summaries[0].has_result is True
    assert summaries[0].has_preview is True
    assert summaries[0].video_name == "traffic.mp4"
    assert summaries[1].status == "frames_extracted"
    assert skipped == 1


def test_load_task_returns_read_only_paths_and_summary(tmp_path: Path) -> None:
    root = _write_task(tmp_path, "task-001")
    task = load_task(tmp_path, "task-001")

    assert task.root == root.resolve()
    assert task.preview == root / "exports" / "preview.mp4"
    assert task.summary.frame_count == 12
    assert task.summary.object_count == 2
    assert task.summary.anomaly_count == 1
    assert "2 个目标" in task.summary.choice_label


def test_resolve_task_root_rejects_traversal_and_missing_task(tmp_path: Path) -> None:
    with pytest.raises(TaskStoreError) as traversal:
        resolve_task_root(tmp_path, "../outside")
    assert traversal.value.code == ErrorCode.TASK_INVALID

    with pytest.raises(TaskStoreError) as missing:
        resolve_task_root(tmp_path, "missing")
    assert missing.value.code == ErrorCode.TASK_NOT_FOUND
