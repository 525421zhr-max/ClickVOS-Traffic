"""Gradio user interface for the local ClickVOS Traffic workflow."""

from __future__ import annotations

import json
import os
import gc
import shutil
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr
import torch
from PIL import Image, ImageDraw

import numpy as np

from clickvos.anomaly import ReactivationGuard, detect_fragmentation, detect_reactivation
from clickvos.config import AppConfig, load_config
from clickvos.errors import ClickVOSError
from clickvos.export import build_preview_video
from clickvos.sam2_engine import (
    ObjectPrompt,
    PromptPoint,
    Sam2Engine,
    save_boolean_mask_and_overlay,
)
from clickvos.video_io import prepare_task


_ACTIVE_SESSIONS: dict[str, dict[str, Any]] = {}
_SESSION_LOCK = threading.Lock()


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


def _save_runtime_prediction(
    runtime: dict[str, Any],
    prediction: Any,
    *,
    update_guard: bool = True,
) -> None:
    try:
        object_index = prediction.object_ids.index(1)
    except ValueError as exc:
        raise RuntimeError("SAM2 correction result no longer contains object 1") from exc
    frame_index = prediction.frame_index
    stem = f"{frame_index:05d}"
    saved, raw, components = save_boolean_mask_and_overlay(
        prediction.masks[object_index],
        runtime["frames"][frame_index],
        runtime["task_root"] / "masks" / f"{stem}.png",
        runtime["task_root"] / "overlays" / f"{stem}.jpg",
        runtime["keep_largest"],
    )
    runtime["model_mask_foreground_pixels"][f"{stem}.png"] = saved
    runtime["model_mask_component_counts"][f"{stem}.png"] = components
    if update_guard and runtime.get("reactivation_guard") is not None:
        confirmed = frame_index in runtime.get("guard_confirmed_frames", set())
        decision = runtime["reactivation_guard"].observe(frame_index, saved, confirmed=confirmed)
        if decision.suppress:
            candidate_masks = runtime["task_root"] / "review_candidates" / "masks"
            candidate_overlays = runtime["task_root"] / "review_candidates" / "overlays"
            candidate_masks.mkdir(parents=True, exist_ok=True)
            candidate_overlays.mkdir(parents=True, exist_ok=True)
            shutil.copy2(runtime["task_root"] / "masks" / f"{stem}.png", candidate_masks / f"{stem}.png")
            shutil.copy2(runtime["task_root"] / "overlays" / f"{stem}.jpg", candidate_overlays / f"{stem}.jpg")
            save_boolean_mask_and_overlay(
                np.zeros_like(prediction.masks[object_index], dtype=bool),
                runtime["frames"][frame_index],
                runtime["task_root"] / "masks" / f"{stem}.png",
                runtime["task_root"] / "overlays" / f"{stem}.jpg",
                False,
            )
            saved = 0
            components = 0
            runtime["guarded_frames"].append(
                {
                    "frame_index": frame_index,
                    "candidate_pixels": runtime["model_mask_foreground_pixels"][f"{stem}.png"],
                    "triggered_guard": decision.triggered,
                    "preceding_empty_frames": decision.empty_frame_count,
                }
            )
    runtime["mask_foreground_pixels"][f"{stem}.png"] = saved
    runtime["raw_mask_foreground_pixels"][f"{stem}.png"] = raw
    runtime["mask_component_counts"][f"{stem}.png"] = components


def _runtime_report(runtime: dict[str, Any]) -> dict[str, Any]:
    anomaly_items = detect_reactivation(runtime["model_mask_foreground_pixels"])
    anomaly_items.extend(detect_fragmentation(runtime["model_mask_component_counts"]))
    anomalies = [asdict(item) for item in anomaly_items]
    return {
        "object_id": 1,
        "category": runtime["category"],
        "frame_count": len(runtime["frames"]),
        "postprocessing": "largest_connected_component" if runtime["keep_largest"] else "none",
        "mask_foreground_pixels": runtime["mask_foreground_pixels"],
        "model_mask_foreground_pixels": runtime["model_mask_foreground_pixels"],
        "raw_mask_foreground_pixels": runtime["raw_mask_foreground_pixels"],
        "mask_component_counts": runtime["mask_component_counts"],
        "model_mask_component_counts": runtime["model_mask_component_counts"],
        "reactivation_guard_enabled": runtime["reactivation_guard"] is not None,
        "reactivation_guard_minimum_empty_frames": 3,
        "guarded_frames": runtime["guarded_frames"],
        "model_load_seconds": runtime["model_load_seconds"],
        "initial_inference_seconds": runtime["initial_inference_seconds"],
        "corrections": runtime["corrections"],
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
    }


def _write_runtime_outputs(runtime: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    preview = build_preview_video(
        runtime["task_root"] / "overlays",
        runtime["task_root"] / "exports" / "preview.mp4",
        runtime["fps"],
    )
    report = _runtime_report(runtime)
    (runtime["task_root"] / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return str(preview), report


def _run_segmentation(
    task_state: dict[str, Any] | None,
    prompts: list[dict[str, Any]] | None,
    category: str,
    checkpoint_path: str,
    config_path: str,
    keep_largest: bool,
    guard_reactivation: bool,
) -> tuple[str, dict[str, Any], str, str]:
    if not task_state:
        raise gr.Error("请先上传并解析视频。")
    if not prompts or not any(item["positive"] for item in prompts):
        raise gr.Error("至少需要一个正点。")
    if not checkpoint_path:
        raise gr.Error("请填写本机 SAM2 权重路径。")
    try:
        config = load_config(Path(config_path))
        with _SESSION_LOCK:
            _ACTIVE_SESSIONS.clear()
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        engine, load_seconds = Sam2Engine.load(config, Path(checkpoint_path))
        frames = [Path(frame) for frame in task_state["frames"]]
        task_root = Path(task_state["task_root"])
        prompt = ObjectPrompt(
            object_id=1,
            category=category,
            frame_index=0,
            points=tuple(PromptPoint(item["x"], item["y"], item["positive"]) for item in prompts),
        )
        session = engine.start_session(frames)
        session.add_prompt(prompt)
        runtime: dict[str, Any] = {
            "session": session,
            "frames": frames,
            "task_root": task_root,
            "fps": task_state["fps"],
            "category": category,
            "keep_largest": keep_largest,
            "model_load_seconds": load_seconds,
            "mask_foreground_pixels": {},
            "model_mask_foreground_pixels": {},
            "raw_mask_foreground_pixels": {},
            "mask_component_counts": {},
            "model_mask_component_counts": {},
            "corrections": [],
            "reactivation_guard": ReactivationGuard(3) if guard_reactivation else None,
            "guarded_frames": [],
            "guard_confirmed_frames": set(),
        }
        started = time.perf_counter()
        for prediction in session.propagate():
            _save_runtime_prediction(runtime, prediction)
        runtime["initial_inference_seconds"] = time.perf_counter() - started
        preview, report = _write_runtime_outputs(runtime)
        session_key = task_root.name
        with _SESSION_LOCK:
            _ACTIVE_SESSIONS[session_key] = runtime
        status = (
            f"传播完成：{len(frames)} 帧，发现 {report['anomaly_count']} 个待复核异常。"
            f"重新激活保护抑制 {len(report['guarded_frames'])} 帧。"
            "可在下方输入帧号进行修正。"
        )
        return preview, report, status, session_key
    except Exception as exc:
        raise _friendly_error(exc) from exc


def _load_correction_frame(
    task_state: dict[str, Any] | None,
    frame_index: float | int,
) -> tuple[str, str, list[Any], list[Any], str]:
    if not task_state:
        raise gr.Error("请先上传并运行视频传播。")
    index = int(frame_index)
    frames = task_state["frames"]
    if not 0 <= index < len(frames):
        raise gr.Error(f"帧号必须在 0 到 {len(frames) - 1} 之间。")
    path = frames[index]
    return path, path, [], [], f"已载入第 {index} 帧，请添加修正点。"


def _apply_correction(
    session_key: str | None,
    frame_index: float | int,
    prompts: list[dict[str, Any]] | None,
) -> tuple[str, dict[str, Any], str, str, list[Any], list[Any]]:
    if not session_key:
        raise gr.Error("当前没有可修正的传播会话，请先运行传播。")
    if not prompts:
        raise gr.Error("请至少添加一个修正点。")
    with _SESSION_LOCK:
        runtime = _ACTIVE_SESSIONS.get(session_key)
    if runtime is None:
        raise gr.Error("推理状态已释放，请重新运行传播后再修正。")
    index = int(frame_index)
    if not 0 <= index < len(runtime["frames"]):
        raise gr.Error("修正帧号超出范围。")
    try:
        if runtime.get("reactivation_guard") is not None:
            runtime["reactivation_guard"] = ReactivationGuard(3)
            runtime["guarded_frames"] = [
                item for item in runtime["guarded_frames"] if item["frame_index"] < index
            ]
            for prior_index in range(index):
                name = f"{prior_index:05d}.png"
                count = runtime["model_mask_foreground_pixels"].get(name, 0)
                runtime["reactivation_guard"].observe(prior_index, count)
            runtime["guard_confirmed_frames"] = (
                {index} if any(item["positive"] for item in prompts) else set()
            )
        correction = ObjectPrompt(
            object_id=1,
            category=runtime["category"],
            frame_index=index,
            points=tuple(PromptPoint(item["x"], item["y"], item["positive"]) for item in prompts),
        )
        immediate_prediction = runtime["session"].add_prompt(correction)
        immediate_object_index = immediate_prediction.object_ids.index(1)
        immediate_pixels = int(immediate_prediction.masks[immediate_object_index].sum())
        started = time.perf_counter()
        updated = 0
        for prediction in runtime["session"].propagate(start_frame_idx=index):
            _save_runtime_prediction(runtime, prediction)
            updated += 1
        # SAM2 returns the user-corrected mask immediately. Preserve that exact mask on
        # the correction frame even if the propagation iterator yields a cached frame.
        _save_runtime_prediction(runtime, immediate_prediction, update_guard=False)
        elapsed = time.perf_counter() - started
        runtime["corrections"].append(
            {
                "frame_index": index,
                "points": prompts,
                "immediate_mask_pixels": immediate_pixels,
                "propagated_frames": updated,
                "seconds": elapsed,
            }
        )
        preview, report = _write_runtime_outputs(runtime)
        overlay = str(runtime["task_root"] / "overlays" / f"{index:05d}.jpg")
        status = f"第 {index} 帧修正完成，重新传播 {updated} 帧，用时 {elapsed:.3f} 秒。"
        return preview, report, status, overlay, [], []
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
        session_key = gr.State()
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
                guard_reactivation = gr.Checkbox(
                    value=True,
                    label="重新激活保护（目标连续消失 3 帧后暂停可疑掩码）",
                )
                prompt_table = gr.JSON(label="提示点")
                clear = gr.Button("清空提示点")
        run = gr.Button("3. 运行 SAM2 传播", variant="primary")
        status = gr.Textbox(label="状态", interactive=False)
        with gr.Row():
            preview = gr.Video(label="分割预览")
            report = gr.JSON(label="运行结果与异常")
        with gr.Accordion("4. 中间帧修正", open=True):
            gr.Markdown(
                "根据异常报告或预览输入帧号，载入该帧后添加正点或负点。"
                "修正会从该帧重新传播到视频结尾。重新激活保护开启时，"
                "被抑制的 SAM2 候选掩码保存在任务目录的 review_candidates 中供核查；"
                "正点表示确认目标重新出现，负点则继续保持拦截。"
            )
            with gr.Row():
                correction_index = gr.Number(value=0, precision=0, minimum=0, label="修正帧号（从 0 开始）")
                load_correction = gr.Button("载入修正帧")
            correction_frame_path = gr.State()
            correction_prompt_state = gr.State([])
            correction_frame = gr.Image(label="点击该帧添加修正提示", interactive=False)
            correction_kind = gr.Radio(["正点", "负点"], value="负点", label="修正点击类型")
            correction_table = gr.JSON(label="本次修正点")
            with gr.Row():
                clear_correction = gr.Button("清空修正点")
                apply_correction = gr.Button("应用修正并重新传播", variant="primary")

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
            inputs=[
                task_state, prompt_state, category, checkpoint, config_value,
                keep_largest, guard_reactivation,
            ],
            outputs=[preview, report, status, session_key],
        )
        load_correction.click(
            _load_correction_frame,
            inputs=[task_state, correction_index],
            outputs=[correction_frame, correction_frame_path, correction_prompt_state, correction_table, status],
        )
        correction_frame.select(
            _add_click,
            inputs=[correction_frame_path, correction_kind, correction_prompt_state],
            outputs=[correction_frame, correction_prompt_state, correction_table],
        )
        clear_correction.click(
            _clear_clicks,
            inputs=correction_frame_path,
            outputs=[correction_frame, correction_prompt_state, correction_table],
        )
        apply_correction.click(
            _apply_correction,
            inputs=[session_key, correction_index, correction_prompt_state],
            outputs=[preview, report, status, correction_frame, correction_prompt_state, correction_table],
        )
    return demo


def main() -> None:
    build_demo().launch(server_name="127.0.0.1", server_port=7860, show_error=True)


if __name__ == "__main__":
    main()
