"""Gradio user interface for the local ClickVOS Traffic workflow."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr
from PIL import Image, ImageDraw

from clickvos.anomaly import detect_fragmentation, detect_reactivation
from clickvos.config import AppConfig, load_config
from clickvos.errors import ClickVOSError
from clickvos.export import build_preview_video
from clickvos.sam2_engine import ObjectPrompt, PromptPoint, Sam2Engine
from clickvos.video_io import prepare_task


def _friendly_error(exc: Exception) -> gr.Error:
    if isinstance(exc, ClickVOSError):
        return gr.Error(exc.user_message)
    return gr.Error(str(exc))


def _prepare_video(video_path: str | None, config_path: str) -> tuple[str, dict[str, Any], list[dict[str, Any]], str]:
    if not video_path:
        raise gr.Error("请先上传交通视频。")
    try:
        config = load_config(Path(config_path))
        layout, metadata, frames = prepare_task(Path(video_path), config.tasks_root)
        state = {
            "task_root": str(layout.root),
            "frames": [str(frame) for frame in frames],
            "fps": metadata.fps,
            "width": metadata.width,
            "height": metadata.height,
        }
        return str(frames[0]), state, [], f"已创建任务 {layout.root.name}，抽取 {len(frames)} 帧。请在首帧点击目标。"
    except Exception as exc:
        raise _friendly_error(exc) from exc


def _add_click(
    image_path: str | None,
    prompt_kind: str,
    prompts: list[dict[str, Any]] | None,
    event: gr.SelectData,
) -> tuple[Image.Image, list[dict[str, Any]], list[dict[str, Any]]]:
    if not image_path:
        raise gr.Error("请先完成视频抽帧。")
    x, y = int(event.index[0]), int(event.index[1])
    entries = list(prompts or [])
    entries.append({"x": x, "y": y, "positive": prompt_kind == "正点"})
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    for item in entries:
        color = "#00ff66" if item["positive"] else "#ff3344"
        px, py = item["x"], item["y"]
        draw.ellipse((px - 6, py - 6, px + 6, py + 6), fill=color, outline="white", width=2)
    return image, entries, entries


def _clear_clicks(image_path: str | None) -> tuple[str | None, list[Any], list[Any]]:
    return image_path, [], []


def _run_segmentation(
    task_state: dict[str, Any] | None,
    prompts: list[dict[str, Any]] | None,
    category: str,
    checkpoint_path: str,
    config_path: str,
    keep_largest: bool,
) -> tuple[str, dict[str, Any], str]:
    if not task_state:
        raise gr.Error("请先上传并解析视频。")
    if not prompts or not any(item["positive"] for item in prompts):
        raise gr.Error("至少需要一个正点。")
    if not checkpoint_path:
        raise gr.Error("请填写本机 SAM2 权重路径。")
    try:
        config = load_config(Path(config_path))
        engine, load_seconds = Sam2Engine.load(config, Path(checkpoint_path))
        frames = [Path(frame) for frame in task_state["frames"]]
        task_root = Path(task_state["task_root"])
        prompt = ObjectPrompt(
            object_id=1,
            category=category,
            frame_index=0,
            points=tuple(PromptPoint(item["x"], item["y"], item["positive"]) for item in prompts),
        )
        result = engine.propagate_single(
            frames,
            prompt,
            task_root / "masks",
            task_root / "overlays",
            keep_largest_component_only=keep_largest,
        )
        preview = build_preview_video(task_root / "overlays", task_root / "exports" / "preview.mp4", task_state["fps"])
        anomaly_items = detect_reactivation(result.mask_foreground_pixels)
        anomaly_items.extend(detect_fragmentation(result.mask_component_counts))
        anomalies = [asdict(item) for item in anomaly_items]
        report = {
            **result.as_dict(),
            "model_load_seconds": load_seconds,
            "prompt_points": prompts,
            "anomaly_count": len(anomalies),
            "anomalies": anomalies,
        }
        (task_root / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        status = f"传播完成：{result.frame_count} 帧，发现 {len(anomalies)} 个待复核异常。"
        return str(preview), report, status
    except Exception as exc:
        raise _friendly_error(exc) from exc


def build_demo(config_path: Path = Path("configs/default.json")) -> gr.Blocks:
    config: AppConfig = load_config(config_path)
    labels = {category.key: category.label_zh for category in config.categories}
    checkpoint_default = os.environ.get("CLICKVOS_CHECKPOINT", "")
    with gr.Blocks(title="ClickVOS Traffic") as demo:
        gr.Markdown(
            "# ClickVOS Traffic\n"
            "上传许可清晰的交通视频，在首帧用正点和负点选择目标，然后运行 SAM2 传播。"
            "禁止上传私人照片、人像测试素材或未经授权的视频。"
        )
        task_state = gr.State()
        prompt_state = gr.State([])
        first_frame_path = gr.State()
        config_value = gr.State(str(config_path))
        with gr.Row():
            with gr.Column():
                video = gr.Video(label="交通视频", sources=["upload"])
                checkpoint = gr.Textbox(label="SAM2 权重路径", value=checkpoint_default, type="text")
                category = gr.Dropdown(
                    choices=[(label, key) for key, label in labels.items()],
                    value="vehicle",
                    label="目标类别",
                )
                prepare = gr.Button("1. 抽帧并显示首帧", variant="primary")
            with gr.Column():
                frame = gr.Image(label="2. 点击首帧添加提示", interactive=False)
                prompt_kind = gr.Radio(["正点", "负点"], value="正点", label="当前点击类型")
                gr.Markdown("建议：目标内部放 1–2 个正点；若掩码覆盖邻近目标，在邻近目标内部添加负点。")
                keep_largest = gr.Checkbox(
                    value=True,
                    label="只保留最大连通区域（减少不相连的串目标）",
                )
                prompt_table = gr.JSON(label="提示点")
                clear = gr.Button("清空提示点")
        run = gr.Button("3. 运行 SAM2 传播", variant="primary")
        status = gr.Textbox(label="状态", interactive=False)
        with gr.Row():
            preview = gr.Video(label="分割预览")
            report = gr.JSON(label="运行结果与异常")

        prepare.click(
            _prepare_video,
            inputs=[video, config_value],
            outputs=[frame, task_state, prompt_state, status],
        ).then(lambda state: state["frames"][0], inputs=task_state, outputs=first_frame_path)
        frame.select(
            _add_click,
            inputs=[first_frame_path, prompt_kind, prompt_state],
            outputs=[frame, prompt_state, prompt_table],
        )
        clear.click(
            _clear_clicks,
            inputs=first_frame_path,
            outputs=[frame, prompt_state, prompt_table],
        )
        run.click(
            _run_segmentation,
            inputs=[task_state, prompt_state, category, checkpoint, config_value, keep_largest],
            outputs=[preview, report, status],
        )
    return demo


def main() -> None:
    build_demo().launch(server_name="127.0.0.1", server_port=7860, show_error=True)


if __name__ == "__main__":
    main()
