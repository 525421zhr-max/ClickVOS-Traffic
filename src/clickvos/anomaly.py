"""Baseline propagation anomaly signals derived from saved mask statistics."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence


@dataclass(frozen=True)
class Anomaly:
    kind: str
    frame_index: int
    severity: str
    message: str
    evidence: dict[str, int | float]


def detect_reactivation(
    pixel_counts: Mapping[str, int],
    minimum_empty_frames: int = 3,
) -> list[Anomaly]:
    if minimum_empty_frames < 1:
        raise ValueError("minimum_empty_frames must be at least 1")
    ordered = sorted((int(Path(name).stem), int(count)) for name, count in pixel_counts.items())
    anomalies: list[Anomaly] = []
    empty_started: int | None = None
    previously_visible = False
    for frame_index, count in ordered:
        if count > 0:
            if empty_started is not None and previously_visible:
                empty_frames = frame_index - empty_started
                if empty_frames >= minimum_empty_frames:
                    anomalies.append(
                        Anomaly(
                            kind="reactivation_after_disappearance",
                            frame_index=frame_index,
                            severity="high" if empty_frames >= 10 else "medium",
                            message="目标长时间消失后重新出现，请确认是否发生身份漂移。",
                            evidence={
                                "empty_start_frame": empty_started,
                                "empty_frame_count": empty_frames,
                                "reactivated_area_pixels": count,
                            },
                        )
                    )
            empty_started = None
            previously_visible = True
        elif previously_visible and empty_started is None:
            empty_started = frame_index
    return anomalies


def analyze_result_file(result_path: Path, minimum_empty_frames: int = 3) -> dict[str, object]:
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    anomalies = detect_reactivation(payload["mask_foreground_pixels"], minimum_empty_frames)
    return {
        "source_result": str(result_path),
        "rule": "reactivation_after_disappearance",
        "minimum_empty_frames": minimum_empty_frames,
        "anomaly_count": len(anomalies),
        "anomalies": [asdict(item) for item in anomalies],
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Detect suspicious SAM2 mask reactivation")
    parser.add_argument("result", type=Path)
    parser.add_argument("--minimum-empty-frames", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = analyze_result_file(args.result, args.minimum_empty_frames)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
