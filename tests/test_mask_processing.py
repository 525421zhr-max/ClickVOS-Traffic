import numpy as np

from clickvos.mask_processing import keep_largest_component, mask_boundary


def test_keep_largest_component_removes_disconnected_spill() -> None:
    mask = np.zeros((8, 10), dtype=bool)
    mask[1:5, 1:5] = True
    mask[6:8, 8:10] = True
    result = keep_largest_component(mask)
    assert result.component_count == 2
    assert result.raw_foreground_pixels == 20
    assert result.kept_foreground_pixels == 16
    assert result.mask[2, 2]
    assert not result.mask[6, 8]


def test_empty_mask_has_no_components() -> None:
    result = keep_largest_component(np.zeros((3, 3), dtype=bool))
    assert result.component_count == 0
    assert result.kept_foreground_pixels == 0


def test_boundary_is_inside_mask() -> None:
    mask = np.zeros((5, 5), dtype=bool)
    mask[1:4, 1:4] = True
    boundary = mask_boundary(mask)
    assert boundary.sum() == 8
    assert not boundary[2, 2]
