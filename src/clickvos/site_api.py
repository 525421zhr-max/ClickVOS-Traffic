"""Authenticated, single-operator HTTP bridge for the unified Sites workbench."""
from __future__ import annotations

import json
import logging
import os
import secrets
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict

from clickvos.config import load_config
from clickvos.video_io import prepare_task

OBJECT_FRAME_BUDGET = 2000


def check_run_resources(task: dict, object_count: int, *, available_bytes: int | None = None, free_disk: int | None = None):
    """Conservative admission estimate; cached SAM2 history still grows with objects."""
    import shutil
    frames = len(task["frames"])
    if frames * object_count > OBJECT_FRAME_BUDGET:
        raise HTTPException(422, f"当前有 {frames} 帧、{object_count} 个目标，超过本机资源预算。请减少目标，或上传时选择 30/15 FPS。")
    if available_bytes is None:
        memory = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
        available_bytes = int(memory["MemAvailable"].split()[0]) * 1024
    # Reserve 1.5 GiB plus source-resolution intermediates; allowance per object/frame
    # is deliberately larger than the pinned tiny model's low-resolution history.
    reserve = 1536 * 1024**2 + task["width"] * task["height"] * (48 + object_count * 16)
    estimate = frames * object_count * 2 * 1024**2 + 128 * 1024**2
    if estimate + reserve > available_bytes:
        raise HTTPException(503, "当前可用内存不足以安全运行这段视频。请减少目标、降低处理帧率或关闭占内存的软件后重试。")
    free_disk = shutil.disk_usage(task["task_root"]).free if free_disk is None else free_disk
    required_disk = frames * task["width"] * task["height"] * (object_count + 3) + 1024**3
    if required_disk > free_disk:
        raise HTTPException(503, "本机磁盘剩余空间不足，请释放空间或缩短视频后重试。")


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    positive: bool


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    object_id: int = Field(gt=0)
    category: Literal["vehicle", "pedestrian", "non_motorized"]
    points: list[Point] = Field(min_length=1, max_length=128)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    objects: list[Target] = Field(min_length=1, max_length=20)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Literal["add", "undo", "preview"]
    object_id: int = Field(gt=0)
    point: Point | None = None


class CorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    object_id: int = Field(gt=0)
    frame_index: int = Field(gt=0)
    points: list[Point] = Field(min_length=1, max_length=128)


def create_app(config_path: Path, checkpoint: Path, token: str, static_dir: Path | None = None,
               origins: tuple[str, ...] = ()) -> FastAPI:
    if len(token) < 32:
        raise ValueError("Use an access token with at least 32 characters.")
    config = load_config(config_path)
    config.tasks_root.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="ClickVOS Workbench", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=list(origins), allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type"], allow_credentials=False)
    tasks: dict[str, dict] = {}
    jobs: dict[str, dict] = {}
    operation = threading.Lock()
    max_bytes = min(config.video.max_upload_bytes, 100 * 1024 * 1024)
    size_message = f"视频超过 {max_bytes / 1024**2:g} MiB，请降低码率或裁剪后重新上传。"

    def authorize(request: Request) -> None:
        supplied = request.headers.get("authorization", "")
        if not secrets.compare_digest(supplied, "Bearer " + token):
            raise HTTPException(401, "访问码无效或已过期，请重新连接推理服务。")

    auth = [Depends(authorize)]

    def task_for(task_id: str) -> dict:
        if task_id not in tasks:
            raise HTTPException(404, "任务不存在，服务重启后请重新上传视频。")
        return tasks[task_id]

    def check_points(points: list[dict], task: dict) -> None:
        if any(p["x"] >= task["width"] or p["y"] >= task["height"] for p in points):
            raise HTTPException(422, "提示点超出画面范围。")

    def require_idle() -> None:
        if not operation.acquire(blocking=False):
            raise HTTPException(409, "推理服务正在处理任务，请等待当前操作完成。")

    def submit(work, *, acquired: bool = False) -> dict:
        if not acquired:
            require_idle()
        if len(jobs) >= 128:
            for old_id in list(jobs):
                if jobs[old_id]["status"] != "running":
                    del jobs[old_id]
                    break
        job_id = secrets.token_hex(12)
        job = {"id": job_id, "status": "running"}
        jobs[job_id] = job

        def execute():
            try:
                job["result"] = work()
                job["status"] = "succeeded"
            except Exception as exc:
                logging.exception("Workbench job failed")
                message = getattr(exc, "user_message", None)
                if isinstance(exc, HTTPException):
                    message = exc.detail
                if message is None and type(exc).__module__.startswith("gradio"):
                    message = str(exc)
                job["error"] = message or "操作失败，请检查视频或服务日志后重试。"
                job["status"] = "failed"
            finally:
                operation.release()
        threading.Thread(target=execute, daemon=True).start()
        return {"job_id": job_id}

    def summary(task: dict) -> dict:
        report = task.get("report") or {}
        applied = [{"object_id": x["object_id"], "category": x["category"],
                    "points": x["initial_points"]} for x in report.get("objects", [])]
        return {"id": task["id"], "width": task["width"], "height": task["height"],
                "frame_count": len(task["frames"]), "fps": task["fps"],
                "source_fps": task.get("source_fps", task["fps"]),
                "duration_seconds": task.get("duration_seconds"),
                "sampling": task.get("sampling", False),
                "objects": task["objects"], "has_result": bool(report),
                "has_draft": bool(task.get("draft")),
                "undo_available": bool(task.get("added_points")),
                "pending": bool(report) and task["objects"] != applied,
                "anomaly_count": report.get("anomaly_count", 0),
                "anomalies": report.get("anomalies", []),
                "correction_count": len(report.get("corrections", []))}

    @app.get("/api/status", dependencies=auth)
    def status():
        import torch
        return {"ready": checkpoint.is_file() and torch.cuda.is_available(),
                "busy": operation.locked(), "max_bytes": max_bytes,
                "max_frames": config.video.max_frames, "max_duration_seconds": config.video.max_duration_seconds,
                "object_frame_budget": OBJECT_FRAME_BUDGET, "mode": "single_operator"}

    @app.get("/api/jobs/{job_id}", dependencies=auth)
    def job_status(job_id: str):
        if job_id not in jobs:
            raise HTTPException(404, "运行记录已失效，请重新连接服务。")
        return dict(jobs[job_id])

    @app.post("/api/tasks", dependencies=auth)
    async def upload(request: Request, fps: Literal["preserve", "30", "15"] = "preserve"):
        if len(tasks) >= 32:
            raise HTTPException(503, "本次服务会话的任务数量已达上限，请联系服务提供者。")
        length = request.headers.get("content-length")
        if length:
            try:
                size = int(length)
                if size < 0:
                    raise ValueError
            except ValueError:
                raise HTTPException(422, "视频大小字段无效。") from None
            if size > max_bytes:
                raise HTTPException(413, size_message)
        require_idle()
        handoff = False
        incoming = config.tasks_root / ("upload-" + secrets.token_hex(12) + ".mp4")
        try:
            count = 0
            with incoming.open("xb") as stream:
                async for chunk in request.stream():
                    count += len(chunk)
                    if count > max_bytes:
                        raise HTTPException(413, size_message)
                    stream.write(chunk)
            if count == 0:
                raise HTTPException(422, "视频为空，请重新选择文件。")

            def prepare():
                layout, metadata, frames = prepare_task(incoming, config.tasks_root,
                    max_bytes=max_bytes, max_frames=config.video.max_frames,
                    quality=config.video.jpeg_quality, sample_fps=None if fps == "preserve" else float(fps),
                    max_duration_seconds=config.video.max_duration_seconds, max_pixels=4096 * 2160)
                processing_fps = metadata.fps if fps == "preserve" else min(metadata.fps, float(fps))
                task = {"id": layout.root.name, "task_root": str(layout.root),
                        "frames": [str(x) for x in frames], "width": metadata.width,
                        "height": metadata.height, "fps": processing_fps, "source_fps": metadata.fps,
                        "duration_seconds": metadata.duration_seconds, "sampling": processing_fps < metadata.fps,
                        "objects": [],
                        "added_points": [], "session_key": None}
                tasks[task["id"]] = task
                return summary(task)
            result = submit(prepare, acquired=True)
            handoff = True
            return result
        finally:
            if not handoff:
                operation.release()
                incoming.unlink(missing_ok=True)

    @app.get("/api/tasks/{task_id}", dependencies=auth)
    def task_summary(task_id: str):
        return summary(task_for(task_id))

    @app.post("/api/tasks/{task_id}/run", dependencies=auth)
    def run(task_id: str, body: RunRequest):
        task = task_for(task_id)
        objects = [x.model_dump() for x in body.objects]
        ids = [x["object_id"] for x in objects]
        if len(ids) != len(set(ids)) or any(not any(p["positive"] for p in x["points"]) for x in objects):
            raise HTTPException(422, "目标编号不能重复，每个目标至少需要一个正点。")
        for target in objects:
            check_points(target["points"], task)
        check_run_resources(task, len(objects))

        def propagate():
            from clickvos import web_app as web
            task.update(report=None, bundle=None, draft=None, session_key=None)
            outputs = web._run_with_review_history(task, objects, str(checkpoint), str(config_path), True, True)
            task.update(objects=objects, report=outputs[1], session_key=outputs[3],
                        first_overlay=outputs[7], added_points=[], draft=None, bundle=None)
            return summary(task)
        return submit(propagate)

    @app.post("/api/tasks/{task_id}/review", dependencies=auth)
    def review(task_id: str, body: ReviewRequest):
        task = task_for(task_id)
        if not task.get("report"):
            raise HTTPException(409, "请先运行传播，再复核首帧。")
        if body.object_id not in [x["object_id"] for x in task["objects"]]:
            raise HTTPException(422, "请选择当前任务中的目标。")
        if body.action == "add":
            if body.point is None:
                raise HTTPException(422, "缺少补点位置。")
            check_points([body.point.model_dump()], task)
            target = next(x for x in task["objects"] if x["object_id"] == body.object_id)
            if len(target["points"]) >= 128:
                raise HTTPException(422, "每个目标最多 128 个提示点。")
        if body.action == "undo" and not task["added_points"]:
            raise HTTPException(409, "没有可撤销的首帧补点。")

        def edit():
            from clickvos import web_app as web
            task["bundle"] = None
            args = (task, task["session_key"])
            if body.action == "preview":
                outputs = web._preview_first_frame_for_web(*args, task["objects"], body.object_id, True)
                task["draft"] = outputs[1]
            elif body.action == "add":
                point = body.point
                outputs = web._review_edit_for_web(*args, task["first_overlay"],
                    "正点" if point.positive else "负点", body.object_id, task["objects"],
                    task["added_points"], SimpleNamespace(index=(point.x, point.y)))
                task["objects"], task["added_points"] = outputs[1], outputs[3]
                task["draft"] = None
            else:
                if not task["added_points"]:
                    raise HTTPException(409, "没有可撤销的首帧补点。")
                outputs = web._review_undo_for_web(*args, task["first_overlay"], body.object_id,
                                                  task["objects"], task["added_points"])
                task["objects"], task["added_points"] = outputs[1], outputs[3]
                task["draft"] = None
            task["bundle"] = None
            return summary(task)
        return submit(edit)

    @app.post("/api/tasks/{task_id}/correct", dependencies=auth)
    def correct(task_id: str, body: CorrectionRequest):
        task = task_for(task_id)
        if not task.get("report") or summary(task)["pending"]:
            raise HTTPException(409, "请先将首帧提示传播到整段视频，再修正中间帧。")
        if body.object_id not in [x["object_id"] for x in task["objects"]] or body.frame_index >= len(task["frames"]):
            raise HTTPException(422, "目标或帧号超出当前任务范围。")
        points = [x.model_dump() for x in body.points]
        check_points(points, task)

        def apply():
            from clickvos import web_app as web
            task.update(bundle=None, draft=None, report=None)
            outputs = web._apply_correction(task["session_key"], body.frame_index, points, body.object_id)
            task.update(report=outputs[1], bundle=None, draft=None)
            return summary(task)
        return submit(apply)

    @app.post("/api/tasks/{task_id}/export", dependencies=auth)
    def export(task_id: str):
        task = task_for(task_id)
        if not task.get("report") or summary(task)["pending"]:
            raise HTTPException(409, "当前提示还未传播到整段视频，请先运行传播再导出。")

        def bundle():
            from clickvos import web_app as web
            task["bundle"] = None
            output, _ = web._export_reviewed_task(task, task["session_key"], task["objects"], True, True)
            task["bundle"] = output
            return {"download": f"/api/tasks/{task_id}/bundle"}
        return submit(bundle)

    @app.get("/api/tasks/{task_id}/frame/{index}", dependencies=auth)
    def frame(task_id: str, index: int, overlay: bool = False, draft: bool = False):
        task = task_for(task_id)
        if not 0 <= index < len(task["frames"]):
            raise HTTPException(404, "帧号超出范围。")
        path = Path(task["frames"][index])
        if overlay:
            path = Path(task["task_root"]) / "overlays" / f"{index:05d}.jpg"
        if draft:
            if index != 0 or not task.get("draft"):
                raise HTTPException(404, "请先更新首帧预览。")
            path = Path(task["draft"])
        if not path.is_file():
            raise HTTPException(404, "该帧的结果尚未生成。")
        return FileResponse(path, headers={"Cache-Control": "no-store"})

    @app.get("/api/tasks/{task_id}/bundle", dependencies=auth)
    def download(task_id: str):
        if operation.locked():
            raise HTTPException(409, "正在更新任务，请等待操作完成后下载。")
        task = task_for(task_id)
        if not task.get("bundle") or summary(task)["pending"]:
            raise HTTPException(409, "请重新生成当前任务的标注包。")
        return FileResponse(task["bundle"], filename="ClickVOS-" + task_id + ".zip",
                            headers={"Cache-Control": "no-store"})

    if static_dir:
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="website")
    return app


def main():
    import uvicorn
    settings = json.loads(Path(os.environ["CLICKVOS_SITE_SETTINGS"]).read_text(encoding="utf-8"))
    app = create_app(Path(settings["config"]), Path(settings["checkpoint"]), settings["token"],
                     Path(settings["static_dir"]), tuple(settings["origins"]))
    uvicorn.run(app, host="127.0.0.1", port=settings.get("port", 7880))


if __name__ == "__main__":
    main()
