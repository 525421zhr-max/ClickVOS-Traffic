import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import gradio as gr
import pytest
from PIL import Image

from clickvos.anomaly import ReactivationGuard
from clickvos.sam2_engine import FramePrediction
from clickvos.web_app import (
    _ACTIVE_SESSIONS,
    _add_object,
    _add_object_click,
    _anomaly_selector_update,
    _archive_history_task,
    _detect_mask_overlaps,
    _export_active_task,
    _export_history_task,
    _load_selected_anomaly,
    _launch_options,
    _open_history_task,
    _preview_history_cleanup,
    _refresh_task_history,
    _restore_guarded_candidate_masks,
    _runtime_report,
    _save_runtime_prediction,
    _undo_guarded_candidate_masks,
    build_demo,
)


def test_launch_options_default_to_local_only(monkeypatch) -> None:
    monkeypatch.delenv("CLICKVOS_HOST", raising=False)
    monkeypatch.delenv("CLICKVOS_PORT", raising=False)
    options = _launch_options()
    assert options["server_name"] == "127.0.0.1"
    assert options["server_port"] == 7860


def test_launch_options_allow_container_binding(monkeypatch) -> None:
    monkeypatch.setenv("CLICKVOS_HOST", "0.0.0.0")
    monkeypatch.setenv("CLICKVOS_PORT", "8080")
    options = _launch_options()
    assert options["server_name"] == "0.0.0.0"
    assert options["server_port"] == 8080


def test_launch_options_reject_invalid_port(monkeypatch) -> None:
    monkeypatch.setenv("CLICKVOS_PORT", "70000")
    with pytest.raises(ValueError, match="1 到 65535"):
        _launch_options()


def test_gradio_demo_builds_with_expected_title() -> None:
    demo = build_demo(Path("configs/default.json"))
    assert isinstance(demo, gr.Blocks)
    config = demo.get_config_file()
    assert config["title"] == "ClickVOS Traffic"
    labels = {component.get("props", {}).get("label") for component in config["components"]}
    values = {component.get("props", {}).get("value") for component in config["components"]}
    assert {
        "交通视频", "目标类别", "分割预览", "运行结果与异常",
        "修正帧号（从 0 开始）", "点击该帧添加修正提示",
        "重新激活保护（目标连续消失 3 帧后暂停可疑掩码）",
        "当前目标", "目标与提示点统计", "标注结果包（ZIP）",
        "待复核异常帧", "本地历史任务", "历史预览", "任务摘要",
        "历史任务标注包（ZIP）",
        "清理范围预览", "输入完整任务编号以确认",
    } <= labels
    assert "撤销本次候选确认" in values


def test_runtime_guard_preserves_candidate_and_writes_empty_final_mask(tmp_path: Path) -> None:
    frames = []
    for index in range(5):
        path = tmp_path / f"{index:05d}.jpg"
        Image.new("RGB", (4, 4), "white").save(path)
        frames.append(path)
    task_root = tmp_path / "task"
    (task_root / "masks").mkdir(parents=True)
    (task_root / "overlays").mkdir()
    def object_runtime(category: str) -> dict[str, object]:
        return {
            "category": category,
            "points": [{"x": 1, "y": 1, "positive": True}],
            "mask_foreground_pixels": {},
            "model_mask_foreground_pixels": {},
            "raw_mask_foreground_pixels": {},
            "mask_component_counts": {},
            "model_mask_component_counts": {},
            "reactivation_guard": ReactivationGuard(3),
            "guarded_frames": [],
            "guard_confirmed_frames": set(),
        }

    first_object = object_runtime("vehicle")
    second_object = object_runtime("pedestrian")
    runtime = {
        "frames": frames,
        "task_root": task_root,
        "keep_largest": False,
        "objects": {1: first_object, 2: second_object},
        "guard_reactivation": True,
        "model_load_seconds": 0.1,
        "initial_inference_seconds": 0.2,
        "peak_cuda_memory_bytes": None,
        "model": {"name": "test-model"},
        "corrections": [],
    }
    first_masks = [np.ones((4, 4), dtype=bool)] + [np.zeros((4, 4), dtype=bool)] * 3
    first_masks.append(np.ones((4, 4), dtype=bool))
    second_mask = np.zeros((4, 4), dtype=bool)
    second_mask[:, :2] = True
    for index, mask in enumerate(first_masks):
        _save_runtime_prediction(
            runtime, FramePrediction(index, (1, 2), (mask, second_mask))
        )

    assert first_object["model_mask_foreground_pixels"]["00004.png"] == 16
    assert first_object["mask_foreground_pixels"]["00004.png"] == 0
    assert first_object["guarded_frames"][0]["frame_index"] == 4
    assert second_object["mask_foreground_pixels"]["00004.png"] == 8
    candidate = np.asarray(Image.open(task_root / "review_candidates" / "masks" / "00004.png"))
    final = np.asarray(Image.open(task_root / "masks" / "00004.png"))
    assert int(candidate.sum()) > 0
    assert int(final.sum()) == 0
    assert (task_root / "masks" / "object_001" / "00004.png").is_file()
    assert (task_root / "masks" / "object_002" / "00004.png").is_file()
    report = _runtime_report(runtime)
    assert report["object_count"] == 2
    assert [item["object_id"] for item in report["objects"]] == [1, 2]
    overlaps = _detect_mask_overlaps(runtime, minimum_overlap_pixels=1)
    assert overlaps[0]["frame_index"] == 0
    assert overlaps[0]["evidence"]["overlap_pixels"] == 8

    restored = _restore_guarded_candidate_masks(runtime, 1, 4)
    assert restored == [4]
    restored_mask = np.asarray(Image.open(task_root / "masks" / "object_001" / "00004.png"))
    assert int(restored_mask.sum()) > 0
    assert report["mask_foreground_pixels"]["00004.png"] == 0
    assert first_object["guarded_frames"] == []
    assert first_object["confirmed_reactivation_frames"] == [4]
    confirmed_report = _runtime_report(runtime)
    assert confirmed_report["anomaly_count"] == 0
    assert confirmed_report["objects"][0]["anomalies"][0]["review_status"] == "confirmed"

    suppressed = _undo_guarded_candidate_masks(runtime, 1, 4)
    assert suppressed == [4]
    suppressed_mask = np.asarray(Image.open(task_root / "masks" / "object_001" / "00004.png"))
    assert int(suppressed_mask.sum()) == 0
    assert first_object["guarded_frames"][0]["frame_index"] == 4
    assert first_object["confirmed_reactivation_frames"] == []
    reverted_report = _runtime_report(runtime)
    assert reverted_report["anomaly_count"] == 1
    assert reverted_report["objects"][0]["anomalies"][0]["review_status"] == "pending"
    assert [action["action"] for action in reverted_report["review_actions"]] == [
        "confirm_reactivation",
        "undo_reactivation_confirmation",
    ]


def test_prompt_points_are_kept_separate_for_each_object(tmp_path: Path) -> None:
    frame = tmp_path / "frame.jpg"
    Image.new("RGB", (20, 20), "white").save(frame)
    _, objects, _, _, _ = _add_object(str(frame), "vehicle", [])
    _, objects, _, _, _ = _add_object(str(frame), "pedestrian", objects)

    class Click:
        index = (4, 5)

    _, objects, _ = _add_object_click(str(frame), "正点", 1, objects, Click())
    Click.index = (15, 12)
    _, objects, _ = _add_object_click(str(frame), "负点", 2, objects, Click())

    assert objects[0]["points"] == [{"x": 4, "y": 5, "positive": True}]
    assert objects[1]["points"] == [{"x": 15, "y": 12, "positive": False}]


def test_web_export_callback_returns_downloadable_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "clickvos-task.zip"
    bundle.write_bytes(b"zip")
    _ACTIVE_SESSIONS["task"] = {"task_root": tmp_path}
    try:
        with patch("clickvos.web_app.build_annotation_bundle", return_value=bundle):
            path, status = _export_active_task("task")
    finally:
        _ACTIVE_SESSIONS.pop("task", None)
    assert path == str(bundle)
    assert "标注包已生成" in status


def test_history_callbacks_list_open_and_export_completed_task(tmp_path: Path) -> None:
    task = tmp_path / "task-001"
    (task / "exports").mkdir(parents=True)
    (task / "task.json").write_text(
        json.dumps(
            {
                "task_id": "task-001",
                "status": "frames_extracted",
                "video": {"path": "/data/traffic.mp4", "frame_count": 2},
                "extracted_frame_count": 2,
            }
        ),
        encoding="utf-8",
    )
    (task / "result.json").write_text(
        json.dumps(
            {
                "object_count": 1,
                "anomaly_count": 0,
                "objects": [{"object_id": 1, "category": "vehicle"}],
                "model": {"name": "test-model"},
            }
        ),
        encoding="utf-8",
    )
    preview = task / "exports" / "preview.mp4"
    preview.write_bytes(b"preview")
    bundle = task / "exports" / "clickvos-task-001.zip"
    bundle.write_bytes(b"zip")
    config = SimpleNamespace(tasks_root=tmp_path)

    with patch("clickvos.web_app.load_config", return_value=config):
        update, refresh_status = _refresh_task_history("test-config.json")
        opened_preview, details, open_status = _open_history_task(
            "test-config.json", "task-001"
        )
        with patch("clickvos.web_app.build_annotation_bundle", return_value=bundle):
            exported, export_status = _export_history_task(
                "test-config.json", "task-001"
            )

    assert update["value"] == "task-001"
    assert "找到 1 个历史任务" in refresh_status
    assert opened_preview == str(preview)
    assert details["read_only"] is True
    assert details["objects"] == [{"object_id": 1, "category": "vehicle"}]
    assert "只读打开" in open_status
    assert exported == str(bundle)
    assert "标注包已生成" in export_status


def test_history_cleanup_callbacks_preview_and_archive_task(tmp_path: Path) -> None:
    task = tmp_path / "task-001"
    task.mkdir()
    (task / "task.json").write_text(
        json.dumps(
            {
                "task_id": "task-001",
                "status": "frames_extracted",
                "video": {"path": "/data/traffic.mp4", "frame_count": 2},
                "extracted_frame_count": 2,
            }
        ),
        encoding="utf-8",
    )
    config = SimpleNamespace(tasks_root=tmp_path)

    with patch("clickvos.web_app.load_config", return_value=config):
        details, state, confirmation, preview_status = _preview_history_cleanup(
            "test-config.json", "task-001"
        )
        with pytest.raises(gr.Error, match="活动推理会话"):
            _archive_history_task(
                "test-config.json",
                "task-001",
                "task-001",
                state,
                {"task_root": str(task)},
            )
        outputs = _archive_history_task(
            "test-config.json", "task-001", "task-001", state, None
        )

    assert details["file_count"] == 1
    assert details["action"] == "move_to_recoverable_trash"
    assert confirmation == ""
    assert "输入任务编号" in preview_status
    assert not task.exists()
    assert outputs[0]["value"] is None
    assert outputs[2] == {}
    assert "尚未永久删除" in outputs[-1]


def test_anomaly_selector_locates_object_and_frame() -> None:
    report = {
        "anomalies": [
            {
                "object_id": 2,
                "kind": "fragmented_mask",
                "frame_index": 3,
            }
        ]
    }
    update = _anomaly_selector_update(report)
    assert update["value"] == "2:3:fragmented_mask"
    task_state = {"frames": [f"frame-{index}.jpg" for index in range(5)]}
    loaded = _load_selected_anomaly(task_state, update["value"])
    assert loaded[0] == 2
    assert loaded[1] == 3
    assert loaded[2] == "frame-3.jpg"
