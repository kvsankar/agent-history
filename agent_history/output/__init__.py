"""Output formatting for agent-history.

This package provides output formatting components:
- OutputFormatter: Main formatter coordinator
- TableFormatter: ASCII table output
- JsonFormatter: JSON output
- TsvFormatter: Tab-separated values output
- FormatterError: Formatting error exception
"""

from agent_history.output.formatter import (
    DataFormatter,
    FormatterError,
    JsonFormatter,
    OutputFormatter,
    TableFormatter,
    TsvFormatter,
)

__all__ = [
    "DataFormatter",
    "FormatterError",
    "JsonFormatter",
    "OutputFormatter",
    "TableFormatter",
    "TsvFormatter",
]
