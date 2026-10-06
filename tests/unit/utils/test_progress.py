"""Progress lines for long syncs: one per interval, to the screen and a log file."""

import io
import time

from agent_history.utils import progress


def test_lines_report_phase_detail_and_counts(tmp_path):
    stream = io.StringIO()
    log_file = tmp_path / "logs" / "sync.log"
    log = progress.ProgressLog(interval=0.05, stream=stream, log_file=log_file)
    log.start("sync")
    log.set_phase("listing", "windows:alex codex")
    log.add("listed", 120)
    time.sleep(0.2)
    log.stop()

    lines = stream.getvalue().splitlines()
    assert lines
    assert "listing windows:alex codex" in lines[-2]
    assert "listed=120" in lines[-2]
    assert lines[-1].endswith("done") or "done" in lines[-1]
    assert log_file.read_text(encoding="utf-8").splitlines() == lines


def test_a_quiet_log_writes_only_the_file(tmp_path):
    log_file = tmp_path / "sync.log"
    log = progress.ProgressLog(interval=0.05, stream=None, log_file=log_file)
    log.start("sync")
    log.add("stored", 3)
    log.stop()

    assert "stored=3" in log_file.read_text(encoding="utf-8")


def test_a_large_log_file_is_rotated(tmp_path):
    log_file = tmp_path / "sync.log"
    log_file.write_text("x" * 2_000_000, encoding="utf-8")
    log = progress.ProgressLog(interval=10, stream=None, log_file=log_file, max_bytes=1_000_000)
    log.start("sync")
    log.stop()

    assert (tmp_path / "sync.log.1").exists()
    assert log_file.stat().st_size < 1_000


def test_module_helpers_do_nothing_when_no_log_is_running():
    progress.set_phase("listing", "local")
    progress.add("listed", 5)
    assert progress.current() is None
