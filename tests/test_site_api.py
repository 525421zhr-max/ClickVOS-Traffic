import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from clickvos.site_api import create_app


@pytest.fixture
def service(tmp_path, monkeypatch):
    config = json.loads(Path("configs/default.json").read_text())
    config["task"]["tasks_root"] = str(tmp_path / "tasks")
    config["video"]["max_upload_bytes"] = 32
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    static = tmp_path / "public"
    static.mkdir()
    (static / "index.html").write_text("public website")
    secret = tmp_path / "private.txt"
    secret.write_text("private video")

    def prepare(*args, **kwargs):
        root = tmp_path / "tasks" / "new-task"
        root.mkdir(exist_ok=True)
        frame = root / "00000.jpg"
        frame.write_bytes(b"frame")
        return SimpleNamespace(root=root), SimpleNamespace(width=10, height=10, fps=10, duration_seconds=.1), [frame]
    monkeypatch.setattr("clickvos.site_api.prepare_task", prepare)
    token = "t" * 32
    client = TestClient(create_app(config_path, tmp_path / "missing.pt", token, static, ("https://example.test",)))
    return client, {"Authorization": "Bearer " + token}, tmp_path


def upload_task(client, headers):
    response = client.post("/api/tasks", content=b"video", headers=headers)
    assert response.status_code == 200
    for _ in range(100):
        job = client.get("/api/jobs/" + response.json()["job_id"], headers=headers).json()
        if job["status"] != "running":
            assert job["status"] == "succeeded"
            return job["result"]["id"]
        time.sleep(.01)
    raise AssertionError("upload did not complete")


@pytest.mark.parametrize("path", ["/api/status", "/api/jobs/unknown", "/api/tasks/old", "/api/tasks/old/frame/0", "/api/tasks/old/bundle"])
def test_all_private_reads_require_access_code(service, path):
    client, _, _ = service
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401


@pytest.mark.parametrize("path", ["/api/tasks", "/api/tasks/old/run", "/api/tasks/old/review", "/api/tasks/old/correct", "/api/tasks/old/export"])
def test_all_mutations_require_access_code(service, path):
    client, _, _ = service
    assert client.post(path, json={}).status_code == 401


def test_static_mount_never_exposes_local_artifacts(service):
    client, _, _ = service
    assert client.get("/").text == "public website"
    for path in ("/docs", "/openapi.json", "/private.txt", "/outputs/tasks", "/%2e%2e/private.txt"):
        assert client.get(path).status_code == 404


def test_cors_only_allows_selected_site(service):
    client, headers, _ = service
    for origin, allowed in (("https://example.test", True), ("https://other.test", False)):
        r = client.options("/api/status", headers={"Origin": origin, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"})
        assert (r.headers.get("access-control-allow-origin") == origin) is allowed


def test_upload_bounds_and_empty_input_do_not_leave_files_or_lock(service):
    client, headers, root = service
    assert client.post("/api/tasks", content=b"x" * 33, headers=headers).status_code == 413
    assert client.post("/api/tasks", content=b"", headers=headers).status_code == 422
    assert list((root / "tasks").iterdir()) == []
    assert upload_task(client, headers) == "new-task"


def test_rejects_chunked_oversize_and_malformed_length(service):
    client, headers, root = service
    assert client.post("/api/tasks", content=iter([b"x" * 20, b"y" * 20]), headers=headers).status_code == 413
    assert client.post("/api/tasks", content=b"x", headers={**headers, "Content-Length": "bad"}).status_code == 422
    assert list((root / "tasks").iterdir()) == []


def test_task_scope_export_guard_and_coordinate_validation(service):
    client, headers, _ = service
    task = upload_task(client, headers)
    assert client.get("/api/tasks/previous-task", headers=headers).status_code == 404
    assert client.get(f"/api/tasks/{task}/frame/1", headers=headers).status_code == 404
    assert client.get(f"/api/tasks/{task}/bundle", headers=headers).status_code == 409
    assert client.post(f"/api/tasks/{task}/export", headers=headers).status_code == 409
    positive = {"x": 2, "y": 2, "positive": True}
    target = {"object_id": 1, "category": "vehicle", "points": [positive]}
    for objects in ([target, target], [{**target, "points": [{**positive, "x": 10}]}], [{**target, "points": [{**positive, "positive": False}]}]):
        assert client.post(f"/api/tasks/{task}/run", json={"objects": objects}, headers=headers).status_code == 422
    assert client.post(f"/api/tasks/{task}/correct", json={"object_id": 1, "frame_index": 0, "points": [positive]}, headers=headers).status_code == 422
    assert client.post(f"/api/tasks/{task}/review", json={"action": "preview", "object_id": 1}, headers=headers).status_code == 409


@pytest.mark.parametrize("operation", ["run", "correct"])
def test_failed_update_cannot_export_previous_or_partial_result(service, monkeypatch, operation):
    from clickvos import web_app
    from clickvos import site_api
    client, headers, _ = service
    original_prepare = site_api.prepare_task
    def two_frames(*args, **kwargs):
        layout, metadata, frames = original_prepare(*args, **kwargs)
        return layout, metadata, frames * 2
    monkeypatch.setattr(site_api, "prepare_task", two_frames)
    task = upload_task(client, headers)
    target = {"object_id": 1, "category": "vehicle", "points": [{"x": 2, "y": 2, "positive": True}]}
    report = {"objects": [{"object_id": 1, "category": "vehicle", "initial_points": target["points"]}]}
    monkeypatch.setattr(web_app, "_run_with_review_history", lambda *args: [None, report, None, "session", None, None, None, "overlay"])
    def wait_job(response):
        assert response.status_code == 200
        for _ in range(100):
            job = client.get("/api/jobs/" + response.json()["job_id"], headers=headers).json()
            if job["status"] != "running":
                return job
            time.sleep(.01)
        raise AssertionError("job timeout")
    assert wait_job(client.post(f"/api/tasks/{task}/run", json={"objects": [target]}, headers=headers))["status"] == "succeeded"
    assert client.get(f"/api/tasks/{task}", headers=headers).json()["has_result"]
    def fail(*args):
        raise RuntimeError("interrupted while writing masks")
    monkeypatch.setattr(web_app, "_run_with_review_history", fail)
    monkeypatch.setattr(web_app, "_apply_correction", fail)
    body = {"objects": [target]} if operation == "run" else {"object_id": 1, "frame_index": 1, "points": target["points"]}
    assert wait_job(client.post(f"/api/tasks/{task}/{operation}", json=body, headers=headers))["status"] == "failed"
    assert not client.get(f"/api/tasks/{task}", headers=headers).json()["has_result"]
    assert client.post(f"/api/tasks/{task}/export", headers=headers).status_code == 409
    assert client.get(f"/api/tasks/{task}/bundle", headers=headers).status_code == 409
