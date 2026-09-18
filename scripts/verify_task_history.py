"""Verify read-only task history and re-export against local task artifacts."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

from clickvos.config import load_config
from clickvos.export import build_annotation_bundle
from clickvos.task_store import list_tasks, load_task


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/default.json"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    config = load_config(args.config)
    tasks, skipped = list_tasks(config.tasks_root)
    selected = next((summary for summary in tasks if summary.has_result), None)
    if selected is None:
        raise RuntimeError("no completed local task available for history verification")
    task = load_task(config.tasks_root, selected.task_id)
    bundle = build_annotation_bundle(task.root)
    with zipfile.ZipFile(bundle) as archive:
        entries = archive.namelist()
    summary = {
        "listed_task_count": len(tasks),
        "skipped_directory_count": skipped,
        "selected_task": selected.as_dict(),
        "preview_exists": task.preview is not None,
        "bundle_name": bundle.name,
        "bundle_bytes": bundle.stat().st_size,
        "bundle_entry_count": len(entries),
        "source_video_in_bundle": any(name.startswith("source/") for name in entries),
        "extracted_frames_in_bundle": any(name.startswith("frames/") for name in entries),
        "mode": "read_only",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
