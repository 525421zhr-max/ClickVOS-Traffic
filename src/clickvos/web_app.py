"""Gradio user interface for the local ClickVOS Traffic workflow."""

from __future__ import annotations

import json
import os
import gc
import shutil
import threading
import time
from dataclasses import asdict
from itertools import combinations
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
from clickvos.task_store import (
    CleanupPreview,
    RestorePreview,
    archive_task,
    list_archived_tasks,
    list_tasks,
    load_task,
    preview_task_cleanup,
    preview_task_restore,
    restore_archived_task,
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

APP_CSS = """
:root {
  --cv-accent: #0f766e;
  --cv-accent-strong: #115e59;
  --cv-surface-muted: #f4f7f6;
  --cv-border: #d7e1df;
  --cv-text: #17211f;
  --cv-muted: #53615e;
  --cv-danger: #b42318;
}
.gradio-container {
  max-width: 1180px !important;
  margin: 0 auto !important;
  color: var(--cv-text) !important;
}
.app-header {
  padding: 1.5rem 0 0.5rem;
  max-width: 72ch;
}
.app-header h1 {
  margin-bottom: 0.45rem !important;
  letter-spacing: -0.025em;
}
.app-header p { color: var(--cv-muted); line-height: 1.65; }
.workflow-steps {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  margin: 0.5rem 0 1.25rem;
}
.workflow-step {
  padding: 0.42rem 0.72rem;
  border: 1px solid var(--cv-border);
  border-radius: 999px;
  background: var(--cv-surface-muted);
  color: var(--cv-muted);
  font-size: 0.88rem;
  font-weight: 650;
}
.workflow-step strong { color: var(--cv-accent-strong); }
.status-strip textarea {
  font-weight: 650 !important;
  color: var(--cv-accent-strong) !important;
  background: #ecf8f5 !important;
  border-color: #9bd4ca !important;
}
.step-panel {
  margin-bottom: 0.8rem;
  border-color: var(--cv-border) !important;
}
.section-note { max-width: 75ch; color: var(--cv-muted); }
.first-frame-review {
  max-width: 75ch;
  padding: 0.85rem 1rem;
  border: 1px solid #b9d8d2;
  border-radius: 0.65rem;
  background: #f2faf8;
  color: #23413c;
}
.first-frame-review h3 {
  margin: 0 0 0.35rem !important;
  color: var(--cv-accent-strong);
  font-size: 1rem !important;
}
.first-frame-review p { margin: 0 !important; line-height: 1.6; }
.danger-soft button {
  color: var(--cv-danger) !important;
  border-color: #efb0aa !important;
  background: #fff7f6 !important;
}
.danger-soft button:hover { background: #fdecea !important; }
.secondary-action button { border-color: var(--cv-border) !important; }
button:focus-visible, input:focus-visible, textarea:focus-visible {
  outline: 3px solid rgba(15, 118, 110, 0.28) !important;
  outline-offset: 2px !important;
}
::selection { background: #bce8df; color: #102522; }
@media (max-width: 760px) {
  .gradio-container { padding-inline: 0.75rem !important; }
  .workflow-step { flex: 1 1 auto; text-align: center; }
  .app-header { padding-top: 0.75rem; }
}
"""


def _friendly_error(exc: Exception) -> gr.Error:
    if isinstance(exc, ClickVOSError):
        return gr.Error(exc.user_message)
    return gr.Error(str(exc))


def _prepare_video(video_path: str | None, config_path: str) -> tuple[str, dict[str, Any], list[dict[str, Any]], str]:
    if not video_path:
        raise gr.Error("请先上传交通视频。")
    try:
        config = load_config(Path(config_path))
        layout, metadata, frames = prepare_task(
            Path(video_path),
            config.tasks_root,
            max_bytes=config.video.max_upload_bytes,
            quality=config.video.jpeg_quality,
        )
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


def _write_composite_overlay(
    runtime: dict[str, Any],
    frame_index: int,
    masks: dict[int, np.ndarray] | None = None,
) -> Path:
    stem = f"{frame_index:05d}"
    effective_masks = masks or {}
    if masks is None:
        for object_id in runtime["objects"]:
            mask_path = runtime["task_root"] / "masks" / f"object_{object_id:03d}" / f"{stem}.png"
            if mask_path.is_file():
                effective_masks[object_id] = np.asarray(Image.open(mask_path).convert("L")) > 0
    frame = np.asarray(Image.open(runtime["frames"][frame_index]).convert("RGB"), dtype=np.float32)
    for object_id in sorted(effective_masks):
        mask = effective_masks[object_id]
        color = np.asarray(OBJECT_COLORS[(object_id - 1) % len(OBJECT_COLORS)], dtype=np.float32)
        frame[mask] = frame[mask] * 0.55 + color * 0.45
        frame[mask_boundary(mask)] = color
    output = runtime["task_root"] / "overlays" / f"{stem}.jpg"
    Image.fromarray(frame.astype(np.uint8)).save(output, quality=92)
    return output


def _detect_mask_overlaps(
    runtime: dict[str, Any], minimum_overlap_pixels: int = 10
) -> list[dict[str, Any]]:
    if minimum_overlap_pixels < 1:
        raise ValueError("minimum_overlap_pixels must be positive")
    events: list[dict[str, Any]] = []
    for frame_index in range(len(runtime["frames"])):
        name = f"{frame_index:05d}.png"
        masks: dict[int, np.ndarray] = {}
        for object_id in runtime["objects"]:
            path = runtime["task_root"] / "masks" / f"object_{object_id:03d}" / name
            if path.is_file():
                masks[object_id] = np.asarray(Image.open(path).convert("L")) > 0
        for first_id, second_id in combinations(sorted(masks), 2):
            overlap_pixels = int(np.logical_and(masks[first_id], masks[second_id]).sum())
            if overlap_pixels >= minimum_overlap_pixels:
                events.append(
                    {
                        "object_id": first_id,
                        "related_object_id": second_id,
                        "kind": "instance_mask_overlap",
                        "frame_index": frame_index,
                        "severity": "medium",
                        "message": "两个对象掩码发生重叠，请确认是否串到同一目标。",
                        "evidence": {"overlap_pixels": overlap_pixels},
                    }
                )
    return events


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

    _write_composite_overlay(runtime, frame_index, effective_masks)


def _runtime_report(runtime: dict[str, Any]) -> dict[str, Any]:
    objects = []
    anomalies: list[dict[str, Any]] = []
    guarded_frames: list[dict[str, Any]] = []
    for object_id, item in sorted(runtime["objects"].items()):
        object_anomalies = detect_reactivation(item["model_mask_foreground_pixels"])
        object_anomalies.extend(detect_fragmentation(item["model_mask_component_counts"]))
        confirmed = set(item.get("confirmed_reactivation_frames", []))
        rendered = []
        for anomaly in object_anomalies:
            resolved = (
                anomaly.kind == "reactivation_after_disappearance"
                and anomaly.frame_index in confirmed
            )
            entry = {
                "object_id": object_id,
                **asdict(anomaly),
                "review_status": "confirmed" if resolved else "pending",
            }
            rendered.append(entry)
            if not resolved:
                anomalies.append(entry)
        guarded_frames.extend(item["guarded_frames"])
        objects.append(
            {
                "object_id": object_id,
                "category": item["category"],
                "color_rgb": list(OBJECT_COLORS[(object_id - 1) % len(OBJECT_COLORS)]),
                "mask_directory": f"masks/object_{object_id:03d}",
                "initial_points": [dict(point) for point in item["points"]],
                "mask_foreground_pixels": dict(item["mask_foreground_pixels"]),
                "model_mask_foreground_pixels": dict(item["model_mask_foreground_pixels"]),
                "raw_mask_foreground_pixels": dict(item["raw_mask_foreground_pixels"]),
                "mask_component_counts": dict(item["mask_component_counts"]),
                "model_mask_component_counts": dict(item["model_mask_component_counts"]),
                "guarded_frames": [dict(entry) for entry in item["guarded_frames"]],
                "confirmed_reactivation_frames": sorted(confirmed),
                "anomalies": rendered,
            }
        )
    overlap_events = _detect_mask_overlaps(runtime)
    anomalies.extend(overlap_events)
    first_id = min(runtime["objects"])
    first = runtime["objects"][first_id]
    return {
        "object_id": first_id,
        "category": first["category"],
        "object_count": len(objects),
        "objects": objects,
        "frame_count": len(runtime["frames"]),
        "postprocessing": "largest_connected_component" if runtime["keep_largest"] else "none",
        "mask_foreground_pixels": dict(first["mask_foreground_pixels"]),
        "model_mask_foreground_pixels": dict(first["model_mask_foreground_pixels"]),
        "raw_mask_foreground_pixels": dict(first["raw_mask_foreground_pixels"]),
        "mask_component_counts": dict(first["mask_component_counts"]),
        "model_mask_component_counts": dict(first["model_mask_component_counts"]),
        "reactivation_guard_enabled": runtime["guard_reactivation"],
        "reactivation_guard_minimum_empty_frames": 3,
        "guarded_frames": [dict(entry) for entry in guarded_frames],
        "confirmed_reactivations": [
            {
                "object_id": entry["object_id"],
                "frame_index": entry["frame_index"],
                "restored_frames": list(entry["restored_frames"]),
            }
            for entry in runtime.get("confirmed_reactivations", [])
        ],
        "review_actions": [
            {**entry, "affected_frames": list(entry["affected_frames"])}
            for entry in runtime.get("review_actions", [])
        ],
        "overlap_event_count": len(overlap_events),
        "overlap_events": overlap_events,
        "model_load_seconds": runtime["model_load_seconds"],
        "initial_inference_seconds": runtime["initial_inference_seconds"],
        "peak_cuda_memory_bytes": runtime["peak_cuda_memory_bytes"],
        "model": dict(runtime["model"]),
        "corrections": [dict(entry) for entry in runtime["corrections"]],
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
                "confirmed_reactivation_frames": [],
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
            "confirmed_reactivations": [],
            "review_actions": [],
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


def _anomaly_selector_update(report: dict[str, Any]) -> dict[str, Any]:
    labels = {
        "reactivation_after_disappearance": "消失后重新激活",
        "fragmented_mask": "多连通区域",
        "instance_mask_overlap": "对象掩码重叠",
    }
    choices = []
    for item in report.get("anomalies", []):
        object_id = int(item["object_id"])
        frame_index = int(item["frame_index"])
        kind = str(item["kind"])
        related = item.get("related_object_id")
        object_label = f"目标 {object_id}"
        if related is not None:
            object_label += f" 与目标 {related}"
        label = f"{object_label} · 第 {frame_index} 帧 · {labels.get(kind, kind)}"
        choices.append((label, f"{object_id}:{frame_index}:{kind}"))
    return gr.update(choices=choices, value=choices[0][1] if choices else None)


def _first_frame_review(report: dict[str, Any], first_overlay: str) -> tuple[str, str]:
    single_point_ids: list[int] = []
    for item in report.get("objects", []):
        positive_count = sum(
            bool(point.get("positive")) for point in item.get("initial_points", [])
        )
        if positive_count == 1:
            single_point_ids.append(int(item["object_id"]))

    if single_point_ids:
        ids = "、".join(str(object_id) for object_id in single_point_ids)
        guidance = (
            "### 先确认首帧对象完整\n"
            f"目标 {ids} 目前只有一个正点。车辆或非机动车可能因此只分出车门、"
            "车窗或车轮等局部。请检查左侧首帧掩码；如果没有覆盖完整目标，回到第 2 步，"
            "在目标的不同部位补充正点后重新运行。负点应放在不需要的邻近物体上。"
        )
    else:
        guidance = (
            "### 先确认首帧对象完整\n"
            "当前目标已有多个正点，但仍请检查左侧首帧掩码是否覆盖完整实例、"
            "且没有包含邻近物体。首帧不完整时应先补点再传播，不要等到后续帧再修正。"
        )
    return first_overlay, guidance


def _review_object_update(report: dict[str, Any]) -> dict[str, Any]:
    choices = [
        (
            f"目标 {int(item['object_id'])} · {item['category']}",
            int(item["object_id"]),
        )
        for item in report.get("objects", [])
    ]
    return gr.update(choices=choices, value=choices[0][1] if choices else None)


def _add_first_frame_review_click(
    first_overlay_path: str | None,
    prompt_kind: str,
    selected_object_id: int | float | None,
    objects: list[dict[str, Any]] | None,
    added_points: list[dict[str, Any]] | None,
    event: gr.SelectData,
) -> tuple[Image.Image, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str]:
    if not first_overlay_path:
        raise gr.Error("请先运行传播，再在首帧结果上补点。")
    if selected_object_id is None:
        raise gr.Error("请选择要补点的目标。")
    selected = int(selected_object_id)
    entries = [
        {**item, "points": [dict(point) for point in item["points"]]}
        for item in (objects or [])
    ]
    target = next((item for item in entries if int(item["object_id"]) == selected), None)
    if target is None:
        raise gr.Error("补点目标不存在，请重新运行传播。")
    x, y = int(event.index[0]), int(event.index[1])
    point = {"x": x, "y": y, "positive": prompt_kind == "正点"}
    target["points"].append(point)
    additions = [dict(item) for item in (added_points or [])]
    additions.append({"object_id": selected, **point})
    point_label = "正点" if point["positive"] else "负点"
    status = (
        f"已为目标 {selected} 添加{point_label} ({x}, {y})。"
        "可继续补点、撤销最后一个补点，或用当前提示重新传播。"
    )
    return (
        _render_object_prompts(first_overlay_path, entries, selected),
        entries,
        _object_summary(entries),
        additions,
        status,
    )


def _undo_first_frame_review_click(
    first_overlay_path: str | None,
    selected_object_id: int | float | None,
    objects: list[dict[str, Any]] | None,
    added_points: list[dict[str, Any]] | None,
) -> tuple[Image.Image, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str]:
    if not first_overlay_path:
        raise gr.Error("请先运行传播，再撤销首帧补点。")
    additions = [dict(item) for item in (added_points or [])]
    if not additions:
        raise gr.Error("当前没有可撤销的首帧补点。")
    last = additions.pop()
    object_id = int(last["object_id"])
    entries = [
        {**item, "points": [dict(point) for point in item["points"]]}
        for item in (objects or [])
    ]
    target = next((item for item in entries if int(item["object_id"]) == object_id), None)
    expected = {key: last[key] for key in ("x", "y", "positive")}
    if target is None or not target["points"] or target["points"][-1] != expected:
        raise gr.Error("提示点状态已经变化，无法安全撤销；请重新运行传播。")
    target["points"].pop()
    rendered_object_id = int(selected_object_id) if selected_object_id is not None else object_id
    return (
        _render_object_prompts(first_overlay_path, entries, rendered_object_id),
        entries,
        _object_summary(entries),
        additions,
        f"已撤销目标 {object_id} 的最后一个首帧补点。",
    )


def _run_multi_for_web(*args: Any) -> tuple[Any, ...]:
    preview, report, status, session_key = _run_multi_segmentation(*args)
    first_overlay = str(Path(args[0]["task_root"]) / "overlays" / "00000.jpg")
    review_overlay, review_guidance = _first_frame_review(report, first_overlay)
    return (
        preview,
        report,
        status,
        session_key,
        _anomaly_selector_update(report),
        review_overlay,
        review_guidance,
        first_overlay,
        _review_object_update(report),
        [],
    )


def _load_selected_anomaly(
    task_state: dict[str, Any] | None,
    selection: str | None,
) -> tuple[int, int, str, str, list[Any], list[Any], str]:
    if not task_state or not selection:
        raise gr.Error("当前没有可定位的异常。")
    try:
        object_text, frame_text, kind = selection.split(":", 2)
        object_id, frame_index = int(object_text), int(frame_text)
    except (TypeError, ValueError) as exc:
        raise gr.Error("异常定位信息无效，请重新运行传播。") from exc
    frames = task_state["frames"]
    if not 0 <= frame_index < len(frames):
        raise gr.Error("异常帧号超出视频范围。")
    path = frames[frame_index]
    return (
        object_id,
        frame_index,
        path,
        path,
        [],
        [],
        f"已定位目标 {object_id} 的第 {frame_index} 帧异常：{kind}。",
    )


def _restore_guarded_candidate_masks(
    runtime: dict[str, Any], object_id: int, start_frame: int
) -> list[int]:
    item = runtime["objects"][object_id]
    guard = item["reactivation_guard"]
    if guard is None:
        raise ValueError("该任务未启用重新激活保护。")
    minimum_empty_frames = guard.minimum_empty_frames
    event_frames = sorted(
        anomaly.frame_index
        for anomaly in detect_reactivation(
            item["model_mask_foreground_pixels"], minimum_empty_frames
        )
    )
    if start_frame not in event_frames:
        raise ValueError("只能确认消失后重新激活的起始帧，请从异常列表定位。")
    next_event = next((frame for frame in event_frames if frame > start_frame), None)
    guarded_entries = [
        dict(entry)
        for entry in item["guarded_frames"]
        if int(entry["frame_index"]) >= start_frame
        and (next_event is None or int(entry["frame_index"]) < next_event)
    ]
    restored = sorted(
        {
            int(entry["frame_index"])
            for entry in guarded_entries
        }
    )
    if not restored:
        raise ValueError("该目标和帧没有等待确认的重新激活候选。")
    candidate_dir = runtime["task_root"] / "review_candidates" / f"object_{object_id:03d}" / "masks"
    object_dir = runtime["task_root"] / "masks" / f"object_{object_id:03d}"
    for frame_index in restored:
        name = f"{frame_index:05d}.png"
        source = candidate_dir / name
        if not source.is_file():
            raise FileNotFoundError(f"missing review candidate: {source}")
        shutil.copy2(source, object_dir / name)
        if object_id == 1:
            shutil.copy2(source, runtime["task_root"] / "masks" / name)
        mask = np.asarray(Image.open(source).convert("L")) > 0
        item["mask_foreground_pixels"][name] = int(mask.sum())
        item["mask_component_counts"][name] = item["model_mask_component_counts"][name]
        _write_composite_overlay(runtime, frame_index)
    restored_set = set(restored)
    item["guarded_frames"] = [
        entry for entry in item["guarded_frames"]
        if int(entry["frame_index"]) not in restored_set
    ]
    confirmations = item.setdefault("confirmed_reactivation_frames", [])
    if start_frame not in confirmations:
        confirmations.append(start_frame)
    runtime.setdefault("confirmed_reactivations", []).append(
        {
            "object_id": object_id,
            "frame_index": start_frame,
            "restored_frames": restored,
            "guarded_entries": guarded_entries,
        }
    )
    runtime.setdefault("review_actions", []).append(
        {
            "action": "confirm_reactivation",
            "object_id": object_id,
            "frame_index": start_frame,
            "affected_frames": list(restored),
        }
    )
    return restored


def _undo_guarded_candidate_masks(
    runtime: dict[str, Any], object_id: int, start_frame: int
) -> list[int]:
    confirmations = runtime.get("confirmed_reactivations", [])
    match_index = next(
        (
            index
            for index in range(len(confirmations) - 1, -1, -1)
            if int(confirmations[index]["object_id"]) == object_id
            and int(confirmations[index]["frame_index"]) == start_frame
        ),
        None,
    )
    if match_index is None:
        raise ValueError("该目标和帧没有可以撤销的候选确认。")

    confirmation = confirmations[match_index]
    restored = [int(frame_index) for frame_index in confirmation["restored_frames"]]
    item = runtime["objects"][object_id]
    object_dir = runtime["task_root"] / "masks" / f"object_{object_id:03d}"
    candidate_dir = (
        runtime["task_root"]
        / "review_candidates"
        / f"object_{object_id:03d}"
        / "masks"
    )
    missing = [
        candidate_dir / f"{frame_index:05d}.png"
        for frame_index in restored
        if not (candidate_dir / f"{frame_index:05d}.png").is_file()
    ]
    if missing:
        raise FileNotFoundError(f"missing review candidate: {missing[0]}")
    confirmations.pop(match_index)
    for frame_index in restored:
        name = f"{frame_index:05d}.png"
        source = candidate_dir / name
        candidate = np.asarray(Image.open(source).convert("L"))
        empty = np.zeros_like(candidate, dtype=np.uint8)
        Image.fromarray(empty).save(object_dir / name)
        if object_id == 1:
            Image.fromarray(empty).save(runtime["task_root"] / "masks" / name)
        item["mask_foreground_pixels"][name] = 0
        item["mask_component_counts"][name] = 0
        _write_composite_overlay(runtime, frame_index)

    guarded_entries = confirmation.get("guarded_entries") or [
        {
            "object_id": object_id,
            "frame_index": frame_index,
            "candidate_pixels": item["model_mask_foreground_pixels"][f"{frame_index:05d}.png"],
            "triggered_guard": frame_index == start_frame,
            "preceding_empty_frames": 3 if frame_index == start_frame else 0,
        }
        for frame_index in restored
    ]
    existing_frames = {int(entry["frame_index"]) for entry in item["guarded_frames"]}
    item["guarded_frames"].extend(
        dict(entry)
        for entry in guarded_entries
        if int(entry["frame_index"]) not in existing_frames
    )
    item["guarded_frames"].sort(key=lambda entry: int(entry["frame_index"]))
    item["confirmed_reactivation_frames"] = [
        frame_index
        for frame_index in item.get("confirmed_reactivation_frames", [])
        if int(frame_index) != start_frame
    ]
    item.get("guard_confirmed_frames", set()).discard(start_frame)
    runtime.setdefault("review_actions", []).append(
        {
            "action": "undo_reactivation_confirmation",
            "object_id": object_id,
            "frame_index": start_frame,
            "affected_frames": list(restored),
        }
    )
    return restored


def _confirm_guarded_candidate(
    session_key: str | None,
    object_id: int | float | None,
    frame_index: int | float,
) -> tuple[str, dict[str, Any], str, str, dict[str, Any]]:
    if not session_key or object_id is None:
        raise gr.Error("请先定位一个重新激活异常。")
    with _SESSION_LOCK:
        runtime = _ACTIVE_SESSIONS.get(session_key)
    if runtime is None:
        raise gr.Error("当前任务状态已释放，请重新运行传播。")
    selected_object_id = int(object_id)
    index = int(frame_index)
    if selected_object_id not in runtime["objects"]:
        raise gr.Error("目标不存在。")
    try:
        restored = _restore_guarded_candidate_masks(runtime, selected_object_id, index)
        preview, report = _write_runtime_outputs(runtime)
        overlay = str(runtime["task_root"] / "overlays" / f"{index:05d}.jpg")
        status = (
            f"已确认目标 {selected_object_id} 在第 {index} 帧重新出现，"
            f"恢复 {len(restored)} 帧候选掩码。"
        )
        return preview, report, status, overlay, _anomaly_selector_update(report)
    except Exception as exc:
        raise _friendly_error(exc) from exc


def _undo_guarded_candidate_confirmation(
    session_key: str | None,
    object_id: int | float | None,
    frame_index: int | float,
) -> tuple[str, dict[str, Any], str, str, dict[str, Any]]:
    if not session_key or object_id is None:
        raise gr.Error("请保留刚才确认的目标和帧，再执行撤销。")
    with _SESSION_LOCK:
        runtime = _ACTIVE_SESSIONS.get(session_key)
    if runtime is None:
        raise gr.Error("当前任务状态已释放，请重新运行传播。")
    selected_object_id = int(object_id)
    index = int(frame_index)
    if selected_object_id not in runtime["objects"]:
        raise gr.Error("目标不存在。")
    try:
        restored = _undo_guarded_candidate_masks(runtime, selected_object_id, index)
        preview, report = _write_runtime_outputs(runtime)
        overlay = str(runtime["task_root"] / "overlays" / f"{index:05d}.jpg")
        status = (
            f"已撤销目标 {selected_object_id} 在第 {index} 帧的候选确认，"
            f"重新拦截 {len(restored)} 帧候选掩码。"
        )
        return preview, report, status, overlay, _anomaly_selector_update(report)
    except Exception as exc:
        raise _friendly_error(exc) from exc


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


def _refresh_task_history(config_path: str) -> tuple[dict[str, Any], str]:
    try:
        config = load_config(Path(config_path))
        tasks, skipped = list_tasks(config.tasks_root)
        choices = [(task.choice_label, task.task_id) for task in tasks]
        if not choices:
            message = "还没有可打开的历史任务。完成一次视频传播后，可在这里重新预览和导出。"
        else:
            message = f"找到 {len(choices)} 个历史任务，按最近更新时间排序。"
        if skipped:
            message += f" 另有 {skipped} 个不完整或损坏的目录已跳过。"
        return gr.update(choices=choices, value=choices[0][1] if choices else None), message
    except Exception as exc:
        raise _friendly_error(exc) from exc


def _open_history_task(
    config_path: str, task_id: str | None
) -> tuple[str | None, dict[str, Any], str]:
    if not task_id:
        raise gr.Error("请先选择一个历史任务。")
    try:
        config = load_config(Path(config_path))
        task = load_task(config.tasks_root, task_id)
        details = task.summary.as_dict()
        details["read_only"] = True
        if task.result is not None:
            details["model"] = task.result.get("model")
            details["initial_inference_seconds"] = task.result.get("initial_inference_seconds")
            details["peak_cuda_memory_bytes"] = task.result.get("peak_cuda_memory_bytes")
            details["objects"] = [
                {
                    "object_id": item.get("object_id"),
                    "category": item.get("category"),
                }
                for item in task.result.get("objects", [])
            ]
        preview = str(task.preview) if task.preview is not None else None
        if task.result is None:
            message = f"任务 {task_id} 只有抽帧结果，尚未生成分割结果。"
        elif task.preview is None:
            message = f"已读取任务 {task_id}，但预览视频缺失；仍可重新生成标注包。"
        else:
            message = f"已只读打开任务 {task_id}。可查看预览或重新生成标注包。"
        return preview, details, message
    except Exception as exc:
        raise _friendly_error(exc) from exc


def _export_history_task(config_path: str, task_id: str | None) -> tuple[str, str]:
    if not task_id:
        raise gr.Error("请先选择一个历史任务。")
    try:
        config = load_config(Path(config_path))
        task = load_task(config.tasks_root, task_id)
        if task.result is None:
            raise gr.Error("该任务尚无分割结果，不能生成标注包。")
        bundle = build_annotation_bundle(task.root)
        return str(bundle), f"历史任务 {task_id} 的标注包已生成。"
    except gr.Error:
        raise
    except Exception as exc:
        raise _friendly_error(exc) from exc


def _format_bytes(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"


def _preview_history_cleanup(
    config_path: str, task_id: str | None
) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    if not task_id:
        raise gr.Error("请先选择一个历史任务。")
    try:
        config = load_config(Path(config_path))
        task = load_task(config.tasks_root, task_id)
        preview = preview_task_cleanup(config.tasks_root, task_id)
        details = {
            "task_id": task_id,
            "video_name": task.summary.video_name,
            "frame_count": task.summary.frame_count,
            "object_count": task.summary.object_count,
            "file_count": preview.file_count,
            "size_bytes": preview.size_bytes,
            "size_human": _format_bytes(preview.size_bytes),
            "action": "move_to_recoverable_trash",
            "trash_root": preview.trash_root,
        }
        message = (
            f"已预览任务 {task_id}：{preview.file_count} 个文件，"
            f"约 {_format_bytes(preview.size_bytes)}。"
            "如需移入回收区，请在确认框完整输入任务编号。"
        )
        return details, preview.as_dict(), "", message
    except Exception as exc:
        raise _friendly_error(exc) from exc


def _archive_history_task(
    config_path: str,
    task_id: str | None,
    confirmation: str,
    cleanup_state: dict[str, Any] | None,
    current_task_state: dict[str, Any] | None,
) -> tuple[dict[str, Any], None, dict[str, Any], dict[str, Any], str, None, str]:
    if not task_id:
        raise gr.Error("请先选择一个历史任务。")
    if not cleanup_state:
        raise gr.Error("请先预览清理范围。")
    try:
        config = load_config(Path(config_path))
        expected = CleanupPreview(**cleanup_state)
        with _SESSION_LOCK:
            active_ids = set(_ACTIVE_SESSIONS)
            if current_task_state and current_task_state.get("task_root"):
                active_ids.add(Path(current_task_state["task_root"]).name)
            archived = archive_task(
                config.tasks_root,
                task_id,
                confirmation,
                expected,
                active_task_ids=active_ids,
            )
        tasks, skipped = list_tasks(config.tasks_root)
        choices = [(task.choice_label, task.task_id) for task in tasks]
        message = (
            f"任务 {archived.task_id} 已移入可恢复回收区："
            f"{archived.archived_root}。本次移动 {archived.file_count} 个文件，"
            f"约 {_format_bytes(archived.size_bytes)}；尚未永久删除。"
        )
        if skipped:
            message += f" 另有 {skipped} 个不完整或损坏目录已跳过。"
        selector = gr.update(choices=choices, value=choices[0][1] if choices else None)
        return selector, None, {}, {}, "", None, message
    except Exception as exc:
        raise _friendly_error(exc) from exc


def _refresh_task_trash(config_path: str) -> tuple[dict[str, Any], str]:
    try:
        config = load_config(Path(config_path))
        tasks, skipped = list_archived_tasks(config.tasks_root)
        choices = [(task.choice_label, task.archive_name) for task in tasks]
        message = f"回收区有 {len(choices)} 个可恢复任务。"
        if skipped:
            message += f" 另有 {skipped} 个无法读取的目录已跳过。"
        return gr.update(choices=choices, value=choices[0][1] if choices else None), message
    except Exception as exc:
        raise _friendly_error(exc) from exc


def _preview_trash_restore(
    config_path: str, archive_name: str | None
) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    if not archive_name:
        raise gr.Error("请先选择一个回收区任务。")
    try:
        config = load_config(Path(config_path))
        preview = preview_task_restore(config.tasks_root, archive_name)
        details = {
            "task_id": preview.task_id,
            "archive_name": archive_name,
            "file_count": preview.file_count,
            "size_bytes": preview.size_bytes,
            "size_human": _format_bytes(preview.size_bytes),
            "target_root": preview.target_root,
            "target_occupied": Path(preview.target_root).exists(),
        }
        message = (
            f"已预览 {preview.task_id}：{preview.file_count} 个文件，"
            f"约 {_format_bytes(preview.size_bytes)}。"
        )
        if details["target_occupied"]:
            message += " 原任务编号已被占用，当前不能恢复。"
        else:
            message += "输入完整任务编号后可恢复到历史任务列表。"
        return details, preview.as_dict(), "", message
    except Exception as exc:
        raise _friendly_error(exc) from exc


def _restore_trash_task(
    config_path: str,
    archive_name: str | None,
    confirmation: str,
    restore_state: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str, str, str]:
    if not archive_name or not restore_state:
        raise gr.Error("请先选择回收区任务并预览恢复范围。")
    try:
        config = load_config(Path(config_path))
        expected = RestorePreview(**restore_state)
        with _SESSION_LOCK:
            restored = restore_archived_task(
                config.tasks_root, archive_name, confirmation, expected
            )
        history, _ = list_tasks(config.tasks_root)
        archived, skipped = list_archived_tasks(config.tasks_root)
        history_choices = [(task.choice_label, task.task_id) for task in history]
        trash_choices = [(task.choice_label, task.archive_name) for task in archived]
        message = f"任务 {restored.name} 已恢复到历史任务列表。"
        if skipped:
            message += f" 回收区另有 {skipped} 个无法读取的目录已跳过。"
        return (
            gr.update(choices=history_choices, value=restored.name),
            gr.update(choices=trash_choices, value=trash_choices[0][1] if trash_choices else None),
            {}, {}, "", message,
        )
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
                confirmed_history = set(item.get("confirmed_reactivation_frames", []))
                was_guarded = any(
                    int(entry["frame_index"]) == index for entry in item["guarded_frames"]
                )
                if (
                    current_object_id == selected_object_id
                    and was_guarded
                    and any(point["positive"] for point in prompts)
                ):
                    confirmed_history.add(index)
                    item["confirmed_reactivation_frames"] = sorted(confirmed_history)
                item["reactivation_guard"] = ReactivationGuard(3)
                item["guarded_frames"] = [
                    entry for entry in item["guarded_frames"] if entry["frame_index"] < index
                ]
                for prior_index in range(index):
                    name = f"{prior_index:05d}.png"
                    count = item["model_mask_foreground_pixels"].get(name, 0)
                    item["reactivation_guard"].observe(
                        prior_index, count, confirmed=prior_index in confirmed_history
                    )
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


def _apply_correction_for_web(*args: Any) -> tuple[Any, ...]:
    preview, report, status, overlay, prompts, table = _apply_correction(*args)
    return preview, report, status, overlay, prompts, table, _anomaly_selector_update(report)


def build_demo(config_path: Path = Path("configs/default.json")) -> gr.Blocks:
    config: AppConfig = load_config(config_path)
    labels = {category.key: category.label_zh for category in config.categories}
    checkpoint_default = os.environ.get("CLICKVOS_CHECKPOINT", "")
    with gr.Blocks(title="ClickVOS Traffic") as demo:
        gr.Markdown(
            "# ClickVOS Traffic\n"
            "面向交通视频的交互式分割与半自动标注工具。上传许可清晰的视频，"
            "通过正负点选择目标，复核传播异常后导出标准标注。\n\n"
            "仅使用自有或许可证明确的交通素材；禁止上传私人照片、人像测试素材或未经授权的视频。",
            elem_classes=["app-header"],
        )
        gr.HTML(
            "<nav class='workflow-steps' aria-label='任务流程'>"
            "<span class='workflow-step'><strong>1</strong> 准备视频</span>"
            "<span class='workflow-step'><strong>2</strong> 标记目标</span>"
            "<span class='workflow-step'><strong>3</strong> 运行传播</span>"
            "<span class='workflow-step'><strong>4</strong> 复核修正</span>"
            "<span class='workflow-step'><strong>5</strong> 导出标注</span>"
            "</nav>"
        )
        task_state = gr.State()
        objects_state = gr.State([])
        first_frame_path = gr.State()
        session_key = gr.State()
        cleanup_state = gr.State({})
        restore_state = gr.State({})
        config_value = gr.State(str(config_path))

        status = gr.Textbox(
            label="当前状态",
            value="等待上传交通视频。",
            interactive=False,
            elem_classes=["status-strip"],
        )
        with gr.Accordion("历史任务与回收区", open=False, elem_classes=["step-panel"]):
            gr.Markdown(
                "这里读取本机 `outputs/tasks` 中已有的结果，不会重新加载模型或改写掩码。"
                "历史任务可以预览和再次导出；可将清理过的任务从回收区恢复。"
                "如需继续补点，请用原视频重新运行传播。",
                elem_classes=["section-note"],
            )
            with gr.Row():
                history_selector = gr.Dropdown(
                    choices=[], label="本地历史任务", interactive=True
                )
                refresh_history = gr.Button(
                    "刷新列表", elem_classes=["secondary-action"]
                )
                open_history = gr.Button("打开所选任务", variant="primary")
            history_status = gr.Markdown("正在读取本地任务列表。")
            with gr.Row(equal_height=False):
                history_preview = gr.Video(label="历史预览")
                history_details = gr.JSON(label="任务摘要")
            with gr.Row():
                export_history = gr.Button("重新生成历史任务标注包")
                history_download = gr.File(
                    label="历史任务标注包（ZIP）", interactive=False
                )
            with gr.Accordion("清理所选任务", open=False):
                gr.Markdown(
                    "先预览文件数和占用空间，再输入完整任务编号确认。"
                    "任务只会移入项目回收区，不会立即永久删除；当前活动任务不能清理。",
                    elem_classes=["section-note"],
                )
                cleanup_preview = gr.JSON(label="清理范围预览")
                cleanup_confirmation = gr.Textbox(
                    label="输入完整任务编号以确认",
                    placeholder="例如：7e3d167b0b81",
                )
                with gr.Row():
                    preview_cleanup = gr.Button(
                        "预览清理范围", elem_classes=["secondary-action"]
                    )
                    archive_history = gr.Button(
                        "移入可恢复回收区", elem_classes=["danger-soft"]
                    )
            with gr.Accordion("从回收区恢复任务", open=False):
                gr.Markdown(
                    "恢复前查看文件数和目标位置，并输入完整任务编号。"
                    "如原任务编号已被占用，恢复会被拒绝。",
                    elem_classes=["section-note"],
                )
                with gr.Row():
                    trash_selector = gr.Dropdown(
                        choices=[], label="回收区任务", interactive=True
                    )
                    refresh_trash = gr.Button(
                        "刷新回收区", elem_classes=["secondary-action"]
                    )
                trash_status = gr.Markdown("正在读取回收区。")
                restore_preview = gr.JSON(label="恢复范围预览")
                restore_confirmation = gr.Textbox(
                    label="输入完整任务编号以恢复", placeholder="例如：7e3d167b0b81"
                )
                with gr.Row():
                    preview_restore = gr.Button(
                        "预览恢复范围", elem_classes=["secondary-action"]
                    )
                    restore_task_button = gr.Button("恢复到历史任务")

        with gr.Accordion("1. 准备交通视频", open=True, elem_classes=["step-panel"]):
            with gr.Row(equal_height=False):
                video = gr.Video(label="交通视频", sources=["upload"])
                with gr.Column():
                    gr.Markdown(
                        "上传后先抽帧并检查首帧。建议使用 5–10 秒、镜头稳定、许可证明确的交通视频。",
                        elem_classes=["section-note"],
                    )
                    checkpoint = gr.Textbox(
                        label="SAM2 权重路径", value=checkpoint_default, type="text"
                    )
                    prepare = gr.Button("抽帧并显示首帧", variant="primary")

        with gr.Accordion("2. 标记一个或多个目标", open=True, elem_classes=["step-panel"]):
            with gr.Row(equal_height=False):
                frame = gr.Image(label="首帧提示区域", interactive=False)
                with gr.Column():
                    gr.Markdown(
                        "为当前目标至少添加一个正点。车辆和非机动车包含多个可分割部件时，"
                        "建议在车头、车身和车尾等不同区域添加正点；负点放在不需要的邻近物体内部。"
                        "切换目标后可继续标记。",
                        elem_classes=["section-note"],
                    )
                    category = gr.Dropdown(
                        choices=[(label, key) for key, label in labels.items()],
                        value="vehicle",
                        label="目标类别",
                    )
                    with gr.Row():
                        add_object = gr.Button("新建目标", variant="primary")
                        delete_object = gr.Button(
                            "删除当前目标", elem_classes=["danger-soft"]
                        )
                    current_object = gr.Dropdown(choices=[], label="当前目标", interactive=True)
                    prompt_kind = gr.Radio(["正点", "负点"], value="正点", label="当前点击类型")
                    clear = gr.Button("清空当前目标提示点", elem_classes=["secondary-action"])
                    object_table = gr.JSON(label="目标与提示点统计")

        with gr.Accordion("传播设置", open=False, elem_classes=["step-panel"]):
            gr.Markdown(
                "默认设置优先减少碎片和目标离场后的错误重现。只有进行对照实验时才建议关闭。",
                elem_classes=["section-note"],
            )
            with gr.Row():
                keep_largest = gr.Checkbox(
                    value=True,
                    label="只保留最大连通区域（减少不相连的串目标）",
                )
                guard_reactivation = gr.Checkbox(
                    value=True,
                    label="重新激活保护（目标连续消失 3 帧后暂停可疑掩码）",
                )
        run = gr.Button("3. 运行 SAM2 传播", variant="primary")

        with gr.Accordion("3. 传播结果", open=True, elem_classes=["step-panel"]):
            with gr.Row(equal_height=False):
                first_result = gr.Image(label="首帧分割检查", interactive=False)
                preview = gr.Video(label="完整传播预览")
            first_frame_guidance = gr.Markdown(
                "运行传播后，请先检查首帧是否覆盖完整目标，再查看后续帧。",
                elem_classes=["first-frame-review"],
            )
            first_result_path = gr.State()
            first_result_added_points = gr.State([])
            with gr.Row():
                first_result_object = gr.Dropdown(
                    choices=[], label="首帧补点目标", interactive=True
                )
                first_result_kind = gr.Radio(
                    ["正点", "负点"], value="正点", label="首帧补点类型"
                )
            with gr.Row():
                undo_first_result_point = gr.Button(
                    "撤销最后一个补点", elem_classes=["secondary-action"]
                )
                rerun_with_first_result_points = gr.Button(
                    "用补点重新传播", variant="primary"
                )
            with gr.Accordion("查看完整运行报告", open=False):
                report = gr.JSON(label="运行结果与异常")

        with gr.Accordion("4. 复核异常并修正", open=True, elem_classes=["step-panel"]):
            gr.Markdown(
                "优先从待复核列表定位异常。确认候选会恢复被保护机制拦截的掩码；"
                "如果判断错误，可以立即撤销。使用正负点修正时，系统会从该帧重新传播到结尾。",
                elem_classes=["section-note"],
            )
            with gr.Row():
                anomaly_selector = gr.Dropdown(
                    choices=[], label="待复核异常帧", interactive=True
                )
                load_anomaly = gr.Button("定位所选异常")
            with gr.Row():
                correction_index = gr.Number(value=0, precision=0, minimum=0, label="修正帧号（从 0 开始）")
                load_correction = gr.Button("载入修正帧")
            correction_frame_path = gr.State()
            correction_prompt_state = gr.State([])
            correction_frame = gr.Image(label="点击该帧添加修正提示", interactive=False)
            correction_kind = gr.Radio(["正点", "负点"], value="负点", label="修正点击类型")
            correction_table = gr.JSON(label="本次修正点")
            with gr.Row():
                clear_correction = gr.Button(
                    "清空修正点", elem_classes=["secondary-action"]
                )
                apply_correction = gr.Button("应用修正并重新传播", variant="primary")
                confirm_candidate = gr.Button("确认候选目标重新出现")
                undo_confirmation = gr.Button(
                    "撤销本次候选确认", elem_classes=["danger-soft"]
                )

        with gr.Accordion("5. 导出标注", open=True, elem_classes=["step-panel"]):
            gr.Markdown(
                "导出包包含逐对象 PNG 掩码、合成预览视频、ClickVOS 项目 JSON 和 COCO RLE；"
                "不会打包原视频和抽帧图片。",
                elem_classes=["section-note"],
            )
            with gr.Row():
                export_bundle = gr.Button("生成标注下载包", variant="primary")
                download = gr.File(label="标注结果包（ZIP）", interactive=False)

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
        current_object.input(
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
            _run_multi_for_web,
            inputs=[
                task_state, objects_state, checkpoint, config_value,
                keep_largest, guard_reactivation,
            ],
            outputs=[
                preview, report, status, session_key, anomaly_selector,
                first_result, first_frame_guidance, first_result_path,
                first_result_object, first_result_added_points,
            ],
        )
        first_result.select(
            _add_first_frame_review_click,
            inputs=[
                first_result_path, first_result_kind, first_result_object,
                objects_state, first_result_added_points,
            ],
            outputs=[
                first_result, objects_state, object_table,
                first_result_added_points, status,
            ],
        )
        undo_first_result_point.click(
            _undo_first_frame_review_click,
            inputs=[
                first_result_path, first_result_object,
                objects_state, first_result_added_points,
            ],
            outputs=[
                first_result, objects_state, object_table,
                first_result_added_points, status,
            ],
        )
        rerun_with_first_result_points.click(
            _run_multi_for_web,
            inputs=[
                task_state, objects_state, checkpoint, config_value,
                keep_largest, guard_reactivation,
            ],
            outputs=[
                preview, report, status, session_key, anomaly_selector,
                first_result, first_frame_guidance, first_result_path,
                first_result_object, first_result_added_points,
            ],
        )
        export_bundle.click(
            _export_active_task,
            inputs=session_key,
            outputs=[download, status],
        )
        load_anomaly.click(
            _load_selected_anomaly,
            inputs=[task_state, anomaly_selector],
            outputs=[
                current_object, correction_index, correction_frame,
                correction_frame_path, correction_prompt_state,
                correction_table, status,
            ],
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
            _apply_correction_for_web,
            inputs=[session_key, correction_index, correction_prompt_state, current_object],
            outputs=[
                preview, report, status, correction_frame,
                correction_prompt_state, correction_table, anomaly_selector,
            ],
        )
        confirm_candidate.click(
            _confirm_guarded_candidate,
            inputs=[session_key, current_object, correction_index],
            outputs=[preview, report, status, correction_frame, anomaly_selector],
        )
        undo_confirmation.click(
            _undo_guarded_candidate_confirmation,
            inputs=[session_key, current_object, correction_index],
            outputs=[preview, report, status, correction_frame, anomaly_selector],
        )
        refresh_history.click(
            _refresh_task_history,
            inputs=config_value,
            outputs=[history_selector, history_status],
        )
        open_history.click(
            _open_history_task,
            inputs=[config_value, history_selector],
            outputs=[history_preview, history_details, history_status],
        )
        export_history.click(
            _export_history_task,
            inputs=[config_value, history_selector],
            outputs=[history_download, history_status],
        )
        preview_cleanup.click(
            _preview_history_cleanup,
            inputs=[config_value, history_selector],
            outputs=[
                cleanup_preview, cleanup_state,
                cleanup_confirmation, history_status,
            ],
        )
        archive_event = archive_history.click(
            _archive_history_task,
            inputs=[
                config_value, history_selector,
                cleanup_confirmation, cleanup_state, task_state,
            ],
            outputs=[
                history_selector, history_preview, history_details,
                cleanup_preview, cleanup_confirmation,
                history_download, history_status,
            ],
        )
        archive_event.then(
            _refresh_task_trash,
            inputs=config_value,
            outputs=[trash_selector, trash_status],
        )
        refresh_trash.click(
            _refresh_task_trash,
            inputs=config_value,
            outputs=[trash_selector, trash_status],
        )
        preview_restore.click(
            _preview_trash_restore,
            inputs=[config_value, trash_selector],
            outputs=[restore_preview, restore_state, restore_confirmation, trash_status],
        )
        restore_task_button.click(
            _restore_trash_task,
            inputs=[config_value, trash_selector, restore_confirmation, restore_state],
            outputs=[
                history_selector, trash_selector, restore_preview,
                restore_state, restore_confirmation, trash_status,
            ],
        )
        demo.load(
            _refresh_task_history,
            inputs=config_value,
            outputs=[history_selector, history_status],
        )
        demo.load(
            _refresh_task_trash,
            inputs=config_value,
            outputs=[trash_selector, trash_status],
        )
    return demo


def _launch_options() -> dict[str, str | int | bool]:
    """Read the small set of safe deployment overrides from the environment."""
    host = os.environ.get("CLICKVOS_HOST", "127.0.0.1").strip()
    if not host:
        raise ValueError("CLICKVOS_HOST 不能为空")
    raw_port = os.environ.get("CLICKVOS_PORT", "7860").strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError("CLICKVOS_PORT 必须是整数") from exc
    if not 1 <= port <= 65535:
        raise ValueError("CLICKVOS_PORT 必须在 1 到 65535 之间")
    return {
        "server_name": host,
        "server_port": port,
        "show_error": True,
        "css": APP_CSS,
    }


def main() -> None:
    config_path = Path(os.environ.get("CLICKVOS_CONFIG", "configs/default.json"))
    build_demo(config_path).launch(
        **_launch_options(),
    )


if __name__ == "__main__":
    main()
