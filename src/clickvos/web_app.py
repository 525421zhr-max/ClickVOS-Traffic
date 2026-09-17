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
from clickvos.export import build_annotation_bundle, build_preview_video
from clickvos.mask_processing import keep_largest_component, mask_boundary
from clickvos.sam2_engine import (
    ObjectPrompt,
    PromptPoint,
    Sam2Engine,
)
from clickvos.video_io import prepare_task


_ACTIVE_SESSIONS: dict[str, dict[str, Any]] = {}
_SESSION_LOCK = threading.Lock()

OBJECT_COLORS = (
    (0, 210, 255),
    (255, 92, 92),
    (143, 255, 92),
    (195, 110, 255),
    (255, 190, 70),
    (70, 150, 255),
)


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


def _object_summary(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "object_id": item["object_id"],
            "category": item["category"],
            "color_rgb": list(OBJECT_COLORS[(int(item["object_id"]) - 1) % len(OBJECT_COLORS)]),
            "positive_points": sum(point["positive"] for point in item["points"]),
            "negative_points": sum(not point["positive"] for point in item["points"]),
        }
        for item in objects
    ]


def _render_object_prompts(
    image_path: str,
    objects: list[dict[str, Any]],
    selected_object_id: int | None,
) -> Image.Image:
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    for item in objects:
        object_id = int(item["object_id"])
        color = OBJECT_COLORS[(object_id - 1) % len(OBJECT_COLORS)]
        outline = "white" if object_id == selected_object_id else "#333333"
        for point in item["points"]:
            x, y = int(point["x"]), int(point["y"])
            if point["positive"]:
                draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=color, outline=outline, width=2)
            else:
                draw.line((x - 7, y - 7, x + 7, y + 7), fill=color, width=4)
                draw.line((x - 7, y + 7, x + 7, y - 7), fill=color, width=4)
            draw.text((x + 9, y - 9), str(object_id), fill=color, stroke_width=2, stroke_fill="black")
    return image


def _prepare_multi_video(
    video_path: str | None,
    config_path: str,
) -> tuple[str, dict[str, Any], list[Any], dict[str, Any], list[Any], str, str]:
    frame, task_state, _, status = _prepare_video(video_path, config_path)
    return frame, task_state, [], gr.update(choices=[], value=None), [], status, frame


def _add_object(
    image_path: str | None,
    category: str,
    objects: list[dict[str, Any]] | None,
) -> tuple[Image.Image, list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], str]:
    if not image_path:
        raise gr.Error("请先完成视频抽帧。")
    entries = [dict(item) for item in (objects or [])]
    object_id = max((int(item["object_id"]) for item in entries), default=0) + 1
    if object_id > 20:
        raise gr.Error("单个任务最多支持 20 个目标。")
    entries.append({"object_id": object_id, "category": category, "points": []})
    choices = [(f"目标 {item['object_id']} · {item['category']}", item["object_id"]) for item in entries]
    return (
        _render_object_prompts(image_path, entries, object_id),
        entries,
        gr.update(choices=choices, value=object_id),
        _object_summary(entries),
        f"已新建目标 {object_id}，请为它添加至少一个正点。",
    )


def _delete_object(
    image_path: str | None,
    selected_object_id: int | float | None,
    objects: list[dict[str, Any]] | None,
) -> tuple[Image.Image | str | None, list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], str]:
    if selected_object_id is None:
        raise gr.Error("请先选择要删除的目标。")
    selected = int(selected_object_id)
    entries = [item for item in (objects or []) if int(item["object_id"]) != selected]
    next_id = int(entries[0]["object_id"]) if entries else None
    choices = [(f"目标 {item['object_id']} · {item['category']}", item["object_id"]) for item in entries]
    rendered = _render_object_prompts(image_path, entries, next_id) if image_path else None
    return rendered, entries, gr.update(choices=choices, value=next_id), _object_summary(entries), f"已删除目标 {selected}。"


def _select_object(
    image_path: str | None,
    selected_object_id: int | float | None,
    objects: list[dict[str, Any]] | None,
) -> tuple[Image.Image | str | None, str]:
    if not image_path or selected_object_id is None:
        return image_path, "请选择或新建目标。"
    selected = int(selected_object_id)
    return _render_object_prompts(image_path, objects or [], selected), f"当前编辑目标 {selected}。"


def _add_object_click(
    image_path: str | None,
    prompt_kind: str,
    selected_object_id: int | float | None,
    objects: list[dict[str, Any]] | None,
    event: gr.SelectData,
) -> tuple[Image.Image, list[dict[str, Any]], list[dict[str, Any]]]:
    if not image_path:
        raise gr.Error("请先完成视频抽帧。")
    if selected_object_id is None:
        raise gr.Error("请先点击“新建目标”。")
    selected = int(selected_object_id)
    entries = [
        {**item, "points": [dict(point) for point in item["points"]]}
        for item in (objects or [])
    ]
    target = next((item for item in entries if int(item["object_id"]) == selected), None)
    if target is None:
        raise gr.Error("当前目标不存在，请重新选择。")
    x, y = int(event.index[0]), int(event.index[1])
    target["points"].append({"x": x, "y": y, "positive": prompt_kind == "正点"})
    return _render_object_prompts(image_path, entries, selected), entries, _object_summary(entries)


def _clear_object_points(
    image_path: str | None,
    selected_object_id: int | float | None,
    objects: list[dict[str, Any]] | None,
) -> tuple[Image.Image | str | None, list[dict[str, Any]], list[dict[str, Any]]]:
    if selected_object_id is None:
        raise gr.Error("请先选择目标。")
    selected = int(selected_object_id)
    entries = [
        {**item, "points": [] if int(item["object_id"]) == selected else [dict(p) for p in item["points"]]}
        for item in (objects or [])
    ]
    rendered = _render_object_prompts(image_path, entries, selected) if image_path else None
    return rendered, entries, _object_summary(entries)


def _save_runtime_prediction(
    runtime: dict[str, Any],
    prediction: Any,
    *,
    update_guard: bool = True,
    only_object_id: int | None = None,
) -> None:
    frame_index = prediction.frame_index
    stem = f"{frame_index:05d}"
    masks_by_id = dict(zip(prediction.object_ids, prediction.masks, strict=True))
    effective_masks: dict[int, np.ndarray] = {}
    for object_id, object_runtime in runtime["objects"].items():
        object_dir = runtime["task_root"] / "masks" / f"object_{object_id:03d}"
        object_dir.mkdir(parents=True, exist_ok=True)
        if only_object_id is not None and object_id != only_object_id:
            existing = object_dir / f"{stem}.png"
            if existing.is_file():
                effective_masks[object_id] = np.asarray(Image.open(existing)) > 0
            continue
        if object_id not in masks_by_id:
            raise RuntimeError(f"SAM2 result no longer contains object {object_id}")
        raw_mask = masks_by_id[object_id].astype(bool, copy=False)
        analysis = keep_largest_component(raw_mask)
        model_mask = analysis.mask if runtime["keep_largest"] else raw_mask
        name = f"{stem}.png"
        model_pixels = int(model_mask.sum())
        object_runtime["model_mask_foreground_pixels"][name] = model_pixels
        object_runtime["raw_mask_foreground_pixels"][name] = analysis.raw_foreground_pixels
        object_runtime["model_mask_component_counts"][name] = analysis.component_count
        final_mask = model_mask
        final_components = analysis.component_count
        if update_guard and object_runtime["reactivation_guard"] is not None:
            confirmed = frame_index in object_runtime["guard_confirmed_frames"]
            decision = object_runtime["reactivation_guard"].observe(
                frame_index, model_pixels, confirmed=confirmed
            )
            if decision.suppress:
                candidate_root = runtime["task_root"] / "review_candidates" / f"object_{object_id:03d}"
                candidate_dir = candidate_root / "masks"
                candidate_overlays = candidate_root / "overlays"
                candidate_dir.mkdir(parents=True, exist_ok=True)
                candidate_overlays.mkdir(parents=True, exist_ok=True)
                Image.fromarray(model_mask.astype(np.uint8) * 255).save(candidate_dir / name)
                candidate_frame = np.asarray(
                    Image.open(runtime["frames"][frame_index]).convert("RGB"), dtype=np.float32
                )
                candidate_color = np.asarray(
                    OBJECT_COLORS[(object_id - 1) % len(OBJECT_COLORS)], dtype=np.float32
                )
                candidate_frame[model_mask] = (
                    candidate_frame[model_mask] * 0.55 + candidate_color * 0.45
                )
                candidate_frame[mask_boundary(model_mask)] = candidate_color
                Image.fromarray(candidate_frame.astype(np.uint8)).save(
                    candidate_overlays / f"{stem}.jpg", quality=92
                )
                if object_id == 1:
                    legacy_candidate = runtime["task_root"] / "review_candidates" / "masks"
                    legacy_overlay = runtime["task_root"] / "review_candidates" / "overlays"
                    legacy_candidate.mkdir(parents=True, exist_ok=True)
                    legacy_overlay.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(candidate_dir / name, legacy_candidate / name)
                    shutil.copy2(candidate_overlays / f"{stem}.jpg", legacy_overlay / f"{stem}.jpg")
                final_mask = np.zeros_like(model_mask, dtype=bool)
                final_components = 0
                object_runtime["guarded_frames"].append(
                    {
                        "object_id": object_id,
                        "frame_index": frame_index,
                        "candidate_pixels": model_pixels,
                        "triggered_guard": decision.triggered,
                        "preceding_empty_frames": decision.empty_frame_count,
                    }
                )
        Image.fromarray(final_mask.astype(np.uint8) * 255).save(object_dir / name)
        if object_id == 1:
            Image.fromarray(final_mask.astype(np.uint8) * 255).save(runtime["task_root"] / "masks" / name)
        object_runtime["mask_foreground_pixels"][name] = int(final_mask.sum())
        object_runtime["mask_component_counts"][name] = final_components
        effective_masks[object_id] = final_mask

    frame = np.asarray(Image.open(runtime["frames"][frame_index]).convert("RGB"), dtype=np.float32)
    for object_id in sorted(effective_masks):
        mask = effective_masks[object_id]
        color = np.asarray(OBJECT_COLORS[(object_id - 1) % len(OBJECT_COLORS)], dtype=np.float32)
        frame[mask] = frame[mask] * 0.55 + color * 0.45
        frame[mask_boundary(mask)] = color
    Image.fromarray(frame.astype(np.uint8)).save(
        runtime["task_root"] / "overlays" / f"{stem}.jpg", quality=92
    )


def _runtime_report(runtime: dict[str, Any]) -> dict[str, Any]:
    objects = []
    anomalies: list[dict[str, Any]] = []
    guarded_frames: list[dict[str, Any]] = []
    for object_id, item in sorted(runtime["objects"].items()):
        object_anomalies = detect_reactivation(item["model_mask_foreground_pixels"])
        object_anomalies.extend(detect_fragmentation(item["model_mask_component_counts"]))
        rendered = [{"object_id": object_id, **asdict(anomaly)} for anomaly in object_anomalies]
        anomalies.extend(rendered)
        guarded_frames.extend(item["guarded_frames"])
        objects.append(
            {
                "object_id": object_id,
                "category": item["category"],
                "color_rgb": list(OBJECT_COLORS[(object_id - 1) % len(OBJECT_COLORS)]),
                "mask_directory": f"masks/object_{object_id:03d}",
                "initial_points": item["points"],
                "mask_foreground_pixels": item["mask_foreground_pixels"],
                "model_mask_foreground_pixels": item["model_mask_foreground_pixels"],
                "raw_mask_foreground_pixels": item["raw_mask_foreground_pixels"],
                "mask_component_counts": item["mask_component_counts"],
                "model_mask_component_counts": item["model_mask_component_counts"],
                "guarded_frames": item["guarded_frames"],
                "anomalies": rendered,
            }
        )
    first_id = min(runtime["objects"])
    first = runtime["objects"][first_id]
    return {
        "object_id": first_id,
        "category": first["category"],
        "object_count": len(objects),
        "objects": objects,
        "frame_count": len(runtime["frames"]),
        "postprocessing": "largest_connected_component" if runtime["keep_largest"] else "none",
        "mask_foreground_pixels": first["mask_foreground_pixels"],
        "model_mask_foreground_pixels": first["model_mask_foreground_pixels"],
        "raw_mask_foreground_pixels": first["raw_mask_foreground_pixels"],
        "mask_component_counts": first["mask_component_counts"],
        "model_mask_component_counts": first["model_mask_component_counts"],
        "reactivation_guard_enabled": runtime["guard_reactivation"],
        "reactivation_guard_minimum_empty_frames": 3,
        "guarded_frames": guarded_frames,
        "model_load_seconds": runtime["model_load_seconds"],
        "initial_inference_seconds": runtime["initial_inference_seconds"],
        "peak_cuda_memory_bytes": runtime["peak_cuda_memory_bytes"],
        "model": runtime["model"],
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


def _run_multi_segmentation(
    task_state: dict[str, Any] | None,
    objects: list[dict[str, Any]] | None,
    checkpoint_path: str,
    config_path: str,
    keep_largest: bool,
    guard_reactivation: bool,
) -> tuple[str, dict[str, Any], str, str]:
    if not task_state:
        raise gr.Error("请先上传并解析视频。")
    if not objects:
        raise gr.Error("请至少新建一个目标。")
    object_ids = [int(item["object_id"]) for item in objects]
    if len(objects) > 20:
        raise gr.Error("单个任务最多支持 20 个目标。")
    if any(object_id <= 0 for object_id in object_ids) or len(set(object_ids)) != len(object_ids):
        raise gr.Error("目标 ID 必须是互不重复的正整数。")
    for item in objects:
        if not item.get("points") or not any(point["positive"] for point in item["points"]):
            raise gr.Error(f"目标 {item['object_id']} 至少需要一个正点。")
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
        if config.model.device == "cuda":
            torch.cuda.reset_peak_memory_stats()
        frames = [Path(frame) for frame in task_state["frames"]]
        task_root = Path(task_state["task_root"])
        session = engine.start_session(frames)
        for item in objects:
            session.add_prompt(
                ObjectPrompt(
                    object_id=int(item["object_id"]),
                    category=item["category"],
                    frame_index=0,
                    points=tuple(
                        PromptPoint(point["x"], point["y"], point["positive"])
                        for point in item["points"]
                    ),
                )
            )
        object_runtimes = {
            int(item["object_id"]): {
                "category": item["category"],
                "points": item["points"],
                "mask_foreground_pixels": {},
                "model_mask_foreground_pixels": {},
                "raw_mask_foreground_pixels": {},
                "mask_component_counts": {},
                "model_mask_component_counts": {},
                "reactivation_guard": ReactivationGuard(3) if guard_reactivation else None,
                "guarded_frames": [],
                "guard_confirmed_frames": set(),
            }
            for item in objects
        }
        runtime: dict[str, Any] = {
            "session": session,
            "frames": frames,
            "task_root": task_root,
            "fps": task_state["fps"],
            "keep_largest": keep_largest,
            "model_load_seconds": load_seconds,
            "model": {
                "name": config.model.name,
                "config": config.model.config,
                "checkpoint_sha256": config.model.checkpoint_sha256,
                "device": config.model.device,
                "offload_video_to_cpu": config.model.offload_video_to_cpu,
                "offload_state_to_cpu": config.model.offload_state_to_cpu,
            },
            "objects": object_runtimes,
            "corrections": [],
            "guard_reactivation": guard_reactivation,
        }
        started = time.perf_counter()
        for prediction in session.propagate():
            _save_runtime_prediction(runtime, prediction)
        runtime["initial_inference_seconds"] = time.perf_counter() - started
        runtime["peak_cuda_memory_bytes"] = (
            int(torch.cuda.max_memory_allocated()) if config.model.device == "cuda" else None
        )
        preview, report = _write_runtime_outputs(runtime)
        session_key = task_root.name
        with _SESSION_LOCK:
            _ACTIVE_SESSIONS[session_key] = runtime
        status = (
            f"传播完成：{len(objects)} 个目标、{len(frames)} 帧，"
            f"发现 {report['anomaly_count']} 个待复核异常。"
            f"重新激活保护抑制 {len(report['guarded_frames'])} 帧。"
            "可在下方输入帧号进行修正。"
        )
        return preview, report, status, session_key
    except Exception as exc:
        raise _friendly_error(exc) from exc


def _run_segmentation(
    task_state: dict[str, Any] | None,
    prompts: list[dict[str, Any]] | None,
    category: str,
    checkpoint_path: str,
    config_path: str,
    keep_largest: bool,
    guard_reactivation: bool,
) -> tuple[str, dict[str, Any], str, str]:
    """Compatibility wrapper for existing single-object verification scripts."""
    objects = [{"object_id": 1, "category": category, "points": list(prompts or [])}]
    return _run_multi_segmentation(
        task_state, objects, checkpoint_path, config_path, keep_largest, guard_reactivation
    )


def _export_active_task(session_key: str | None) -> tuple[str, str]:
    if not session_key:
        raise gr.Error("请先运行视频传播。")
    with _SESSION_LOCK:
        runtime = _ACTIVE_SESSIONS.get(session_key)
    if runtime is None:
        raise gr.Error("当前任务状态已释放，请重新运行传播。")
    try:
        bundle = build_annotation_bundle(runtime["task_root"])
        return str(bundle), f"标注包已生成：{bundle.name}"
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
    object_id: int | float | None = 1,
) -> tuple[str, dict[str, Any], str, str, list[Any], list[Any]]:
    if not session_key:
        raise gr.Error("当前没有可修正的传播会话，请先运行传播。")
    if not prompts:
        raise gr.Error("请至少添加一个修正点。")
    with _SESSION_LOCK:
        runtime = _ACTIVE_SESSIONS.get(session_key)
    if runtime is None:
        raise gr.Error("推理状态已释放，请重新运行传播后再修正。")
    if object_id is None or int(object_id) not in runtime["objects"]:
        raise gr.Error("请选择要修正的目标。")
    selected_object_id = int(object_id)
    index = int(frame_index)
    if not 0 <= index < len(runtime["frames"]):
        raise gr.Error("修正帧号超出范围。")
    try:
        if runtime["guard_reactivation"]:
            for current_object_id, item in runtime["objects"].items():
                item["reactivation_guard"] = ReactivationGuard(3)
                item["guarded_frames"] = [
                    entry for entry in item["guarded_frames"] if entry["frame_index"] < index
                ]
                for prior_index in range(index):
                    name = f"{prior_index:05d}.png"
                    count = item["model_mask_foreground_pixels"].get(name, 0)
                    item["reactivation_guard"].observe(prior_index, count)
                item["guard_confirmed_frames"] = (
                    {index}
                    if current_object_id == selected_object_id
                    and any(point["positive"] for point in prompts)
                    else set()
                )
        correction = ObjectPrompt(
            object_id=selected_object_id,
            category=runtime["objects"][selected_object_id]["category"],
            frame_index=index,
            points=tuple(PromptPoint(item["x"], item["y"], item["positive"]) for item in prompts),
        )
        immediate_prediction = runtime["session"].add_prompt(correction)
        immediate_object_index = immediate_prediction.object_ids.index(selected_object_id)
        immediate_pixels = int(immediate_prediction.masks[immediate_object_index].sum())
        started = time.perf_counter()
        updated = 0
        for prediction in runtime["session"].propagate(start_frame_idx=index):
            _save_runtime_prediction(runtime, prediction)
            updated += 1
        # SAM2 returns the user-corrected mask immediately. Preserve that exact mask on
        # the correction frame even if the propagation iterator yields a cached frame.
        _save_runtime_prediction(
            runtime,
            immediate_prediction,
            update_guard=False,
            only_object_id=selected_object_id,
        )
        elapsed = time.perf_counter() - started
        runtime["corrections"].append(
            {
                "object_id": selected_object_id,
                "frame_index": index,
                "points": prompts,
                "immediate_mask_pixels": immediate_pixels,
                "propagated_frames": updated,
                "seconds": elapsed,
            }
        )
        preview, report = _write_runtime_outputs(runtime)
        overlay = str(runtime["task_root"] / "overlays" / f"{index:05d}.jpg")
        status = (
            f"目标 {selected_object_id} 的第 {index} 帧修正完成，"
            f"重新传播 {updated} 帧，用时 {elapsed:.3f} 秒。"
        )
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
        objects_state = gr.State([])
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
                frame = gr.Image(label="2. 为多个目标添加提示", interactive=False)
                with gr.Row():
                    add_object = gr.Button("新建目标", variant="primary")
                    delete_object = gr.Button("删除当前目标")
                current_object = gr.Dropdown(choices=[], label="当前目标", interactive=True)
                prompt_kind = gr.Radio(["正点", "负点"], value="正点", label="当前点击类型")
                gr.Markdown(
                    "先选择类别并新建目标，再在目标内部添加正点；切换目标后继续点击。"
                    "若掩码可能覆盖邻近物体，可在邻近物体内部为当前目标添加负点。"
                )
                keep_largest = gr.Checkbox(
                    value=True,
                    label="只保留最大连通区域（减少不相连的串目标）",
                )
                guard_reactivation = gr.Checkbox(
                    value=True,
                    label="重新激活保护（目标连续消失 3 帧后暂停可疑掩码）",
                )
                object_table = gr.JSON(label="目标与提示点统计")
                clear = gr.Button("清空当前目标提示点")
        run = gr.Button("3. 运行 SAM2 传播", variant="primary")
        status = gr.Textbox(label="状态", interactive=False)
        with gr.Row():
            preview = gr.Video(label="分割预览")
            report = gr.JSON(label="运行结果与异常")
        with gr.Row():
            export_bundle = gr.Button("生成标注下载包", variant="primary")
            download = gr.File(label="标注结果包（ZIP）", interactive=False)
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
            _prepare_multi_video,
            inputs=[video, config_value],
            outputs=[
                frame, task_state, objects_state, current_object,
                object_table, status, first_frame_path,
            ],
        )
        add_object.click(
            _add_object,
            inputs=[first_frame_path, category, objects_state],
            outputs=[frame, objects_state, current_object, object_table, status],
        )
        delete_object.click(
            _delete_object,
            inputs=[first_frame_path, current_object, objects_state],
            outputs=[frame, objects_state, current_object, object_table, status],
        )
        current_object.change(
            _select_object,
            inputs=[first_frame_path, current_object, objects_state],
            outputs=[frame, status],
        )
        frame.select(
            _add_object_click,
            inputs=[first_frame_path, prompt_kind, current_object, objects_state],
            outputs=[frame, objects_state, object_table],
        )
        clear.click(
            _clear_object_points,
            inputs=[first_frame_path, current_object, objects_state],
            outputs=[frame, objects_state, object_table],
        )
        run.click(
            _run_multi_segmentation,
            inputs=[
                task_state, objects_state, checkpoint, config_value,
                keep_largest, guard_reactivation,
            ],
            outputs=[preview, report, status, session_key],
        )
        export_bundle.click(
            _export_active_task,
            inputs=session_key,
            outputs=[download, status],
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
            inputs=[session_key, correction_index, correction_prompt_state, current_object],
            outputs=[preview, report, status, correction_frame, correction_prompt_state, correction_table],
        )
    return demo


def main() -> None:
    build_demo().launch(server_name="127.0.0.1", server_port=7860, show_error=True)


if __name__ == "__main__":
    main()
