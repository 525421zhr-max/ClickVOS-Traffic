"""Video validation, metadata inspection, frame extraction, and task layout."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

from clickvos.config import load_config
from clickvos.errors import ClickVOSError, ErrorCode


SUPPORTED_VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".avi", ".mkv", ".webm"})
DEFAULT_MAX_VIDEO_BYTES = 200 * 1024 * 1024
TASK_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


class VideoIOError(ClickVOSError):
    """Backward-compatible typed error for video input failures."""


@dataclass(frozen=True)
class VideoMetadata:
    path: str
    width: int
    height: int
    fps: float
    frame_count: int | None
    duration_seconds: float | None
    codec: str
    size_bytes: int


@dataclass(frozen=True)
class TaskLayout:
    root: Path
    source: Path
    frames: Path
    masks: Path
    overlays: Path
    exports: Path
    metadata: Path

    def create(self) -> None:
        for directory in (
            self.root,
            self.source,
            self.frames,
            self.masks,
            self.overlays,
            self.exports,
        ):
            directory.mkdir(parents=True, exist_ok=True)


def validate_video(path: Path, max_bytes: int = DEFAULT_MAX_VIDEO_BYTES) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise VideoIOError(ErrorCode.VIDEO_NOT_FOUND, "找不到视频文件。", str(resolved))
    if resolved.suffix.lower() not in SUPPORTED_VIDEO_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_VIDEO_SUFFIXES))
        raise VideoIOError(ErrorCode.VIDEO_UNSUPPORTED, "不支持该视频格式。", f"expected {supported}")
    size = resolved.stat().st_size
    if size <= 0:
        raise VideoIOError(ErrorCode.VIDEO_EMPTY, "视频文件为空。", str(resolved))
    if size > max_bytes:
        raise VideoIOError(ErrorCode.VIDEO_TOO_LARGE, "视频超过上传大小限制。", f"size={size}, limit={max_bytes}")
    return resolved


def _parse_optional_float(value: Any) -> float | None:
    if value in (None, "", "N/A"):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _parse_rate(value: str) -> float:
    numerator, separator, denominator = value.partition("/")
    if not separator:
        rate = float(numerator)
    else:
        rate = float(numerator) / float(denominator)
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError(f"invalid frame rate: {value}")
    return rate


def probe_video(path: Path, max_bytes: int = DEFAULT_MAX_VIDEO_BYTES) -> VideoMetadata:
    video = validate_video(path, max_bytes=max_bytes)
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,codec_name,avg_frame_rate,nb_frames,duration:format=duration",
        "-of",
        "json",
        str(video),
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        payload = json.loads(completed.stdout)
        stream = payload["streams"][0]
        duration = _parse_optional_float(stream.get("duration"))
        if duration is None:
            duration = _parse_optional_float(payload.get("format", {}).get("duration"))
        raw_count = stream.get("nb_frames")
        frame_count = int(raw_count) if raw_count not in (None, "", "N/A") else None
        return VideoMetadata(
            path=str(video),
            width=int(stream["width"]),
            height=int(stream["height"]),
            fps=_parse_rate(stream["avg_frame_rate"]),
            frame_count=frame_count,
            duration_seconds=duration,
            codec=str(stream.get("codec_name", "unknown")),
            size_bytes=video.stat().st_size,
        )
    except FileNotFoundError as exc:
        raise VideoIOError(ErrorCode.DEPENDENCY_MISSING, "缺少 FFmpeg，无法读取视频。", "ffprobe not found") from exc
    except (subprocess.CalledProcessError, KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
        raise VideoIOError(ErrorCode.VIDEO_INSPECTION_FAILED, "无法读取视频信息，请确认文件未损坏。", str(exc)) from exc


def create_task_layout(tasks_root: Path, task_id: str | None = None) -> TaskLayout:
    identifier = task_id or uuid.uuid4().hex[:12]
    if not TASK_ID_PATTERN.fullmatch(identifier):
        raise ValueError("task ID must contain 1-64 ASCII letters, digits, underscores, or hyphens")
    root = tasks_root.expanduser().resolve() / identifier
    layout = TaskLayout(
        root=root,
        source=root / "source",
        frames=root / "frames",
        masks=root / "masks",
        overlays=root / "overlays",
        exports=root / "exports",
        metadata=root / "task.json",
    )
    layout.create()
    return layout


def extract_frames(
    video: Path,
    frames_dir: Path,
    quality: int = 2,
    max_bytes: int = DEFAULT_MAX_VIDEO_BYTES,
) -> list[Path]:
    source = validate_video(video, max_bytes=max_bytes)
    if not 2 <= quality <= 31:
        raise ValueError("JPEG quality must be between 2 and 31")
    frames_dir.mkdir(parents=True, exist_ok=True)
    if any(frames_dir.iterdir()):
        raise VideoIOError(ErrorCode.TASK_CONFLICT, "任务目录已有抽帧结果，请更换任务编号。", str(frames_dir))
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(source), "-q:v", str(quality), str(frames_dir / "%05d.jpg")],
            check=True,
        )
    except FileNotFoundError as exc:
        raise VideoIOError(ErrorCode.DEPENDENCY_MISSING, "缺少 FFmpeg，无法抽取视频帧。", "ffmpeg not found") from exc
    except subprocess.CalledProcessError as exc:
        raise VideoIOError(ErrorCode.FRAME_EXTRACTION_FAILED, "视频抽帧失败，请确认文件可正常播放。", str(source)) from exc
    frames = sorted(frames_dir.glob("*.jpg"))
    if not frames:
        raise VideoIOError(ErrorCode.FRAME_EXTRACTION_FAILED, "视频中没有可读取的画面。")
    return frames


def prepare_task(
    video: Path,
    tasks_root: Path,
    task_id: str | None = None,
    max_bytes: int = DEFAULT_MAX_VIDEO_BYTES,
    quality: int = 2,
) -> tuple[TaskLayout, VideoMetadata, list[Path]]:
    metadata = probe_video(video, max_bytes=max_bytes)
    layout = create_task_layout(tasks_root, task_id)
    frames = extract_frames(video, layout.frames, quality=quality, max_bytes=max_bytes)
    record = {
        "schema_version": 1,
        "task_id": layout.root.name,
        "status": "frames_extracted",
        "video": asdict(metadata),
        "extracted_frame_count": len(frames),
    }
    layout.metadata.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return layout, metadata, frames


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect videos and create ClickVOS task directories")
    parser.add_argument("--config", type=Path, default=Path("configs/default.json"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect", help="print video metadata as JSON")
    inspect_parser.add_argument("video", type=Path)
    prepare_parser = subparsers.add_parser("prepare", help="create a task and extract JPEG frames")
    prepare_parser.add_argument("video", type=Path)
    prepare_parser.add_argument("--tasks-root", type=Path)
    prepare_parser.add_argument("--task-id")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        if args.command == "inspect":
            result = asdict(probe_video(args.video, max_bytes=config.video.max_upload_bytes))
        else:
            layout, metadata, frames = prepare_task(
                args.video,
                args.tasks_root or config.tasks_root,
                args.task_id,
                max_bytes=config.video.max_upload_bytes,
                quality=config.video.jpeg_quality,
            )
            result = {
                "task_directory": str(layout.root),
                "metadata": asdict(metadata),
                "extracted_frame_count": len(frames),
            }
    except (VideoIOError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
