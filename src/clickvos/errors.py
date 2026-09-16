"""Stable application errors suitable for CLI and future web UI responses."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    VIDEO_NOT_FOUND = "video_not_found"
    VIDEO_EMPTY = "video_empty"
    VIDEO_UNSUPPORTED = "video_unsupported"
    VIDEO_TOO_LARGE = "video_too_large"
    VIDEO_INSPECTION_FAILED = "video_inspection_failed"
    FRAME_EXTRACTION_FAILED = "frame_extraction_failed"
    TASK_CONFLICT = "task_conflict"
    CONFIG_INVALID = "config_invalid"
    DEPENDENCY_MISSING = "dependency_missing"


@dataclass(frozen=True)
class ClickVOSError(RuntimeError):
    code: ErrorCode
    user_message: str
    detail: str | None = None

    def __str__(self) -> str:
        return self.user_message

    def as_dict(self) -> dict[str, str]:
        result = {"code": self.code.value, "message": self.user_message}
        if self.detail:
            result["detail"] = self.detail
        return result

