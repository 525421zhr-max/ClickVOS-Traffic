"""Check the real FFmpeg overflow path using a longer, authorized local video."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from clickvos.errors import ErrorCode
from clickvos.video_io import VideoIOError, prepare_task


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--max-frames", type=int, default=3)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="clickvos-frame-limit-") as temp:
        tasks_root = Path(temp) / "tasks"
        try:
            prepare_task(args.video, tasks_root, "limit-smoke", max_frames=args.max_frames)
        except VideoIOError as exc:
            if exc.code != ErrorCode.VIDEO_TOO_MANY_FRAMES:
                raise
        else:
            raise RuntimeError("Expected video_too_many_frames, but video was accepted")
        record = json.loads((tasks_root / "limit-smoke" / "task.json").read_text(encoding="utf-8"))
        frame_count = len(list((tasks_root / "limit-smoke" / "frames").glob("*.jpg")))
        if record["status"] != "frame_extraction_failed" or frame_count != args.max_frames + 1:
            raise RuntimeError("Frame-limit smoke test produced an unexpected task state")
        print(json.dumps({
            "source_name": args.video.name,
            "max_frames": args.max_frames,
            "extracted_before_rejection": frame_count,
            "task_status": record["status"],
            "error_code": record["error"]["code"],
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
