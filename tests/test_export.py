import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from clickvos.errors import ClickVOSError
from clickvos.export import build_preview_video


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
