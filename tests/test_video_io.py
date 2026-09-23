from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from clickvos.errors import ErrorCode
from clickvos.video_io import VideoIOError, create_task_layout, probe_video, validate_video


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
