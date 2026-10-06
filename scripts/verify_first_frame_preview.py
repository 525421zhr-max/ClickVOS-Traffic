"""Bounded real-GPU Web callback smoke: two frames, two runs, two previews."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import gradio as gr
import torch
from PIL import Image

from clickvos import web_app as web
from clickvos.first_frame_review import read_review_history
from clickvos.sam2_engine import file_sha256

if __package__ in (None, ""):
    from run_sam2_multi_frames import load_prompts
else:
    from scripts.run_sam2_multi_frames import load_prompts


def formal_files(root: Path) -> dict[str, str]:
    files = [root / "result.json"]
    for name in ("masks", "overlays", "exports"):
        files.extend(path for path in (root / name).rglob("*") if path.is_file())
    return {path.relative_to(root).as_posix(): file_sha256(path) for path in sorted(files)}


def session_points(session) -> dict:
    return {
        str(object_id): {
            str(frame): {key: value.detach().cpu().tolist() for key, value in points.items()}
            for frame, points in frames.items()
        }
        for object_id, frames in session.state["point_inputs_per_obj"].items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames-dir", type=Path, required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", default="configs/default.json")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"output already exists: {args.output}")
    _, prompts = load_prompts(Path("configs/experiments/davis-bmx-trees-two-objects.json"))
    source_frames = [args.frames_dir / f"{index:05d}.jpg" for index in range(2)]
    if args.frames_dir.name != "bmx-trees" or not all(path.is_file() for path in source_frames):
        raise SystemExit("expected the first two bmx-trees JPEG frames")
    objects = [{"object_id": prompt.object_id, "category": prompt.category,
                "points": [{"x": p.x, "y": p.y, "positive": p.positive} for p in prompt.points]}
               for prompt in prompts]
    root = args.output.resolve()
    (root / "frames").mkdir(parents=True)
    for frame in source_frames:
        shutil.copy2(frame, root / "frames" / frame.name)
    frames = sorted((root / "frames").glob("*.jpg"))
    with Image.open(frames[0]) as image:
        width, height = image.size
    (root / "task.json").write_text(json.dumps({
        "schema_version": 1, "task_id": root.name, "status": "frames_extracted",
        "created_at": datetime.now(UTC).isoformat(), "extracted_frame_count": 2,
        "video": {"path": "bmx-trees-two-frame-engineering-smoke", "width": width,
                  "height": height, "fps": 10.0, "frame_count": 2},
    }, indent=2), encoding="utf-8")
    state = {"task_root": str(root), "frames": [str(p) for p in frames], "fps": 10.0}
    torch.manual_seed(0)
    try:
        initial = web._run_with_review_history(state, objects, args.checkpoint, args.config, False, False)
        key = initial[3]
        runtime = web._ACTIVE_SESSIONS[key]
        session = runtime["session"]
        state_reference = session.state
        original_points = session_points(session)
        original_objects = copy.deepcopy(runtime["objects"])
        before = formal_files(root)
        added = web._review_edit_for_web(
            state, key, initial[7], "负点", 1, objects, [], SimpleNamespace(index=(533, 292)),
        )
        preview = web._preview_first_frame_for_web(state, key, added[1], 1, False)
        assert formal_files(root) == before, "preview altered formal results"
        assert web._ACTIVE_SESSIONS[key] is runtime and session.state is state_reference
        assert session_points(session) == original_points and runtime["objects"] == original_objects
        try:
            web._export_reviewed_task(state, key, added[1], False, False)
        except gr.Error as exc:
            assert "尚未应用" in str(exc)
        else:
            raise AssertionError("export allowed pending first-frame edits")
        undone = web._review_undo_for_web(state, key, preview[1], 1, added[1], added[3])
        assert undone[1] == objects
        restored = web._preview_first_frame_for_web(state, key, undone[1], 1, False)
        assert formal_files(root) == before and session_points(session) == original_points
        assert runtime["objects"] == original_objects
        final = web._run_with_review_history(state, undone[1], args.checkpoint, args.config, False, False)
        bundle, _ = web._export_reviewed_task(state, final[3], undone[1], False, False)
        history = read_review_history(root)
        actions = [event["action"] for event in history["events"]]
        assert actions == ["propagate", "add", "preview", "undo", "preview", "propagate"]
        with zipfile.ZipFile(bundle) as archive:
            names = archive.namelist()
            assert "first_frame_review.json" in names
            assert not any(name.startswith(("frames/", "first_frame_previews/")) for name in names)
            assert json.loads(archive.read("first_frame_review.json")) == history
        reports = [json.loads(path.read_text()) for path in (root / "first_frame_previews").glob("*/preview.json")]
        assert len(reports) == 2 and all(report["temporal_propagation_count"] == 0 for report in reports)
        summary = {
            "schema_version": 1, "status": "passed", "scope": "two_frame_web_callback_engineering_smoke",
            "frame_count": 2, "full_propagation_runs": 2, "single_frame_previews": 2,
            "added_clicks": 1, "undo_actions": 1, "journal_actions": actions,
            "formal_outputs_unchanged_during_previews": True,
            "active_session_and_prompts_unchanged_during_previews": True,
            "pending_export_rejected": True, "review_log_in_export": True,
            "source_frames_and_draft_masks_excluded_from_export": True,
            "final_saved_masks_per_object": [len(obj["mask_foreground_pixels"]) for obj in final[1]["objects"]],
            "seed": 0, "model": final[1]["model"], "torch": torch.__version__,
            "gpu": torch.cuda.get_device_name(0), "quality_metrics_reported": [],
            "negative_preview": str(Path(preview[1]).relative_to(root)),
            "undo_preview": str(Path(restored[1]).relative_to(root)),
            "export": str(Path(bundle).relative_to(root)),
        }
        (root / "preview-smoke-result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        web._ACTIVE_SESSIONS.clear()


if __name__ == "__main__":
    main()
