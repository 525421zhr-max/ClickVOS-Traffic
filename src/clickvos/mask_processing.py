"""Transparent, optional mask cleanup and visualization helpers."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ComponentResult:
    mask: np.ndarray
    component_count: int
    raw_foreground_pixels: int
    kept_foreground_pixels: int


def keep_largest_component(mask: np.ndarray) -> ComponentResult:
    if mask.ndim != 2:
        raise ValueError("mask must be two-dimensional")
    binary = mask.astype(bool, copy=False)
    remaining = {tuple(point) for point in np.argwhere(binary)}
    largest: list[tuple[int, int]] = []
    component_count = 0
    height, width = binary.shape
    while remaining:
        component_count += 1
        start = remaining.pop()
        queue = deque([start])
        component = [start]
        while queue:
            y, x = queue.popleft()
            for neighbor in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                ny, nx = neighbor
                if 0 <= ny < height and 0 <= nx < width and neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
                    component.append(neighbor)
        if len(component) > len(largest):
            largest = component
    cleaned = np.zeros_like(binary)
    if largest:
        ys, xs = zip(*largest)
        cleaned[np.asarray(ys), np.asarray(xs)] = True
    return ComponentResult(
        mask=cleaned,
        component_count=component_count,
        raw_foreground_pixels=int(binary.sum()),
        kept_foreground_pixels=len(largest),
    )


def mask_boundary(mask: np.ndarray) -> np.ndarray:
    binary = mask.astype(bool, copy=False)
    interior = binary.copy()
    interior[1:, :] &= binary[:-1, :]
    interior[:-1, :] &= binary[1:, :]
    interior[:, 1:] &= binary[:, :-1]
    interior[:, :-1] &= binary[:, 1:]
    return binary & ~interior
