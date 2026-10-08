import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
import torch
from PIL import Image
from fastapi import HTTPException

from clickvos.config import load_config
from clickvos.lazy_frames import BoundedVideoFrames, init_bounded_state
from clickvos.site_api import check_run_resources
from clickvos.video_io import VideoMetadata, VideoIOError, prepare_task
from clickvos.export import build_project_manifest


def test_lazy_frames_match_pinned_eager_after_eviction(tmp_path):
    misc = pytest.importorskip("sam2.utils.misc")
    frames = []
    for i in range(5):
        frame = tmp_path / f"{i:05d}.jpg"
        Image.fromarray(np.random.default_rng(i).integers(0, 256, (12, 18, 3), dtype=np.uint8)).save(frame)
        frames.append(frame)
    eager, h, w = misc.load_video_frames_from_jpg_images(str(tmp_path), 16, True)
    lazy = BoundedVideoFrames(frames, 16, capacity=2)
    for i in [0, 4, 1, 3, 0, 2, 4]:
        assert torch.equal(lazy[i], eager[i])
        assert len(lazy.cache) <= 2
    assert (h, w) == (12, 18)
    with pytest.raises(IndexError):
        lazy[5]


def test_bounded_init_keeps_features_dimensions_and_full_frame_count(tmp_path):
    frames = [tmp_path / f"{i:05d}.jpg" for i in range(4)]
    for frame in frames:
        Image.new("RGB", (18, 12)).save(frame)
    marker = object()
    class Predictor:
        image_size = 16
        def init_state(self, folder, **kwargs):
            assert len(list(Path(folder).glob("*.jpg"))) == 1
            assert Path(folder, "00000.jpg").resolve() == frames[0]
            assert kwargs["offload_video_to_cpu"] is True
            return {"num_frames": 1, "cached_features": marker, "video_width": 18, "video_height": 12}
    state = init_bounded_state(Predictor(), load_config(Path("configs/default.json")), frames)
    assert state["num_frames"] == 4 and state["cached_features"] is marker
    assert state["video_width"] == 18 and len(state["images"]) == 4


@pytest.mark.parametrize("requested,effective,sampled", [(15,15,True),(30,30,True),(120,60,False),(None,60,False)])
def test_preparation_preserves_source_and_processed_timebase(tmp_path, requested, effective, sampled):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"video")
    metadata = VideoMetadata(str(video), 16, 12, 60, 600, 10, "h264", 5)
    def extract(source, folder, **kwargs):
        assert kwargs.get("sample_fps") == (effective if sampled else None)
        assert kwargs.get("preserve_frames", False) is (not sampled)
        frames = [folder / f"{i:05d}.jpg" for i in range(int(effective * 10))]
        for p in frames:
            p.write_bytes(b"frame")
        return frames
    with patch("clickvos.video_io.probe_video", return_value=metadata), patch("clickvos.video_io.extract_frames", side_effect=extract):
        layout, original, frames = prepare_task(video, tmp_path / "tasks", max_frames=2000, sample_fps=requested, max_duration_seconds=30)
    record = json.loads(layout.metadata.read_text())
    assert original.fps == record["source_video"]["fps"] == 60
    assert record["video"]["fps"] == record["processing"]["fps"] == effective
    assert record["video"]["frame_count"] == len(frames)
    assert record["processing"]["mode"] == ("sampled" if sampled else "all_frames")


@pytest.mark.parametrize("duration,accepted", [(30,True),(30.001,False)])
def test_duration_limit_is_checked_before_extraction(tmp_path, duration, accepted):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"video")
    metadata = VideoMetadata(str(video), 16,12,60,1800,duration,"h264",5)
    with patch("clickvos.video_io.probe_video", return_value=metadata), patch("clickvos.video_io.extract_frames", return_value=[tmp_path / "fake.jpg"]) as extract:
        if accepted:
            prepare_task(video, tmp_path / "tasks", max_frames=2000, max_duration_seconds=30)
            assert extract.called
        else:
            with pytest.raises(VideoIOError, match="时长"):
                prepare_task(video, tmp_path / "tasks", max_frames=2000, max_duration_seconds=30)
            assert not extract.called and not (tmp_path / "tasks").exists()


@pytest.mark.parametrize("count,objects,memory,disk,accepted", [(1000,2,8,20,True),(1001,2,8,20,False),(600,2,2,20,False),(600,2,8,1,False)])
def test_resources_reject_before_model_load(count, objects, memory, disk, accepted):
    task = {"frames": ["frame"]*count,"width":960,"height":540,"task_root":"."}
    if accepted:
        check_run_resources(task,objects,available_bytes=memory*1024**3,free_disk=disk*1024**3)
    else:
        with pytest.raises(HTTPException):
            check_run_resources(task,objects,available_bytes=memory*1024**3,free_disk=disk*1024**3)


def test_export_keeps_sampled_timebase_without_private_source_path(tmp_path):
    (tmp_path / "task.json").write_text(json.dumps({
        "video": {"path": "/private/video.mp4", "fps": 15, "width": 16, "height": 12},
        "source_video": {"path": "/private/video.mp4", "fps": 60, "duration_seconds": 30, "frame_count": 1800},
        "processing": {"mode": "sampled", "fps": 15, "source_fps": 60, "requested_fps": 15},
    }))
    output = build_project_manifest(tmp_path, {"objects": [], "frame_count": 450}, tmp_path / "project.json")
    data = json.loads(output.read_text())
    assert data["video"]["fps"] == 15 and data["video"]["frame_count"] == 450
    assert data["source_video"]["fps"] == 60 and data["processing"]["mode"] == "sampled"
    assert "/private" not in output.read_text() and "path" not in data["source_video"]
