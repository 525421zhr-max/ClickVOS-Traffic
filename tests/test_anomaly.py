from clickvos.anomaly import detect_reactivation


def test_detects_cp02_style_long_reactivation() -> None:
    counts = {f"{index:05d}.png": (100 if index < 2 or index >= 8 else 0) for index in range(10)}
    anomalies = detect_reactivation(counts, minimum_empty_frames=3)
    assert len(anomalies) == 1
    assert anomalies[0].frame_index == 8
    assert anomalies[0].evidence["empty_frame_count"] == 6


def test_ignores_short_dropout() -> None:
    counts = {"00000.png": 100, "00001.png": 0, "00002.png": 100}
    assert detect_reactivation(counts, minimum_empty_frames=2) == []


def test_initial_empty_frames_are_not_reactivation() -> None:
    counts = {"00000.png": 0, "00001.png": 0, "00002.png": 100}
    assert detect_reactivation(counts) == []
