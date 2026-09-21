"""Run dependency-free repository integrity checks before backup or in CI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "docs" / "research" / "results"
FORBIDDEN_TRACKED_SUFFIXES = {".pt", ".pth", ".ckpt", ".mp4", ".mov", ".avi", ".webm", ".mkv"}
REQUIRED_CATEGORIES = {"vehicle", "pedestrian", "non_motorized"}


def fail(message: str) -> None:
    raise RuntimeError(message)


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"无法读取有效 JSON：{path.relative_to(ROOT)} ({exc})")
    if not isinstance(data, dict):
        fail(f"JSON 顶层必须是对象：{path.relative_to(ROOT)}")
    return data


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [Path(item.decode("utf-8")) for item in result.stdout.split(b"\0") if item]


def main() -> int:
    config = load_json(ROOT / "configs" / "default.json")
    if config.get("schema_version") != 1:
        fail("configs/default.json 的 schema_version 必须为 1")
    categories = {item.get("key") for item in config.get("categories", [])}
    if categories != REQUIRED_CATEGORIES:
        fail(f"目标类别不完整：{sorted(str(item) for item in categories)}")

    result_files = sorted(RESULTS_DIR.glob("*.json"))
    if not result_files:
        fail("docs/research/results 中没有实验摘要")
    for path in result_files:
        record = load_json(path)
        if record.get("schema_version") != 1:
            fail(f"实验摘要 schema_version 错误：{path.relative_to(ROOT)}")
        if not record.get("source_checkpoint"):
            fail(f"实验摘要缺少 source_checkpoint：{path.relative_to(ROOT)}")
        ground_truth = record.get("ground_truth_available")
        metrics = record.get("quality_metrics_reported")
        if not isinstance(ground_truth, bool):
            fail(f"实验摘要必须明确 ground_truth_available：{path.relative_to(ROOT)}")
        if not isinstance(metrics, list):
            fail(f"实验摘要缺少 quality_metrics_reported 数组：{path.relative_to(ROOT)}")
        if ground_truth and not metrics:
            fail(f"有真值的实验摘要必须列出质量指标：{path.relative_to(ROOT)}")
        if not ground_truth and metrics:
            fail(f"无真值的实验摘要不得报告质量指标：{path.relative_to(ROOT)}")

    required_docs = [
        ROOT / "README.md",
        ROOT / "docs" / "operations" / "github-backup.md",
        ROOT / "docs" / "research" / "data-sources.md",
    ]
    for path in required_docs:
        if not path.is_file():
            fail(f"缺少必需文档：{path.relative_to(ROOT)}")

    tracked = tracked_files()
    forbidden = [str(path) for path in tracked if path.suffix.lower() in FORBIDDEN_TRACKED_SUFFIXES]
    if forbidden:
        fail("Git 索引中存在禁止上传的模型或视频：" + ", ".join(forbidden))

    print(
        f"repository checks passed: {len(result_files)} result summaries, "
        f"{len(tracked)} tracked files, no tracked model/video artifacts"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"repository checks failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
