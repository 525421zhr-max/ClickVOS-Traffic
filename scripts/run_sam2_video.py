"""Run a reproducible SAM2 propagation test on an existing video."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from pathlib import Path

import torch

from clickvos.config import load_config
from clickvos.sam2_engine import ObjectPrompt, PromptPoint, Sam2Engine, file_sha256
from clickvos.video_io import extract_frames

def point(value: str) -> tuple[float, float]:
    try:
        x, y = value.split(",", maxsplit=1)
        return float(x), float(y)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("point must use x,y format") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--positive", required=True, action="append", type=point)
    parser.add_argument("--negative", action="append", default=[], type=point)
    parser.add_argument("--category", default="vehicle")
    parser.add_argument("--object-id", default=1, type=int)
    parser.add_argument("--keep-largest-component", action="store_true")
    parser.add_argument("--app-config", default=Path("configs/default.json"), type=Path)
    parser.add_argument(
        "--config", default="configs/sam2.1/sam2.1_hiera_t.yaml"
    )
    args = parser.parse_args()

    app_config = load_config(args.app_config)
    app_config = replace(app_config, model=replace(app_config.model, config=args.config))

    args.output.mkdir(parents=True, exist_ok=True)
    frames_dir = args.output / "frames"
    masks_dir = args.output / "masks"
    overlays_dir = args.output / "overlays"
    masks_dir.mkdir(parents=True, exist_ok=True)
    overlays_dir.mkdir(parents=True, exist_ok=True)

    extract_started = time.perf_counter()
    frames = extract_frames(
        args.video,
        frames_dir,
        quality=app_config.video.jpeg_quality,
        max_bytes=app_config.video.max_upload_bytes,
        max_frames=app_config.video.max_frames,
    )
    extraction_seconds = time.perf_counter() - extract_started

    engine, model_load_seconds = Sam2Engine.load(app_config, args.checkpoint)
    prompt = ObjectPrompt(
        object_id=args.object_id,
        category=args.category,
        frame_index=0,
        points=tuple(
            [PromptPoint(x, y, True) for x, y in args.positive]
            + [PromptPoint(x, y, False) for x, y in args.negative]
        ),
    )
    propagation = engine.propagate_single(
        frames,
        prompt,
        masks_dir,
        overlays_dir,
        keep_largest_component_only=args.keep_largest_component,
    )

    result = {
        "video": str(args.video),
        "video_sha256": file_sha256(args.video),
        "checkpoint_sha256": file_sha256(args.checkpoint),
        "config": args.config,
        "torch": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0),
        "extracted_frame_count": len(frames),
        "saved_mask_count": len(list(masks_dir.glob("*.png"))),
        "saved_overlay_count": len(list(overlays_dir.glob("*.jpg"))),
        "object_id": prompt.object_id,
        "category": prompt.category,
        "propagation_yield_count": propagation.propagation_yield_count,
        "prompt_points_xy": [[item.x, item.y] for item in prompt.points],
        "prompt_labels": [1 if item.positive else 0 for item in prompt.points],
        "mask_foreground_pixels": propagation.mask_foreground_pixels,
        "raw_mask_foreground_pixels": propagation.raw_mask_foreground_pixels,
        "mask_component_counts": propagation.mask_component_counts,
        "postprocessing": propagation.postprocessing,
        "extraction_seconds": extraction_seconds,
        "model_load_seconds": model_load_seconds,
        "inference_seconds": propagation.inference_seconds,
        "propagation_fps_including_state_init": len(frames) / propagation.inference_seconds,
        "peak_cuda_memory_bytes": propagation.peak_cuda_memory_bytes,
    }
    (args.output / "result.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
