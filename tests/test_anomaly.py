from clickvos.anomaly import ReactivationGuard, detect_fragmentation, detect_reactivation


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


def test_detects_fragmented_mask() -> None:
    anomalies = detect_fragmentation({"00000.png": 1, "00001.png": 3})
    assert len(anomalies) == 1
    assert anomalies[0].frame_index == 1
    assert anomalies[0].evidence["component_count"] == 3


def test_guard_suppresses_reactivation_and_following_masks() -> None:
    guard = ReactivationGuard(minimum_empty_frames=3)
    counts = [100, 0, 0, 0, 80, 90]
    decisions = [guard.observe(index, count) for index, count in enumerate(counts)]
    assert decisions[4].triggered is True
    assert decisions[4].empty_frame_count == 3
    assert decisions[4].suppress is True
    assert decisions[5].suppress is True


def test_guard_allows_user_confirmed_reactivation() -> None:
    guard = ReactivationGuard(minimum_empty_frames=2)
    guard.observe(0, 100)
    guard.observe(1, 0)
    guard.observe(2, 0)
    decision = guard.observe(3, 80, confirmed=True)
    assert decision.suppress is False
    assert decision.triggered is False


def test_guard_does_not_block_initial_appearance() -> None:
    guard = ReactivationGuard(minimum_empty_frames=2)
    assert guard.observe(0, 0).suppress is False
    assert guard.observe(1, 0).suppress is False
    assert guard.observe(2, 50).suppress is False
