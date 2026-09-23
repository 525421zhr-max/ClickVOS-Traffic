import importlib.util
import zipfile
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scan_mots_gaps.py"
spec = importlib.util.spec_from_file_location("scan_mots_gaps", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_internal_gap_and_ignore_region(tmp_path):
    archive = tmp_path / "instances_txt.zip"
    lines = [
        "0 1001 1 375 1242 x",
        "0 10000 10 375 1242 x",
        "4 1001 1 375 1242 x",
        "5 2001 2 375 1242 x",
        "6 2001 2 375 1242 x",
    ]
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("instances_txt/0000.txt", "\n".join(lines))
    result = module.scan_annotations(archive, minimum_gap=3)
    assert result["candidate_count"] == 1
    assert result["candidate_count_by_class"] == {"car": 1, "pedestrian": 0, "other": 0}
    assert result["candidates"][0]["first_missing_frame"] == 1
    assert result["candidates"][0]["last_missing_frame"] == 3


def test_reject_invalid_minimum_gap(tmp_path):
    with pytest.raises(ValueError, match="minimum_gap"):
        module.scan_annotations(tmp_path / "missing.zip", minimum_gap=0)
