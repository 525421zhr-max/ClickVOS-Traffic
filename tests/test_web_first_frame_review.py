import copy
import json
from pathlib import Path
from types import SimpleNamespace

import gradio as gr
import pytest
from PIL import Image

from clickvos import web_app as web
from clickvos.first_frame_review import read_review_history


@pytest.fixture
def task(tmp_path):
    (tmp_path / "overlays").mkdir()
    overlay = tmp_path / "overlays" / "00000.jpg"
    Image.new("RGB", (30, 20), "white").save(overlay)
    objects = [{"object_id": 1, "category": "vehicle", "points": [
        {"x": 4, "y": 5, "positive": True},
    ]}]
    runtime = {
        "task_root": tmp_path,
        "session": object(),
        "objects": {1: copy.deepcopy(objects[0])},
        "keep_largest": False,
        "guard_reactivation": False,
    }
    web._ACTIVE_SESSIONS["review-test"] = runtime
    yield {"task_root": str(tmp_path)}, runtime, str(overlay), objects
    web._ACTIVE_SESSIONS.clear()


def test_add_preview_undo_persists_history_without_changing_applied_prompts(task, monkeypatch):
    state, runtime, overlay, original = task
    added = web._review_edit_for_web(
        state, "review-test", overlay, "负点", 1, original, [], SimpleNamespace(index=(18, 12)),
    )
    calls = []

    def preview(session, objects, root, keep_largest):
        calls.append(copy.deepcopy(objects))
        return {"preview_id": "preview-test", "overlay": overlay, "report": {}}

    monkeypatch.setattr(web, "preview_first_frame", preview)
    shown = web._preview_first_frame_for_web(state, "review-test", added[1], 1, False)
    assert "完整视频仍是上次传播结果" in shown[2]
    assert shown[-1] is None  # Clear any previously generated download.
    undone = web._review_undo_for_web(state, "review-test", shown[1], 1, added[1], added[3])
    assert undone[1] == original
    assert runtime["objects"][1]["points"] == original[0]["points"]
    assert calls[0][0]["points"][-1] == {"x": 18, "y": 12, "positive": False}
    history = read_review_history(Path(state["task_root"]))
    assert [event["action"] for event in history["events"]] == ["add", "preview", "undo"]
    assert history["events"][0]["objects"] == added[1]
    assert history["events"][-1]["objects"] == original


def test_pending_points_or_settings_block_export_until_applied(task, monkeypatch):
    state, runtime, overlay, objects = task
    calls = []
    monkeypatch.setattr(web, "_export_active_task", lambda key: calls.append(key) or ("bundle.zip", "导出完成"))
    updated = copy.deepcopy(objects)
    updated[0]["points"].append({"x": 10, "y": 10, "positive": False})
    with pytest.raises(gr.Error, match="尚未应用"):
        web._export_reviewed_task(state, "review-test", updated, False, False)
    with pytest.raises(gr.Error, match="尚未应用"):
        web._export_reviewed_task(state, "review-test", objects, True, False)
    assert not calls
    runtime["objects"][1]["points"] = copy.deepcopy(updated[0]["points"])
    assert web._export_reviewed_task(state, "review-test", updated, False, False)[0] == "bundle.zip"


def test_cross_task_or_stale_overlay_cannot_edit_or_preview(task, tmp_path):
    state, runtime, overlay, objects = task
    wrong = {"task_root": str(tmp_path / "other-task")}
    with pytest.raises(gr.Error, match="另一个任务"):
        web._preview_first_frame_for_web(wrong, "review-test", objects, 1, False)
    with pytest.raises(gr.Error, match="不属于当前任务"):
        web._review_edit_for_web(
            state, "review-test", str(tmp_path.parent / "old.jpg"), "负点", 1,
            objects, [], SimpleNamespace(index=(1, 1)),
        )
    assert not (tmp_path / "first_frame_review.json").exists()


def test_out_of_bounds_click_does_not_append_history(task):
    state, _, overlay, objects = task
    with pytest.raises(gr.Error, match="超出首帧范围"):
        web._review_edit_for_web(
            state, "review-test", overlay, "负点", 1, objects, [], SimpleNamespace(index=(30, 20)),
        )
    assert not (Path(state["task_root"]) / "first_frame_review.json").exists()


def test_rerun_records_applied_snapshot_and_retains_prior_actions(task, monkeypatch):
    state, _, overlay, objects = task
    added = web._review_edit_for_web(
        state, "review-test", overlay, "负点", 1, objects, [], SimpleNamespace(index=(18, 12)),
    )
    report = {"frame_count": 2, "postprocessing": "none", "objects": [{
        "object_id": 1, "category": "vehicle", "initial_points": added[1][0]["points"],
    }]}
    monkeypatch.setattr(web, "_run_multi_for_web", lambda *args: (
        "video.mp4", report, "完成", "review-test", {}, overlay, "检查首帧", overlay, {}, [],
    ))
    result = web._run_with_review_history(state)
    assert len(result) == 13
    assert result[9] == []
    history = result[10]
    assert [entry["action"] for entry in history["events"]] == ["add", "propagate"]
    assert history["events"][-1]["objects"] == added[1]


def test_prepare_reset_clears_old_result_and_editing_handles(task):
    values = web._reset_task_review()
    assert len(values) == 17
    assert values[:4] == (None, None, None, [])
    assert not web._ACTIVE_SESSIONS
    assert values[8:11] == (None, None, None)


def test_gradio_wires_preview_edits_and_gpu_actions_into_one_queue():
    demo = web.build_demo()
    preview_fn = next(fn for fn in demo.fns.values() if fn.fn is web._preview_first_frame_for_web)
    assert len(preview_fn.inputs) == 5 and len(preview_fn.outputs) == 6
    operations = {
        web._review_edit_for_web, web._review_undo_for_web, web._preview_first_frame_for_web,
        web._run_with_review_history, web._apply_correction_for_web, web._export_reviewed_task,
    }
    assert all(fn.concurrency_id == "task_operations" for fn in demo.fns.values() if fn.fn in operations)
    assert len(next(fn for fn in demo.fns.values() if fn.fn is web._review_edit_for_web).outputs) == 8
