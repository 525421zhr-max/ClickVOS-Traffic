"""Export ClickVOS frame sequences to user-facing artifacts."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Sequence

from clickvos.errors import ClickVOSError, ErrorCode


def build_preview_video(overlays_dir: Path, output: Path, fps: float) -> Path:
    if fps <= 0:
        raise ValueError("fps must be positive")
    frames = sorted(overlays_dir.glob("*.jpg"))
    if not frames:
        raise ClickVOSError(ErrorCode.FRAME_EXTRACTION_FAILED, "没有可导出的叠加帧。", str(overlays_dir))
    expected = [f"{index:05d}.jpg" for index in range(len(frames))]
    actual = [frame.name for frame in frames]
    if actual != expected:
        raise ClickVOSError(ErrorCode.FRAME_EXTRACTION_FAILED, "叠加帧编号不连续，无法导出视频。")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error", "-framerate", str(fps),
                "-i", str(overlays_dir / "%05d.jpg"), "-c:v", "libx264",
                "-pix_fmt", "yuv420p", str(output),
            ],
            check=True,
        )
    except FileNotFoundError as exc:
        raise ClickVOSError(ErrorCode.DEPENDENCY_MISSING, "缺少 FFmpeg，无法导出预览视频。") from exc
    except subprocess.CalledProcessError as exc:
        raise ClickVOSError(ErrorCode.FRAME_EXTRACTION_FAILED, "预览视频导出失败。", str(exc)) from exc
    return output


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export overlay JPEG frames as an MP4 preview")
    parser.add_argument("overlays", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fps", type=float, required=True)
    args = parser.parse_args(argv)
    print(build_preview_video(args.overlays, args.output, args.fps))


if __name__ == "__main__":
    main()
