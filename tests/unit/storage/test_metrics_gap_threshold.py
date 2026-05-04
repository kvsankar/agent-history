"""Work-period gap threshold behavior."""

from agent_history.storage import metrics


def test_work_period_gap_threshold_is_30_minutes():
    """Gap threshold should be 30 minutes per spec/legacy behavior."""
    assert metrics.WORK_PERIOD_GAP_THRESHOLD == 30 * 60
