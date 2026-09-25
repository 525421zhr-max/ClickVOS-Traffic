"""Run one reproducible multi-object SAM2 session on ordered JPEG frames."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
from PIL import Image

from clickvos.config import load_config
from clickvos.sam2_engine import (
    FramePrediction,
    ObjectPrompt,
    PromptPoint,
    Sam2Engine,
    save_boolean_mask_and_overlay,
)


def load_prompts(path: Path) -> tuple[str, tuple[ObjectPrompt, ...]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    prompts = []
    for entry in payload["objects"]:
        points = tuple(PromptPoint(x, y, True) for x, y in entry["positive"])
        points += tuple(PromptPoint(x, y, False) for x, y in entry.get("negative", []))
        prompts.append(ObjectPrompt(int(entry["object_id"]), entry["category"], 0, points))
    ids = [prompt.object_id for prompt in prompts]
    if not prompts or len(ids) != len(set(ids)):
        raise ValueError("prompt config needs distinct object IDs")
    return payload["sequence"], tuple(prompts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames-dir", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--prompt-config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--app-config", type=Path, default=Path("configs/default.json"))
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    frames = sorted(args.frames_dir.glob("*.jpg"))
    if not frames or [frame.name for frame in frames] != [f"{i:05d}.jpg" for i in range(len(frames))]:
        raise SystemExit("frames must be named contiguously from 00000.jpg")
    if args.output.exists():
        raise SystemExit(f"output already exists: {args.output}")
    sequence, prompts = load_prompts(args.prompt_config)
    config = load_config(args.app_config)
    if sequence != args.frames_dir.name:
        raise SystemExit("prompt sequence and frame directory name do not match")
    with Image.open(frames[0]) as first_frame:
        width, height = first_frame.size
    for prompt in prompts:
        prompt.validate(width, height, {category.key for category in config.categories})
    expected_ids = {prompt.object_id for prompt in prompts}
    torch.manual_seed(args.seed)
    engine, model_load_seconds = Sam2Engine.load(config, args.checkpoint)
    if config.model.device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    args.output.mkdir(parents=True)
    counts: dict[int, dict[str, int]] = {object_id: {} for object_id in expected_ids}

    def save_prediction(prediction: FramePrediction) -> None:
        if set(prediction.object_ids) != expected_ids or len(prediction.object_ids) != len(expected_ids):
            raise RuntimeError(f"unexpected object IDs at frame {prediction.frame_index}")
        if not 0 <= prediction.frame_index < len(frames):
            raise RuntimeError(f"frame index out of range: {prediction.frame_index}")
        name = f"{prediction.frame_index:05d}"
        for object_id, mask in zip(prediction.object_ids, prediction.masks, strict=True):
            object_root = args.output / f"object_{object_id:03d}"
            masks_dir = object_root / "masks"
            overlays_dir = object_root / "overlays"
            masks_dir.mkdir(parents=True, exist_ok=True)
            overlays_dir.mkdir(parents=True, exist_ok=True)
            pixels, _, _ = save_boolean_mask_and_overlay(
                mask,
                frames[prediction.frame_index],
                masks_dir / f"{name}.png",
                overlays_dir / f"{name}.jpg",
            )
            counts[object_id][f"{name}.png"] = pixels

    started = time.perf_counter()
    with torch.inference_mode():
        session = engine.start_session(frames)
        for prompt in prompts:
            first_prediction = session.add_prompt(prompt)
        save_prediction(first_prediction)
        for prediction in session.propagate():
            save_prediction(prediction)
    inference_seconds = time.perf_counter() - started
    expected_names = {f"{i:05d}.png" for i in range(len(frames))}
    for object_id, pixels in counts.items():
        if set(pixels) != expected_names:
            raise RuntimeError(f"incomplete predictions for object {object_id}")
    peak_memory = int(torch.cuda.max_memory_allocated()) if config.model.device == "cuda" else None
    result = {
        "sequence": sequence,
        "frame_count": len(frames),
        "model": config.model.name,
        "model_config": config.model.config,
        "checkpoint_sha256": config.model.checkpoint_sha256,
        "seed": args.seed,
        "frame_size_wh": [width, height],
        "torch": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0) if config.model.device == "cuda" else None,
        "postprocessing": "none",
        "model_load_seconds": model_load_seconds,
        "inference_seconds": inference_seconds,
        "fps_including_state_init": len(frames) / inference_seconds,
        "peak_cuda_memory_bytes": peak_memory,
        "objects": [
            {
                "object_id": prompt.object_id,
                "category": prompt.category,
                "positive": [[point.x, point.y] for point in prompt.points if point.positive],
                "negative": [[point.x, point.y] for point in prompt.points if not point.positive],
                "saved_mask_count": len(counts[prompt.object_id]),
                "mask_foreground_pixels": counts[prompt.object_id],
            }
            for prompt in prompts
        ],
    }
    (args.output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "objects"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
