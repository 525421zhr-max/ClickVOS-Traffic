from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from clickvos.errors import ErrorCode
from clickvos.video_io import (
    VideoIOError,
    VideoMetadata,
    create_task_layout,
    extract_frames,
    prepare_task,
    probe_video,
    validate_video,
)


def test_validate_video_rejects_unknown_extension(tmp_path: Path) -> None:
    file = tmp_path / "sample.txt"
    file.write_bytes(b"not a video")
    with pytest.raises(VideoIOError) as captured:
        validate_video(file)
    assert captured.value.code == ErrorCode.VIDEO_UNSUPPORTED
    assert captured.value.user_message == "不支持该视频格式。"


def test_create_task_layout_creates_expected_directories(tmp_path: Path) -> None:
    layout = create_task_layout(tmp_path, "traffic_001")
    assert layout.root == (tmp_path / "traffic_001").resolve()
    assert all(path.is_dir() for path in (layout.source, layout.frames, layout.masks, layout.overlays, layout.exports))
    assert layout.metadata == layout.root / "task.json"


def test_create_task_layout_rejects_unsafe_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="task ID"):
        create_task_layout(tmp_path, "../outside")


def test_create_task_layout_never_reuses_existing_task(tmp_path: Path) -> None:
    existing = create_task_layout(tmp_path, "traffic_001")
    original = existing.metadata
    original.write_text('{"status":"frames_extracted"}', encoding="utf-8")
    with pytest.raises(VideoIOError) as captured:
        create_task_layout(tmp_path, "traffic_001")
    assert captured.value.code == ErrorCode.TASK_CONFLICT
    assert original.read_text(encoding="utf-8") == '{"status":"frames_extracted"}'


def test_create_task_layout_rejects_empty_existing_directory(tmp_path: Path) -> None:
    (tmp_path / "reserved").mkdir()
    with pytest.raises(VideoIOError) as captured:
        create_task_layout(tmp_path, "reserved")
    assert captured.value.code == ErrorCode.TASK_CONFLICT


def test_probe_video_parses_ffprobe_json(tmp_path: Path) -> None:
    video = tmp_path / "sample.mp4"
    video.write_bytes(b"video")
    payload = {
        "streams": [{
            "width": 960,
            "height": 540,
            "codec_name": "h264",
            "avg_frame_rate": "10/1",
            "nb_frames": "50",
            "duration": "5.000000",
        }],
        "format": {"duration": "5.000000"},
    }
    completed = subprocess.CompletedProcess([], 0, stdout=json.dumps(payload), stderr="")
    with patch("clickvos.video_io.subprocess.run", return_value=completed):
        metadata = probe_video(video)
    assert (metadata.width, metadata.height, metadata.fps) == (960, 540, 10.0)
    assert metadata.frame_count == 50
    assert metadata.duration_seconds == 5.0


def test_prepare_task_keeps_failure_record_and_partial_frames(tmp_path: Path) -> None:
    video = tmp_path / "traffic.mp4"
    video.write_bytes(b"video")
    metadata = VideoMetadata(str(video), 4, 4, 10.0, 2, 0.2, "h264", 5)

    def fail_after_first_frame(source, frames_dir, **kwargs):
        (frames_dir / "00000.jpg").write_bytes(b"partial")
        raise VideoIOError(ErrorCode.FRAME_EXTRACTION_FAILED, "视频抽帧失败。")

    with patch("clickvos.video_io.probe_video", return_value=metadata), patch(
        "clickvos.video_io.extract_frames", side_effect=fail_after_first_frame
    ):
        with pytest.raises(VideoIOError) as captured:
            prepare_task(video, tmp_path / "tasks", "failed-task")

    assert captured.value.code == ErrorCode.FRAME_EXTRACTION_FAILED
    root = tmp_path / "tasks" / "failed-task"
    record = json.loads((root / "task.json").read_text(encoding="utf-8"))
    assert record["status"] == "frame_extraction_failed"
    assert record["extracted_frame_count"] == 1
    assert record["error"] == {
        "code": "frame_extraction_failed",
        "message": "视频抽帧失败。",
    }
    assert (root / "frames" / "00000.jpg").read_bytes() == b"partial"
    assert not (root / "task.json.tmp").exists()


def test_prepare_task_marks_success_after_frame_extraction(tmp_path: Path) -> None:
    video = tmp_path / "traffic.mp4"
    video.write_bytes(b"video")
    metadata = VideoMetadata(str(video), 4, 4, 10.0, 2, 0.2, "h264", 5)

    def write_frames(source, frames_dir, **kwargs):
        frames = [frames_dir / f"{index:05d}.jpg" for index in range(2)]
        for frame in frames:
            frame.write_bytes(b"frame")
        return frames

    with patch("clickvos.video_io.probe_video", return_value=metadata), patch(
        "clickvos.video_io.extract_frames", side_effect=write_frames
    ):
        layout, _, frames = prepare_task(video, tmp_path / "tasks", "ok-task")
    record = json.loads(layout.metadata.read_text(encoding="utf-8"))
    assert record["status"] == "frames_extracted"
    assert record["extracted_frame_count"] == len(frames) == 2
    assert "error" not in record


def test_prepare_task_rejects_reported_frame_overflow_before_creating_task(tmp_path: Path) -> None:
    video = tmp_path / "traffic.mp4"
    video.write_bytes(b"video")
    metadata = VideoMetadata(str(video), 4, 4, 30.0, 301, 10.1, "h264", 5)
    with patch("clickvos.video_io.probe_video", return_value=metadata):
        with pytest.raises(VideoIOError) as captured:
            prepare_task(video, tmp_path / "tasks", "too-long", max_frames=300)
    assert captured.value.code == ErrorCode.VIDEO_TOO_MANY_FRAMES
    assert not (tmp_path / "tasks" / "too-long").exists()


def test_extract_frames_caps_unknown_length_before_accepting(tmp_path: Path) -> None:
    video = tmp_path / "traffic.mp4"
    video.write_bytes(b"video")
    frames_dir = tmp_path / "frames"
    commands = []

    def fake_ffmpeg(command, **kwargs):
        commands.append(command)
        for index in range(1, 5):
            (frames_dir / f"{index:05d}.jpg").write_bytes(b"frame")
        return subprocess.CompletedProcess(command, 0)

    with patch("clickvos.video_io.subprocess.run", side_effect=fake_ffmpeg):
        with pytest.raises(VideoIOError) as captured:
            extract_frames(video, frames_dir, max_frames=3)
    assert captured.value.code == ErrorCode.VIDEO_TOO_MANY_FRAMES
    assert commands[0][commands[0].index("-frames:v") + 1] == "4"
    assert len(list(frames_dir.glob("*.jpg"))) == 4
