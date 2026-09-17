from pathlib import Path
from unittest.mock import patch

import numpy as np
import gradio as gr
from PIL import Image

from clickvos.anomaly import ReactivationGuard
from clickvos.sam2_engine import FramePrediction
from clickvos.web_app import (
    _ACTIVE_SESSIONS,
    _add_object,
    _add_object_click,
    _export_active_task,
    _runtime_report,
    _save_runtime_prediction,
    build_demo,
)


def test_gradio_demo_builds_with_expected_title() -> None:
    demo = build_demo(Path("configs/default.json"))
    assert isinstance(demo, gr.Blocks)
    config = demo.get_config_file()
    assert config["title"] == "ClickVOS Traffic"
    labels = {component.get("props", {}).get("label") for component in config["components"]}
    assert {
        "交通视频", "目标类别", "分割预览", "运行结果与异常",
        "修正帧号（从 0 开始）", "点击该帧添加修正提示",
        "重新激活保护（目标连续消失 3 帧后暂停可疑掩码）",
        "当前目标", "目标与提示点统计", "标注结果包（ZIP）",
    } <= labels


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
