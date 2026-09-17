import json
import subprocess
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

from clickvos.errors import ClickVOSError
from clickvos.export import build_annotation_bundle, build_preview_video, encode_uncompressed_rle


def test_preview_export_uses_numbered_frames(tmp_path: Path) -> None:
    overlays = tmp_path / "overlays"
    overlays.mkdir()
    for index in range(2):
        (overlays / f"{index:05d}.jpg").write_bytes(b"jpeg")
    with patch("clickvos.export.subprocess.run", return_value=subprocess.CompletedProcess([], 0)) as run:
        output = build_preview_video(overlays, tmp_path / "preview.mp4", 10.0)
    assert output.name == "preview.mp4"
    assert any(str(argument).endswith("%05d.jpg") for argument in run.call_args.args[0])
    assert run.call_args.kwargs["check"] is True


def test_preview_export_rejects_frame_gap(tmp_path: Path) -> None:
    overlays = tmp_path / "overlays"
    overlays.mkdir()
    (overlays / "00001.jpg").write_bytes(b"jpeg")
    with pytest.raises(ClickVOSError, match="编号不连续"):
        build_preview_video(overlays, tmp_path / "preview.mp4", 10.0)


def _decode_rle(rle: dict[str, object]) -> np.ndarray:
    values = []
    current = 0
    for count in rle["counts"]:
        values.extend([current] * int(count))
        current = 1 - current
    height, width = rle["size"]
    return np.asarray(values, dtype=bool).reshape((int(height), int(width)), order="F")


def test_uncompressed_rle_round_trip() -> None:
    mask = np.asarray(
        [[False, True, True], [False, True, False], [True, False, False]], dtype=bool
    )
    encoded = encode_uncompressed_rle(mask)
    assert encoded["size"] == [3, 3]
    assert np.array_equal(_decode_rle(encoded), mask)


def test_annotation_bundle_contains_masks_and_json_but_not_source_frames(tmp_path: Path) -> None:
    task = tmp_path / "task-001"
    (task / "masks" / "object_001").mkdir(parents=True)
    (task / "masks" / "object_002").mkdir(parents=True)
    (task / "exports").mkdir()
    (task / "frames").mkdir()
    (task / "source").mkdir()
    (task / "frames" / "00000.jpg").write_bytes(b"private-frame")
    (task / "source" / "video.mp4").write_bytes(b"private-video")
    (task / "exports" / "preview.mp4").write_bytes(b"preview")
    (task / "task.json").write_text(
        json.dumps(
            {
                "video": {
                    "path": "/private/absolute/path/traffic.mp4",
                    "width": 4,
                    "height": 3,
                    "fps": 10.0,
                }
            }
        ),
        encoding="utf-8",
    )
    masks = {
        1: [
            np.asarray([[1, 1, 0, 0], [1, 0, 0, 0], [0, 0, 0, 0]], dtype=np.uint8),
            np.zeros((3, 4), dtype=np.uint8),
        ],
        2: [
            np.asarray([[0, 0, 0, 0], [0, 0, 1, 1], [0, 0, 1, 1]], dtype=np.uint8),
            np.asarray([[0, 1, 0, 0], [0, 1, 0, 0], [0, 0, 0, 0]], dtype=np.uint8),
        ],
    }
    objects = []
    for object_id, category in ((1, "vehicle"), (2, "pedestrian")):
        pixel_counts = {}
        for frame_index, mask in enumerate(masks[object_id]):
            name = f"{frame_index:05d}.png"
            Image.fromarray(mask * 255).save(task / "masks" / f"object_{object_id:03d}" / name)
            pixel_counts[name] = int(mask.sum())
        objects.append(
            {
                "object_id": object_id,
                "category": category,
                "initial_points": [{"x": 1, "y": 1, "positive": True}],
                "mask_foreground_pixels": pixel_counts,
                "guarded_frames": [],
                "anomalies": [],
            }
        )
    (task / "result.json").write_text(
        json.dumps(
            {
                "frame_count": 2,
                "objects": objects,
                "model": {"name": "test-model"},
                "postprocessing": "none",
                "reactivation_guard_enabled": False,
                "corrections": [],
            }
        ),
        encoding="utf-8",
    )

    bundle = build_annotation_bundle(task)
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        assert "project.json" in names
        assert "annotations/coco_rle.json" in names
        assert "preview.mp4" in names
        assert "masks/object_001/00000.png" in names
        assert not any(name.startswith("frames/") for name in names)
        assert not any(name.startswith("source/") for name in names)
        project = json.loads(archive.read("project.json"))
        coco = json.loads(archive.read("annotations/coco_rle.json"))
    assert project["video"]["file_name"] == "traffic.mp4"
    assert "/private/" not in json.dumps(project)
    assert len(coco["images"]) == 2
    assert len(coco["annotations"]) == 3
    assert coco["annotations"][0]["area"] == 3
    assert coco["annotations"][0]["bbox"] == [0, 0, 2, 2]
