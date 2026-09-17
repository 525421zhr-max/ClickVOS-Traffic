from pathlib import Path

import numpy as np
import gradio as gr
from PIL import Image

from clickvos.anomaly import ReactivationGuard
from clickvos.sam2_engine import FramePrediction
from clickvos.web_app import _save_runtime_prediction, build_demo


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
    runtime = {
        "frames": frames,
        "task_root": task_root,
        "keep_largest": False,
        "mask_foreground_pixels": {},
        "model_mask_foreground_pixels": {},
        "raw_mask_foreground_pixels": {},
        "mask_component_counts": {},
        "model_mask_component_counts": {},
        "reactivation_guard": ReactivationGuard(3),
        "guarded_frames": [],
        "guard_confirmed_frames": set(),
    }
    masks = [np.ones((4, 4), dtype=bool)] + [np.zeros((4, 4), dtype=bool)] * 3
    masks.append(np.ones((4, 4), dtype=bool))
    for index, mask in enumerate(masks):
        _save_runtime_prediction(runtime, FramePrediction(index, (1,), (mask,)))

    assert runtime["model_mask_foreground_pixels"]["00004.png"] == 16
    assert runtime["mask_foreground_pixels"]["00004.png"] == 0
    assert runtime["guarded_frames"][0]["frame_index"] == 4
    candidate = np.asarray(Image.open(task_root / "review_candidates" / "masks" / "00004.png"))
    final = np.asarray(Image.open(task_root / "masks" / "00004.png"))
    assert int(candidate.sum()) > 0
    assert int(final.sum()) == 0
