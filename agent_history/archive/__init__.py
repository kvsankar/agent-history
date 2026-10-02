"""Session archive: collect agent session files into a compressed archive and verify it.

See docs/design-v2/archive-library.md. Needs the ``archive`` extra (zstandard).
"""

from agent_history.archive.collect import RunSummary, collect_source
from agent_history.archive.config import ArchiveConfig, SourceConfig, load_config, parse_config
from agent_history.archive.errors import ArchiveConfigError, ArchiveError
from agent_history.archive.transport import open_destination
from agent_history.archive.verify import VerifyReport, verify_source

__all__ = [
    "ArchiveConfig",
    "ArchiveConfigError",
    "ArchiveError",
    "RunSummary",
    "SourceConfig",
    "VerifyReport",
    "collect_source",
    "load_config",
    "open_destination",
    "parse_config",
    "verify_source",
]
