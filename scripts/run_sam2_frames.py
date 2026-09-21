"""Run SAM2 propagation on an existing ordered JPEG frame directory."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from pathlib import Path

import torch

from clickvos.config import load_config
from clickvos.sam2_engine import ObjectPrompt, PromptPoint, Sam2Engine, file_sha256


def point(value: str) -> tuple[float, float]:
    try:
        x, y = value.split(",", maxsplit=1)
        return float(x), float(y)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("point must use x,y format") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames-dir", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--positive", required=True, action="append", type=point)
    parser.add_argument("--negative", action="append", default=[], type=point)
    parser.add_argument("--category", default="vehicle")
    parser.add_argument("--object-id", default=1, type=int)
    parser.add_argument("--keep-largest-component", action="store_true")
    parser.add_argument("--app-config", default=Path("configs/default.json"), type=Path)
    parser.add_argument("--config", default="configs/sam2.1/sam2.1_hiera_t.yaml")
    args = parser.parse_args()

    frames = sorted(args.frames_dir.glob("*.jpg"))
    if not frames:
        raise SystemExit(f"no JPEG frames found: {args.frames_dir}")
    expected = [f"{index:05d}.jpg" for index in range(len(frames))]
    if [frame.name for frame in frames] != expected:
        raise SystemExit("frames must be named contiguously from 00000.jpg")

    app_config = load_config(args.app_config)
    app_config = replace(app_config, model=replace(app_config.model, config=args.config))
    masks_dir = args.output / "masks"
    overlays_dir = args.output / "overlays"
    masks_dir.mkdir(parents=True, exist_ok=True)
    overlays_dir.mkdir(parents=True, exist_ok=True)
    if any(masks_dir.iterdir()) or any(overlays_dir.iterdir()):
        raise SystemExit(f"output mask or overlay directory is not empty: {args.output}")

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
    started = time.perf_counter()
    propagation = engine.propagate_single(
        frames,
        prompt,
        masks_dir,
        overlays_dir,
        keep_largest_component_only=args.keep_largest_component,
    )
    total_seconds = time.perf_counter() - started
    result = {
        "frames_directory": str(args.frames_dir),
        "checkpoint_sha256": file_sha256(args.checkpoint),
        "config": args.config,
        "torch": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0),
        "frame_count": len(frames),
        "saved_mask_count": len(list(masks_dir.glob("*.png"))),
        "saved_overlay_count": len(list(overlays_dir.glob("*.jpg"))),
        "object_id": prompt.object_id,
        "category": prompt.category,
        "prompt_points_xy": [[item.x, item.y] for item in prompt.points],
        "prompt_labels": [1 if item.positive else 0 for item in prompt.points],
        "postprocessing": propagation.postprocessing,
        "model_load_seconds": model_load_seconds,
        "inference_seconds": propagation.inference_seconds,
        "end_to_end_propagation_seconds": total_seconds,
        "propagation_fps_including_state_init": len(frames) / propagation.inference_seconds,
        "peak_cuda_memory_bytes": propagation.peak_cuda_memory_bytes,
        "mask_foreground_pixels": propagation.mask_foreground_pixels,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
