"""Export ClickVOS frame sequences to user-facing artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image

from clickvos.errors import ClickVOSError, ErrorCode


CATEGORY_IDS = {"vehicle": 1, "pedestrian": 2, "non_motorized": 3}
CATEGORY_NAMES_ZH = {"vehicle": "车辆", "pedestrian": "行人", "non_motorized": "非机动车"}
DEFAULT_OBJECT_COLORS = (
    (0, 210, 255),
    (255, 92, 92),
    (143, 255, 92),
    (195, 110, 255),
    (255, 190, 70),
    (70, 150, 255),
)


def build_preview_video(overlays_dir: Path, output: Path, fps: float) -> Path:
    if fps <= 0:
        raise ValueError("fps must be positive")
    frames = sorted(overlays_dir.glob("*.jpg"))
    if not frames:
        raise ClickVOSError(ErrorCode.FRAME_EXTRACTION_FAILED, "没有可导出的叠加帧。", str(overlays_dir))
    expected = [f"{index:05d}.jpg" for index in range(len(frames))]
    actual = [frame.name for frame in frames]
    if actual != expected:
        raise ClickVOSError(ErrorCode.FRAME_EXTRACTION_FAILED, "叠加帧编号不连续，无法导出视频。")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error", "-framerate", str(fps),
                "-i", str(overlays_dir / "%05d.jpg"), "-c:v", "libx264",
                "-pix_fmt", "yuv420p", str(output),
            ],
            check=True,
        )
    except FileNotFoundError as exc:
        raise ClickVOSError(ErrorCode.DEPENDENCY_MISSING, "缺少 FFmpeg，无法导出预览视频。") from exc
    except subprocess.CalledProcessError as exc:
        raise ClickVOSError(ErrorCode.FRAME_EXTRACTION_FAILED, "预览视频导出失败。", str(exc)) from exc
    return output


def encode_uncompressed_rle(mask: np.ndarray) -> dict[str, object]:
    """Encode a 2D binary mask as COCO's JSON-safe uncompressed RLE."""
    values = np.asarray(mask, dtype=np.uint8)
    if values.ndim != 2:
        raise ValueError(f"mask must be 2D, got {values.shape}")
    flat = values.ravel(order="F")
    counts: list[int] = []
    previous = 0
    run_length = 0
    for value in flat:
        current = int(value > 0)
        if current != previous:
            counts.append(run_length)
            run_length = 1
            previous = current
        else:
            run_length += 1
    counts.append(run_length)
    return {"size": [int(values.shape[0]), int(values.shape[1])], "counts": counts}


def _bbox(mask: np.ndarray) -> list[int]:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return [0, 0, 0, 0]
    x_min, x_max = int(xs.min()), int(xs.max())
    y_min, y_max = int(ys.min()), int(ys.max())
    return [x_min, y_min, x_max - x_min + 1, y_max - y_min + 1]


def _safe_relative_directory(task_root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe task-relative path: {relative}")
    resolved = (task_root / path).resolve()
    if task_root.resolve() not in resolved.parents:
        raise ValueError(f"path escapes task root: {relative}")
    return resolved


def _mask_directory(item: dict[str, Any]) -> str:
    object_id = int(item["object_id"])
    return str(item.get("mask_directory") or f"masks/object_{object_id:03d}")


def build_coco_rle(task_root: Path, result: dict[str, Any], output: Path) -> Path:
    objects = result.get("objects")
    frame_count = int(result.get("frame_count", 0))
    if not isinstance(objects, list) or not objects or frame_count <= 0:
        raise ValueError("result.json does not contain a valid multi-object result")

    images: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    annotation_id = 1
    dimensions: tuple[int, int] | None = None
    for frame_index in range(frame_count):
        frame_name = f"{frame_index:05d}.png"
        image_id = frame_index + 1
        for item in objects:
            category = str(item["category"])
            if category not in CATEGORY_IDS:
                raise ValueError(f"unsupported category in result: {category}")
            mask_dir = _safe_relative_directory(task_root, _mask_directory(item))
            mask_path = mask_dir / frame_name
            if not mask_path.is_file():
                raise FileNotFoundError(f"missing object mask: {mask_path}")
            mask = np.asarray(Image.open(mask_path).convert("L")) > 0
            height, width = mask.shape
            if dimensions is None:
                dimensions = (width, height)
            elif dimensions != (width, height):
                raise ValueError("mask dimensions are inconsistent")
            area = int(mask.sum())
            if area == 0:
                continue
            annotations.append(
                {
                    "id": annotation_id,
                    "image_id": image_id,
                    "category_id": CATEGORY_IDS[category],
                    "segmentation": encode_uncompressed_rle(mask),
                    "area": area,
                    "bbox": _bbox(mask),
                    "iscrowd": 0,
                    "object_id": int(item["object_id"]),
                }
            )
            annotation_id += 1
        if dimensions is None:
            raise ValueError("could not determine mask dimensions")
        images.append(
            {
                "id": image_id,
                "file_name": f"frames/{frame_index:05d}.jpg",
                "width": dimensions[0],
                "height": dimensions[1],
                "frame_index": frame_index,
            }
        )

    payload = {
        "info": {
            "description": "ClickVOS Traffic multi-object video segmentation export",
            "schema_version": 1,
            "task_id": task_root.name,
            "images_included_in_bundle": False,
        },
        "images": images,
        "annotations": annotations,
        "categories": [
            {"id": category_id, "name": key, "name_zh": CATEGORY_NAMES_ZH[key]}
            for key, category_id in CATEGORY_IDS.items()
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def build_project_manifest(task_root: Path, result: dict[str, Any], output: Path) -> Path:
    task_metadata_path = task_root / "task.json"
    task_metadata = json.loads(task_metadata_path.read_text(encoding="utf-8"))
    video = task_metadata.get("video", {})
    objects = []
    for item in result["objects"]:
        object_id = int(item["object_id"])
        objects.append(
            {
                "object_id": object_id,
                "category": item["category"],
                "color_rgb": item.get(
                    "color_rgb",
                    list(DEFAULT_OBJECT_COLORS[(object_id - 1) % len(DEFAULT_OBJECT_COLORS)]),
                ),
                "initial_points": item["initial_points"],
                "mask_directory": f"masks/object_{object_id:03d}",
                "mask_foreground_pixels": item["mask_foreground_pixels"],
                "guarded_frames": item["guarded_frames"],
                "anomalies": item["anomalies"],
            }
        )
    payload = {
        "schema_version": 1,
        "format": "clickvos_traffic_project",
        "task_id": task_root.name,
        "video": {
            "file_name": Path(str(video.get("path", "video"))).name,
            "width": video.get("width"),
            "height": video.get("height"),
            "fps": video.get("fps"),
            "frame_count": result["frame_count"],
        },
        "model": result.get("model"),
        "postprocessing": result.get("postprocessing"),
        "reactivation_guard_enabled": result.get("reactivation_guard_enabled"),
        "objects": objects,
        "corrections": result.get("corrections", []),
        "confirmed_reactivations": result.get("confirmed_reactivations", []),
        "overlap_events": result.get("overlap_events", []),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def build_annotation_bundle(task_root: Path) -> Path:
    task_root = task_root.expanduser().resolve()
    result_path = task_root / "result.json"
    if not result_path.is_file():
        raise FileNotFoundError(f"missing task result: {result_path}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    exports = task_root / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    project = build_project_manifest(task_root, result, exports / "project.json")
    coco = build_coco_rle(task_root, result, exports / "coco_rle.json")
    bundle = exports / f"clickvos-{task_root.name}.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(project, "project.json")
        archive.write(coco, "annotations/coco_rle.json")
        preview = exports / "preview.mp4"
        if preview.is_file():
            archive.write(preview, "preview.mp4")
        for item in result["objects"]:
            object_id = int(item["object_id"])
            mask_dir = _safe_relative_directory(task_root, _mask_directory(item))
            for mask in sorted(mask_dir.glob("*.png")):
                archive.write(mask, f"masks/object_{object_id:03d}/{mask.name}")
    return bundle


def main(argv: Sequence[str] | None = None) -> None:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "bundle":
        bundle_parser = argparse.ArgumentParser(description="Build a ClickVOS annotation ZIP")
        bundle_parser.add_argument("command", choices=["bundle"])
        bundle_parser.add_argument("task", type=Path)
        bundle_args = bundle_parser.parse_args(arguments)
        print(build_annotation_bundle(bundle_args.task))
        return
    parser = argparse.ArgumentParser(description="Export overlay JPEG frames as an MP4 preview")
    parser.add_argument("overlays", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fps", type=float, required=True)
    args = parser.parse_args(arguments)
    print(build_preview_video(args.overlays, args.output, args.fps))


if __name__ == "__main__":
    main()
