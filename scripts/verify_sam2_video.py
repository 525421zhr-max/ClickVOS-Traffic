"""Run a deterministic SAM2 video smoke test and save binary PNG masks."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw
from sam2.build_sam import build_sam2_video_predictor


EXPECTED_TINY_SHA256 = (
    "7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_sample_video(work_dir: Path, frame_count: int = 8) -> Path:
    source_dir = work_dir / "generated_source_frames"
    source_dir.mkdir(parents=True, exist_ok=True)
    for index in range(frame_count):
        image = Image.new("RGB", (256, 256), (220, 220, 220))
        draw = ImageDraw.Draw(image)
        left = 40 + 5 * index
        draw.rectangle((left, 80, left + 79, 159), fill=(210, 35, 35))
        image.save(source_dir / f"{index:05d}.png")

    video_path = work_dir / "sample-moving-square.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            "4",
            "-i",
            str(source_dir / "%05d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video_path),
        ],
        check=True,
    )
    return video_path


def extract_frames(video_path: Path, frames_dir: Path) -> list[Path]:
    frames_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-q:v",
            "2",
            str(frames_dir / "%05d.jpg"),
        ],
        check=True,
    )
    frames = sorted(frames_dir.glob("*.jpg"))
    if not frames:
        raise RuntimeError("ffmpeg did not produce any JPEG frames")
    return frames


def save_mask(mask_logits: torch.Tensor, path: Path) -> int:
    mask = (mask_logits > 0).detach().cpu().numpy().squeeze()
    Image.fromarray(mask.astype(np.uint8) * 255, mode="L").save(path)
    return int(mask.sum())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    actual_hash = sha256(args.checkpoint)
    if actual_hash != EXPECTED_TINY_SHA256:
        raise SystemExit(
            f"checkpoint SHA-256 mismatch: expected {EXPECTED_TINY_SHA256}, got {actual_hash}"
        )
    if not torch.cuda.is_available():
        raise SystemExit("CUDA is not available")

    args.output.mkdir(parents=True, exist_ok=True)
    video_path = make_sample_video(args.output)
    frames_dir = args.output / "extracted_frames"
    frames = extract_frames(video_path, frames_dir)
    masks_dir = args.output / "masks"
    masks_dir.mkdir(parents=True, exist_ok=True)

    torch.cuda.reset_peak_memory_stats()
    predictor = build_sam2_video_predictor(
        "configs/sam2.1/sam2.1_hiera_t.yaml",
        str(args.checkpoint),
        device="cuda",
    )

    points = np.array([[80.0, 120.0], [210.0, 30.0]], dtype=np.float32)
    labels = np.array([1, 0], dtype=np.int32)
    pixel_counts: dict[str, int] = {}

    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        state = predictor.init_state(
            str(frames_dir), offload_video_to_cpu=True, offload_state_to_cpu=True
        )
        _, object_ids, first_logits = predictor.add_new_points_or_box(
            state, frame_idx=0, obj_id=1, points=points, labels=labels
        )
        pixel_counts["00000.png"] = save_mask(first_logits[0], masks_dir / "00000.png")

        propagated = 0
        for frame_index, propagated_ids, logits in predictor.propagate_in_video(state):
            if list(propagated_ids) != list(object_ids):
                raise RuntimeError("object IDs changed during propagation")
            name = f"{frame_index:05d}.png"
            pixel_counts[name] = save_mask(logits[0], masks_dir / name)
            propagated += 1

    result = {
        "checkpoint": str(args.checkpoint),
        "checkpoint_sha256": actual_hash,
        "python_torch": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0),
        "video": str(video_path),
        "extracted_frame_count": len(frames),
        "propagation_yield_count": propagated,
        "saved_mask_count": len(list(masks_dir.glob("*.png"))),
        "mask_foreground_pixels": pixel_counts,
        "peak_cuda_memory_bytes": torch.cuda.max_memory_allocated(),
        "prompt_points_xy": points.tolist(),
        "prompt_labels": labels.tolist(),
    }
    result_path = args.output / "result.json"
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
