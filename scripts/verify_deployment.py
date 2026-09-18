"""Fail fast when a local or container deployment is missing a GPU or model."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
from pathlib import Path

import torch

from clickvos.config import load_config
from clickvos.sam2_engine import file_sha256


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify ClickVOS deployment prerequisites")
    parser.add_argument("--config", type=Path, default=Path("configs/default.json"))
    parser.add_argument("--checkpoint", type=Path, required=True)
    args = parser.parse_args()

    config = load_config(args.config)
    checkpoint = args.checkpoint.expanduser().resolve()
    if not checkpoint.is_file():
        raise SystemExit(f"checkpoint not found: {checkpoint}")
    actual_hash = file_sha256(checkpoint)
    if actual_hash != config.model.checkpoint_sha256:
        raise SystemExit(
            "checkpoint SHA-256 mismatch: "
            f"expected={config.model.checkpoint_sha256}, actual={actual_hash}"
        )
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise SystemExit("ffmpeg and ffprobe must both be available")
    if config.model.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA is required by the selected config but is not available")

    result = {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torch_cuda_runtime": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": actual_hash,
        "config": str(args.config.resolve()),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
