"""Run a reproducible SAM2 propagation test on an existing video."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from sam2.build_sam import build_sam2_video_predictor

from clickvos.video_io import extract_frames


TINY_SHA256 = "7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def point(value: str) -> tuple[float, float]:
    try:
        x, y = value.split(",", maxsplit=1)
        return float(x), float(y)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("point must use x,y format") from exc


def save_mask_and_overlay(
    logits: torch.Tensor, frame_path: Path, mask_path: Path, overlay_path: Path
) -> int:
    mask = (logits > 0).detach().cpu().numpy().squeeze()
    Image.fromarray(mask.astype(np.uint8) * 255, mode="L").save(mask_path)

    frame = np.asarray(Image.open(frame_path).convert("RGB"), dtype=np.float32)
    green = np.zeros_like(frame)
    green[..., 1] = 255
    frame[mask] = frame[mask] * 0.55 + green[mask] * 0.45
    Image.fromarray(frame.astype(np.uint8)).save(overlay_path, quality=92)
    return int(mask.sum())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--positive", required=True, action="append", type=point)
    parser.add_argument("--negative", action="append", default=[], type=point)
    parser.add_argument(
        "--config", default="configs/sam2.1/sam2.1_hiera_t.yaml"
    )
    args = parser.parse_args()

    checkpoint_hash = file_sha256(args.checkpoint)
    if checkpoint_hash != TINY_SHA256:
        raise SystemExit(f"unexpected checkpoint SHA-256: {checkpoint_hash}")
    if not torch.cuda.is_available():
        raise SystemExit("CUDA is not available")

    args.output.mkdir(parents=True, exist_ok=True)
    frames_dir = args.output / "frames"
    masks_dir = args.output / "masks"
    overlays_dir = args.output / "overlays"
    masks_dir.mkdir(parents=True, exist_ok=True)
    overlays_dir.mkdir(parents=True, exist_ok=True)

    extract_started = time.perf_counter()
    frames = extract_frames(args.video, frames_dir)
    extraction_seconds = time.perf_counter() - extract_started

    torch.cuda.reset_peak_memory_stats()
    load_started = time.perf_counter()
    predictor = build_sam2_video_predictor(
        args.config, str(args.checkpoint), device="cuda"
    )
    model_load_seconds = time.perf_counter() - load_started

    points = np.asarray(args.positive + args.negative, dtype=np.float32)
    labels = np.asarray(
        [1] * len(args.positive) + [0] * len(args.negative), dtype=np.int32
    )
    pixel_counts: dict[str, int] = {}

    inference_started = time.perf_counter()
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        state = predictor.init_state(
            str(frames_dir), offload_video_to_cpu=True, offload_state_to_cpu=True
        )
        _, object_ids, first_logits = predictor.add_new_points_or_box(
            state, frame_idx=0, obj_id=1, points=points, labels=labels
        )
        pixel_counts["00000.png"] = save_mask_and_overlay(
            first_logits[0], frames[0], masks_dir / "00000.png", overlays_dir / "00000.jpg"
        )

        propagation_yields = 0
        for frame_index, propagated_ids, logits in predictor.propagate_in_video(state):
            if list(propagated_ids) != list(object_ids):
                raise RuntimeError("object IDs changed during propagation")
            stem = f"{frame_index:05d}"
            pixel_counts[f"{stem}.png"] = save_mask_and_overlay(
                logits[0], frames[frame_index], masks_dir / f"{stem}.png",
                overlays_dir / f"{stem}.jpg",
            )
            propagation_yields += 1
    inference_seconds = time.perf_counter() - inference_started

    result = {
        "video": str(args.video),
        "video_sha256": file_sha256(args.video),
        "checkpoint_sha256": checkpoint_hash,
        "config": args.config,
        "torch": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0),
        "extracted_frame_count": len(frames),
        "saved_mask_count": len(list(masks_dir.glob("*.png"))),
        "saved_overlay_count": len(list(overlays_dir.glob("*.jpg"))),
        "propagation_yield_count": propagation_yields,
        "prompt_points_xy": points.tolist(),
        "prompt_labels": labels.tolist(),
        "mask_foreground_pixels": pixel_counts,
        "extraction_seconds": extraction_seconds,
        "model_load_seconds": model_load_seconds,
        "inference_seconds": inference_seconds,
        "propagation_fps_including_state_init": len(frames) / inference_seconds,
        "peak_cuda_memory_bytes": torch.cuda.max_memory_allocated(),
    }
    (args.output / "result.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
