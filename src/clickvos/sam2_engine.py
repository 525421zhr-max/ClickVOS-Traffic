"""Reusable SAM2 single-object video propagation service."""

from __future__ import annotations

import hashlib
import time
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Protocol

import numpy as np
import torch
from PIL import Image

from clickvos.config import AppConfig
from clickvos.errors import ClickVOSError, ErrorCode
from clickvos.mask_processing import keep_largest_component, mask_boundary


class Predictor(Protocol):
    def init_state(self, video_path: str, **kwargs: Any) -> Any: ...
    def add_new_points_or_box(self, state: Any, **kwargs: Any) -> tuple[Any, Any, Any]: ...
    def propagate_in_video(self, state: Any) -> Any: ...


@dataclass(frozen=True)
class PromptPoint:
    x: float
    y: float
    positive: bool = True


@dataclass(frozen=True)
class ObjectPrompt:
    object_id: int
    category: str
    frame_index: int
    points: tuple[PromptPoint, ...]

    def validate(
        self,
        width: int,
        height: int,
        categories: set[str],
        require_positive: bool = True,
    ) -> None:
        if self.object_id <= 0:
            raise ValueError("object_id must be positive")
        if self.category not in categories:
            raise ValueError(f"unsupported category: {self.category}")
        if self.frame_index < 0:
            raise ValueError("frame_index must not be negative")
        if not self.points:
            raise ValueError("at least one point is required")
        if require_positive and not any(point.positive for point in self.points):
            raise ValueError("at least one positive point is required")
        for point in self.points:
            if not 0 <= point.x < width or not 0 <= point.y < height:
                raise ValueError(f"point ({point.x}, {point.y}) is outside {width}x{height}")


@dataclass(frozen=True)
class PropagationResult:
    object_id: int
    category: str
    frame_count: int
    propagation_yield_count: int
    postprocessing: str
    mask_foreground_pixels: dict[str, int]
    raw_mask_foreground_pixels: dict[str, int]
    mask_component_counts: dict[str, int]
    inference_seconds: float
    peak_cuda_memory_bytes: int | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FramePrediction:
    frame_index: int
    object_ids: tuple[int, ...]
    masks: tuple[np.ndarray, ...]


def logits_to_masks(logits: torch.Tensor) -> tuple[np.ndarray, ...]:
    values = (logits > 0).detach().cpu().numpy()
    if values.ndim == 4 and values.shape[1] == 1:
        values = values[:, 0]
    if values.ndim != 3:
        raise ValueError(f"expected object masks shaped NxHxW, got {values.shape}")
    return tuple(values[index].astype(bool) for index in range(values.shape[0]))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_mask_and_overlay(
    logits: torch.Tensor,
    frame_path: Path,
    mask_path: Path,
    overlay_path: Path,
    keep_largest: bool = False,
) -> tuple[int, int, int]:
    mask = (logits > 0).detach().cpu().numpy().squeeze().astype(bool)
    return save_boolean_mask_and_overlay(
        mask, frame_path, mask_path, overlay_path, keep_largest
    )


def save_boolean_mask_and_overlay(
    mask: np.ndarray,
    frame_path: Path,
    mask_path: Path,
    overlay_path: Path,
    keep_largest: bool = False,
) -> tuple[int, int, int]:
    mask = mask.astype(bool, copy=False)
    if mask.ndim != 2:
        raise ValueError(f"expected a 2D mask, got shape {mask.shape}")
    components = keep_largest_component(mask)
    if keep_largest:
        mask = components.mask
    Image.fromarray(mask.astype(np.uint8) * 255).save(mask_path)
    frame = np.asarray(Image.open(frame_path).convert("RGB"), dtype=np.float32)
    if frame.shape[:2] != mask.shape:
        raise ValueError(f"mask shape {mask.shape} does not match frame shape {frame.shape[:2]}")
    green = np.zeros_like(frame)
    green[..., 1] = 255
    frame[mask] = frame[mask] * 0.55 + green[mask] * 0.45
    frame[mask_boundary(mask)] = np.array([255, 230, 0], dtype=np.float32)
    Image.fromarray(frame.astype(np.uint8)).save(overlay_path, quality=92)
    return int(mask.sum()), components.raw_foreground_pixels, components.component_count


class Sam2Engine:
    def __init__(self, config: AppConfig, predictor: Predictor) -> None:
        self.config = config
        self.predictor = predictor

    @classmethod
    def load(
        cls,
        config: AppConfig,
        checkpoint: Path,
        predictor_factory: Callable[..., Predictor] | None = None,
    ) -> tuple["Sam2Engine", float]:
        checkpoint = checkpoint.expanduser().resolve()
        if not checkpoint.is_file():
            raise ClickVOSError(ErrorCode.DEPENDENCY_MISSING, "找不到 SAM2 权重文件。", str(checkpoint))
        actual_hash = file_sha256(checkpoint)
        if actual_hash != config.model.checkpoint_sha256:
            raise ClickVOSError(
                ErrorCode.CONFIG_INVALID,
                "SAM2 权重校验失败。",
                f"expected={config.model.checkpoint_sha256}, actual={actual_hash}",
            )
        if config.model.device == "cuda" and not torch.cuda.is_available():
            raise ClickVOSError(ErrorCode.DEPENDENCY_MISSING, "CUDA 当前不可用，无法加载 SAM2。")
        if predictor_factory is None:
            from sam2.build_sam import build_sam2_video_predictor

            predictor_factory = build_sam2_video_predictor
        started = time.perf_counter()
        predictor = predictor_factory(config.model.config, str(checkpoint), device=config.model.device)
        return cls(config, predictor), time.perf_counter() - started

    def start_session(self, frames: list[Path]) -> "Sam2Session":
        return Sam2Session(self.config, self.predictor, frames)

    def propagate_single(
        self,
        frames: list[Path],
        prompt: ObjectPrompt,
        masks_dir: Path,
        overlays_dir: Path,
        keep_largest_component_only: bool = False,
    ) -> PropagationResult:
        if not frames:
            raise ValueError("frames must not be empty")
        with Image.open(frames[0]) as first_frame:
            width, height = first_frame.size
        prompt.validate(width, height, {item.key for item in self.config.categories})
        if prompt.frame_index >= len(frames):
            raise ValueError("prompt frame is outside the extracted frame sequence")
        masks_dir.mkdir(parents=True, exist_ok=True)
        overlays_dir.mkdir(parents=True, exist_ok=True)
        if any(masks_dir.iterdir()) or any(overlays_dir.iterdir()):
            raise ClickVOSError(ErrorCode.TASK_CONFLICT, "输出目录已有分割结果，请创建新任务。")

        points = np.asarray([(point.x, point.y) for point in prompt.points], dtype=np.float32)
        labels = np.asarray([1 if point.positive else 0 for point in prompt.points], dtype=np.int32)
        pixel_counts: dict[str, int] = {}
        raw_pixel_counts: dict[str, int] = {}
        component_counts: dict[str, int] = {}
        if self.config.model.device == "cuda":
            torch.cuda.reset_peak_memory_stats()
            inference_context = torch.inference_mode()
            autocast_context = torch.autocast("cuda", dtype=torch.bfloat16)
        else:
            inference_context = torch.inference_mode()
            autocast_context = nullcontext()

        started = time.perf_counter()
        with inference_context, autocast_context:
            state = self.predictor.init_state(
                str(frames[0].parent),
                offload_video_to_cpu=self.config.model.offload_video_to_cpu,
                offload_state_to_cpu=self.config.model.offload_state_to_cpu,
            )
            _, object_ids, first_logits = self.predictor.add_new_points_or_box(
                state,
                frame_idx=prompt.frame_index,
                obj_id=prompt.object_id,
                points=points,
                labels=labels,
            )
            if list(object_ids) != [prompt.object_id]:
                raise RuntimeError(f"predictor returned unexpected object IDs: {list(object_ids)}")
            prompt_stem = f"{prompt.frame_index:05d}"
            saved, raw, components = save_mask_and_overlay(
                first_logits[0],
                frames[prompt.frame_index],
                masks_dir / f"{prompt_stem}.png",
                overlays_dir / f"{prompt_stem}.jpg",
                keep_largest_component_only,
            )
            pixel_counts[f"{prompt_stem}.png"] = saved
            raw_pixel_counts[f"{prompt_stem}.png"] = raw
            component_counts[f"{prompt_stem}.png"] = components
            propagation_yields = 0
            for frame_index, propagated_ids, logits in self.predictor.propagate_in_video(state):
                if list(propagated_ids) != [prompt.object_id]:
                    raise RuntimeError("object IDs changed during propagation")
                if not 0 <= frame_index < len(frames):
                    raise RuntimeError(f"predictor returned invalid frame index: {frame_index}")
                stem = f"{frame_index:05d}"
                saved, raw, components = save_mask_and_overlay(
                    logits[0], frames[frame_index], masks_dir / f"{stem}.png", overlays_dir / f"{stem}.jpg",
                    keep_largest_component_only,
                )
                pixel_counts[f"{stem}.png"] = saved
                raw_pixel_counts[f"{stem}.png"] = raw
                component_counts[f"{stem}.png"] = components
                propagation_yields += 1
        elapsed = time.perf_counter() - started
        peak_memory = torch.cuda.max_memory_allocated() if self.config.model.device == "cuda" else None
        return PropagationResult(
            object_id=prompt.object_id,
            category=prompt.category,
            frame_count=len(frames),
            propagation_yield_count=propagation_yields,
            postprocessing="largest_connected_component" if keep_largest_component_only else "none",
            mask_foreground_pixels=pixel_counts,
            raw_mask_foreground_pixels=raw_pixel_counts,
            mask_component_counts=component_counts,
            inference_seconds=elapsed,
            peak_cuda_memory_bytes=peak_memory,
        )


class Sam2Session:
    """Stateful multi-object session supporting prompts on later correction frames."""

    def __init__(self, config: AppConfig, predictor: Predictor, frames: list[Path]) -> None:
        if not frames:
            raise ValueError("frames must not be empty")
        self.config = config
        self.predictor = predictor
        self.frames = frames
        with Image.open(frames[0]) as first_frame:
            self.width, self.height = first_frame.size
        self.state = predictor.init_state(
            str(frames[0].parent),
            offload_video_to_cpu=config.model.offload_video_to_cpu,
            offload_state_to_cpu=config.model.offload_state_to_cpu,
        )
        self.objects: dict[int, str] = {}

    def _autocast(self) -> Any:
        if self.config.model.device == "cuda":
            return torch.autocast("cuda", dtype=torch.bfloat16)
        return nullcontext()

    def add_prompt(self, prompt: ObjectPrompt, clear_old_points: bool = True) -> FramePrediction:
        prompt.validate(
            self.width,
            self.height,
            {category.key for category in self.config.categories},
            require_positive=prompt.object_id not in self.objects,
        )
        if prompt.frame_index >= len(self.frames):
            raise ValueError("prompt frame is outside the extracted frame sequence")
        existing_category = self.objects.get(prompt.object_id)
        if existing_category is not None and existing_category != prompt.category:
            raise ValueError("an object category cannot change within a task")
        points = np.asarray([(point.x, point.y) for point in prompt.points], dtype=np.float32)
        labels = np.asarray([1 if point.positive else 0 for point in prompt.points], dtype=np.int32)
        with self._autocast():
            _, object_ids, logits = self.predictor.add_new_points_or_box(
                self.state,
                frame_idx=prompt.frame_index,
                obj_id=prompt.object_id,
                points=points,
                labels=labels,
                clear_old_points=clear_old_points,
            )
        ids = tuple(int(item) for item in object_ids)
        self.objects[prompt.object_id] = prompt.category
        return FramePrediction(prompt.frame_index, ids, logits_to_masks(logits))

    def propagate(
        self,
        start_frame_idx: int | None = None,
        max_frame_num_to_track: int | None = None,
        reverse: bool = False,
    ) -> Iterator[FramePrediction]:
        if not self.objects:
            raise ValueError("add at least one object prompt before propagation")
        if start_frame_idx is not None and not 0 <= start_frame_idx < len(self.frames):
            raise ValueError("start_frame_idx is outside the frame sequence")
        with self._autocast():
            for frame_index, object_ids, logits in self.predictor.propagate_in_video(
                self.state,
                start_frame_idx=start_frame_idx,
                max_frame_num_to_track=max_frame_num_to_track,
                reverse=reverse,
            ):
                ids = tuple(int(item) for item in object_ids)
                masks = logits_to_masks(logits)
                if len(ids) != len(masks):
                    raise RuntimeError("predictor returned different object ID and mask counts")
                yield FramePrediction(int(frame_index), ids, masks)
