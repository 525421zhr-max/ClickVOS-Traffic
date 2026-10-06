"""Isolated first-frame previews and a persistent, task-local review journal."""

from __future__ import annotations

import copy
import json
import math
import os
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image

from clickvos.export import DEFAULT_OBJECT_COLORS
from clickvos.mask_processing import keep_largest_component, mask_boundary
from clickvos.sam2_engine import ObjectPrompt, PromptPoint, Sam2Engine, Sam2Session

_JOURNAL_LOCK = threading.RLock()


def _journal_path(task_root: Path) -> Path:
    if not task_root.is_dir():
        raise ValueError("任务目录不存在，请先准备视频。")
    path = task_root / "first_frame_review.json"
    if path.is_symlink():
        raise ValueError("首帧记录不能使用符号链接。")
    return path


def read_review_history(task_root: Path) -> dict[str, Any]:
    with _JOURNAL_LOCK:
        path = _journal_path(task_root)
        if not path.exists():
            return {"schema_version": 1, "events": []}
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(history, dict) or history.get("schema_version") != 1:
                raise ValueError("unsupported schema")
            events = history["events"]
            if not isinstance(events, list) or any(
                not isinstance(event, dict) or event.get("event_id") != index
                or event.get("action") not in {"add", "undo", "preview", "propagate"}
                or not isinstance(event.get("objects"), list)
                for index, event in enumerate(events, 1)
            ):
                raise ValueError("invalid events")
            return history
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("首帧补点记录损坏，已保留原文件；请检查记录后重试。") from exc


def append_review_event(
    task_root: Path, action: str, objects: list[dict[str, Any]], **details: Any,
) -> dict[str, Any]:
    if action not in {"add", "undo", "preview", "propagate"} or not isinstance(objects, list):
        raise ValueError("invalid review action or object list")
    # Clone the input and reject NaN/non-JSON data before touching the journal.
    event = json.loads(json.dumps({
        "action": action, "objects": objects, "details": details,
        "timestamp_utc": datetime.now(UTC).isoformat(),
    }, allow_nan=False))
    with _JOURNAL_LOCK:
        path = _journal_path(task_root)
        history = read_review_history(task_root)
        event["event_id"] = len(history["events"]) + 1
        history["events"].append(event)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=task_root, prefix=".first-frame-", suffix=".tmp", delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(history, stream, ensure_ascii=False, indent=2, allow_nan=False)
            os.replace(temporary, path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        return history


def render_composite_overlay(
    frame: Path, masks: dict[int, np.ndarray], output: Path,
) -> Path:
    with Image.open(frame) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    for object_id in sorted(masks):
        mask = masks[object_id]
        if mask.dtype != np.bool_ or mask.shape != rgb.shape[:2]:
            raise ValueError("invalid mask for composite overlay")
        color = np.asarray(DEFAULT_OBJECT_COLORS[(object_id - 1) % len(DEFAULT_OBJECT_COLORS)], dtype=np.float32)
        rgb[mask] = rgb[mask] * 0.55 + color * 0.45
        rgb[mask_boundary(mask)] = color
    output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb.astype(np.uint8)).save(output, quality=92)
    return output


def preview_first_frame(
    active_session: Sam2Session, objects: list[dict[str, Any]], task_root: Path,
    keep_largest: bool = False,
) -> dict[str, Any]:
    task_root = task_root.resolve()
    if not task_root.is_dir():
        raise ValueError("任务目录不存在，请先准备视频。")
    if not objects or len(objects) > 20:
        raise ValueError("请为 1 到 20 个目标添加提示点。")
    entries = copy.deepcopy(objects)
    prompts = []
    ids = set()
    frame = active_session.frames[0]
    with Image.open(frame) as image:
        width, height = image.size
    for item in entries:
        object_id = item["object_id"]
        if type(object_id) is not int or not 1 <= object_id <= 20 or object_id in ids:
            raise ValueError("目标 ID 必须是 1 到 20 之间互不重复的整数。")
        ids.add(object_id)
        points = []
        for point in item["points"]:
            if type(point["positive"]) is not bool or any(
                type(point[key]) not in (int, float) or not math.isfinite(point[key]) for key in ("x", "y")
            ):
                raise ValueError("提示点坐标和正负类型无效。")
            points.append(PromptPoint(point["x"], point["y"], point["positive"]))
        prompt = ObjectPrompt(object_id, item["category"], 0, tuple(points))
        prompt.validate(width, height, {category.key for category in active_session.config.categories})
        prompts.append(prompt)
    preview_root = task_root / "first_frame_previews"
    if task_root not in preview_root.resolve().parents:
        raise ValueError("预览目录超出当前任务范围。")
    preview_id = uuid.uuid4().hex
    root = preview_root / preview_id
    frames = root / "input_frames"
    frames.mkdir(parents=True, exist_ok=False)
    staged = frames / "00000.jpg"
    shutil.copy2(frame, staged)
    started = time.perf_counter()
    report = {
        "schema_version": 1, "preview_id": preview_id, "status": "running",
        "frame_count": 1, "temporal_propagation_count": 0,
        "model": asdict(active_session.config.model), "keep_largest": bool(keep_largest),
        "session_policy": "fresh_single_frame_session_complete_prompts",
    }
    report_path = root / "preview.json"
    try:
        with torch.inference_mode():
            engine = Sam2Engine(active_session.config, active_session.predictor)
            session = engine.start_session([staged])
            for prompt in prompts:
                prediction = session.add_prompt(prompt)
            if (
                prediction.frame_index != 0 or set(prediction.object_ids) != ids
                or len(prediction.object_ids) != len(ids) or len(prediction.masks) != len(ids)
            ):
                raise RuntimeError("首帧预览返回的对象不完整。")
            masks = {}
            measurements = []
            for object_id, raw in zip(prediction.object_ids, prediction.masks, strict=True):
                if raw.dtype != np.bool_ or raw.shape != (height, width):
                    raise RuntimeError("首帧预览掩码尺寸或类型无效。")
                effective = keep_largest_component(raw).mask if keep_largest else raw
                destination = root / "masks" / f"object_{object_id:03d}" / "00000.png"
                destination.parent.mkdir(parents=True)
                Image.fromarray(effective.astype(np.uint8) * 255).save(destination)
                masks[object_id] = effective
                entry = next(item for item in entries if item["object_id"] == object_id)
                measurements.append({
                    **entry, "raw_mask_pixels": int(raw.sum()), "mask_pixels": int(effective.sum()),
                    "mask": destination.relative_to(root).as_posix(),
                })
            overlay = render_composite_overlay(staged, masks, root / "overlay.jpg")
        report.update(
            status="complete", objects=measurements,
            elapsed_seconds=time.perf_counter() - started,
        )
    except Exception as exc:
        report.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)})
        raise
    finally:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return {"overlay": str(overlay), "preview_id": preview_id, "report": report}
