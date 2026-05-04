"""CLI Constants for agent-history command.

This module contains magic strings and configuration constants
extracted from the parser module for better maintainability.
"""

from __future__ import annotations

# =============================================================================
# Flag categories
# =============================================================================

# Flags that require a value argument (used in argument preprocessing)
FLAGS_WITH_VALUES = frozenset({
    "-n", "--name",
    "--format",
    "--since", "--until",
    "--agent",
    "-w", "--width",
    "-o", "--output",
    "--split",
    "--jobs",
    "--home",
    "-r", "--remote",
    "--project",
    "--session", "--session-id",
    "--by",
    "--top-ws",
    "--bin-dir",
    "--skill-dir",
})

# =============================================================================
# Resource subcommands
# =============================================================================

# Subcommands available for each resource type
RESOURCE_SUBCOMMANDS = {
    "ws": frozenset({"list", "show", "export", "stats"}),
    "session": frozenset({"list", "show", "export", "stats"}),
    "project": frozenset({"list", "show", "add", "remove", "export", "stats"}),
    "home": frozenset({"list", "show", "add", "remove", "export", "stats"}),
    "gemini-index": frozenset({"index"}),
    "install": frozenset({"run"}),
    "reset": frozenset({"run"}),
    "fetch": frozenset({"run"}),
}

# Subset used in preprocessing (ws and session only)
WS_SUBCOMMANDS = frozenset({"list", "show", "export", "stats"})
SESSION_SUBCOMMANDS = frozenset({"list", "show", "export", "stats"})

# =============================================================================
# Agent choices
# =============================================================================

AGENT_CHOICES = ("auto", "claude", "codex", "gemini")
DEFAULT_AGENT = "auto"

# =============================================================================
# Output format choices
# =============================================================================

OUTPUT_FORMAT_CHOICES = ("table", "tsv", "json")

# =============================================================================
# Default values
# =============================================================================

DEFAULT_OUTPUT_DIR = "./ai-chats"
MIN_SPLIT_LINES = 10

# =============================================================================
# Resource and verb names
# =============================================================================

# Resource names
RESOURCE_SESSION = "session"
RESOURCE_WS = "ws"
RESOURCE_PROJECT = "project"
RESOURCE_HOME = "home"
RESOURCE_GEMINI_INDEX = "gemini-index"
RESOURCE_INSTALL = "install"
RESOURCE_RESET = "reset"
RESOURCE_FETCH = "fetch"

# Default verbs
DEFAULT_VERB_LIST = "list"
DEFAULT_VERB_INDEX = "index"
DEFAULT_VERB_RUN = "run"

# =============================================================================
# Global flags that take values (used in preprocessing)
# =============================================================================

GLOBAL_FLAGS_WITH_VALUES = frozenset({"--agent"})
