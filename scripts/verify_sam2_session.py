"""Verify multi-object prompts and a later correction against the CP-02 sample."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from clickvos.config import load_config
from clickvos.sam2_engine import ObjectPrompt, PromptPoint, Sam2Engine


def mask_counts(prediction: object) -> dict[str, int]:
    return {
        str(object_id): int(mask.sum())
        for object_id, mask in zip(prediction.object_ids, prediction.masks, strict=True)
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    frames = sorted(args.frames.glob("*.jpg"))
    config = load_config(Path("configs/default.json"))
    engine, load_seconds = Sam2Engine.load(config, args.checkpoint)
    session = engine.start_session(frames)
    first = session.add_prompt(ObjectPrompt(1, "vehicle", 0, (PromptPoint(520, 370),)))
    second = session.add_prompt(ObjectPrompt(2, "vehicle", 0, (PromptPoint(700, 440),)))
    initial_predictions = list(session.propagate(start_frame_idx=0, max_frame_num_to_track=5))
    correction = session.add_prompt(
        ObjectPrompt(
            1,
            "vehicle",
            3,
            (PromptPoint(545, 390), PromptPoint(530, 380), PromptPoint(550, 410)),
        )
    )
    corrected_predictions = list(session.propagate(start_frame_idx=3, max_frame_num_to_track=3))
    report = {
        "model_load_seconds": load_seconds,
        "frame_count_available": len(frames),
        "object_ids_after_first_prompt": list(first.object_ids),
        "object_ids_after_second_prompt": list(second.object_ids),
        "initial_frames": [
            {"frame_index": item.frame_index, "mask_pixels_by_object": mask_counts(item)}
            for item in initial_predictions
        ],
        "correction_frame": correction.frame_index,
        "correction_mask_pixels_by_object": mask_counts(correction),
        "corrected_frames": [
            {"frame_index": item.frame_index, "mask_pixels_by_object": mask_counts(item)}
            for item in corrected_predictions
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
