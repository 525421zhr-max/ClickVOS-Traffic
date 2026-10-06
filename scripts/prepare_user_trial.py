"""Prepare licensed local trial clips and ten empty records; never run inference."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"output exists; refusing to overwrite: {output}")
    if not output.is_relative_to((ROOT / "outputs/tasks").resolve()):
        raise SystemExit("trial assets and feedback must stay under ignored outputs/tasks")
    car = ROOT / "data/raw/davis2017/trainval-road-cars/DAVIS/JPEGImages/480p/car-roundabout"
    people = ROOT / "data/processed/traffic-002/sample.mp4"
    riders = ROOT / "outputs/tasks/dev32-browser-e2e-001/traffic-004.mp4"
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"missing tool: {tool}")
    if sorted(p.name for p in car.glob("*.jpg")) != [f"{i:05d}.jpg" for i in range(75)]:
        raise SystemExit("expected complete local 75-frame car-roundabout sequence")
    for source, expected in ((people, "461c2fed7d2913100c19d68fe2ec6a958c44498194ed863533eaeada12b7169f"),
                             (riders, "57916fe7b6968ac71e1da7cc5bb24b6409975b942b638d41b14edcc35d6be5b6")):
        if not source.is_file() or sha256(source) != expected:
            raise SystemExit(f"registered input missing or changed: {source}")
    template = json.loads((ROOT / "docs/trials/record-template.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-framerate", "10",
                    "-i", str(car / "%05d.jpg"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(output / "T1-car.mp4")], check=True, timeout=60)
    shutil.copyfile(people, output / "T2-pedestrians.mp4")
    shutil.copyfile(riders, output / "T3-riders.mp4")
    assets = []
    for name, size, count, source_id, license_name, url, limit in (
        ("T1-car.mp4", [854, 480], 75, "davis-002-car-roundabout", "CC BY-NC 4.0; source terms also apply", "https://davischallenge.org/davis2017/code.html", 480),
        ("T2-pedestrians.mp4", [960, 540], 50, "traffic-002", "CC BY-SA 3.0 / Amada44", "https://commons.wikimedia.org/wiki/File:People_waiting_to_cross_the_street.webm", 600),
        ("T3-riders.mp4", [960, 540], 30, "traffic-004", "CC BY 3.0 / idioterna", "https://commons.wikimedia.org/wiki/File:Bloody_Cyclists.webm", 720),
    ):
        path = output / name
        probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,nb_frames,r_frame_rate", "-of", "json", str(path)], timeout=20))
        stream = probe["streams"][0]
        if [stream["width"], stream["height"]] != size or int(stream["nb_frames"]) != count or stream["r_frame_rate"] != "10/1":
            raise RuntimeError(f"unexpected clip specification: {name}")
        assets.append({"file": name, "sha256": sha256(path), "bytes": path.stat().st_size,
                       "width_height": size, "frame_count": count, "playback_fps": 10,
                       "source_id": source_id, "license_attribution": license_name, "source_url": url,
                       "time_limit_seconds": limit})
    (output / "records").mkdir()
    (output / "configs").mkdir()
    default_config = json.loads((ROOT / "configs/default.json").read_text(encoding="utf-8"))
    for index in range(1, 11):
        record = copy.deepcopy(template)
        record["participant_id"] = f"P{index:02d}"
        (output / "records" / f"P{index:02d}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        participant_config = copy.deepcopy(default_config)
        participant_config["task"]["tasks_root"] = (output / "sessions" / f"P{index:02d}" / "tasks").relative_to(ROOT).as_posix()
        (output / "configs" / f"P{index:02d}.json").write_text(json.dumps(participant_config, indent=2), encoding="utf-8")
    shutil.copyfile(ROOT / "docs/trials/README.md", output / "trial-instructions.md")
    receipt = {"schema_version": 1, "protocol_version": "clickvos-user-trial-v1",
               "status": "materials_prepared_no_participants", "real_participants": 0,
               "blank_record_count": 10, "gpu_runs": 0, "assets": assets}
    (output / "assets.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
