"""Export utilities for session export handler.

This package provides focused modules for different aspects of session export:
- markdown: Markdown generation from session messages
- splitting: Conversation splitting logic
- manifest: Index manifest generation
- ndjson: NDJSON export format
- source: Source file copying
"""

from agent_history.export.manifest import (
    classify_session_source,
    format_source_label,
    format_workspace_sources,
    generate_index_manifest,
    scan_workspace_directories,
)
from agent_history.export.markdown import (
    generate_markdown_file_header,
    generate_message_section,
    generate_metadata_section,
    generate_part_markdown,
    parse_jsonl_to_markdown,
)
from agent_history.export.ndjson import (
    build_output_filename_ndjson,
    normalize_message_to_unified,
    write_ndjson_export,
)
from agent_history.export.source import copy_source_file
from agent_history.export.splitting import (
    MIN_MESSAGES_FOR_SPLIT,
    calculate_split_score,
    estimate_message_lines,
    find_best_split_point,
    generate_markdown_parts,
    get_time_gap,
)

__all__ = [
    # Markdown generation
    "parse_jsonl_to_markdown",
    "generate_markdown_file_header",
    "generate_message_section",
    "generate_metadata_section",
    "generate_part_markdown",
    # Splitting
    "generate_markdown_parts",
    "find_best_split_point",
    "estimate_message_lines",
    "calculate_split_score",
    "get_time_gap",
    "MIN_MESSAGES_FOR_SPLIT",
    # Manifest
    "generate_index_manifest",
    "scan_workspace_directories",
    "classify_session_source",
    "format_source_label",
    "format_workspace_sources",
    # NDJSON
    "build_output_filename_ndjson",
    "write_ndjson_export",
    "normalize_message_to_unified",
    # Source
    "copy_source_file",
]
