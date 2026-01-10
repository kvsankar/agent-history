"""Type aliases for commonly used dict types in agent-history.

This module provides type aliases to improve code clarity and enable better
type checking for dictionary types used throughout the codebase.

These aliases represent the common data structures:
- SessionDict: Individual session data (agent, file, modified, etc.)
- WorkspaceDict: Workspace aggregation data (workspace, sessions, status)
- HomeDict: Home information (home, type, status, session_count)
- ProjectDict: Project configuration (project, homes, workspaces)
- StatsDict: Statistics aggregation (total_sessions, by_agent, etc.)
- MessageDict: Message data from session files
- ContentBlock: Content blocks within messages
- MetricsDict: Usage metrics (tokens, timing, etc.)
"""

from typing import Any, Dict, List

# Session and workspace data types
# SessionDict contains fields like: agent, file, filename, modified, message_count,
# workspace, workspace_readable, home
SessionDict = Dict[str, Any]

# WorkspaceDict contains fields like: workspace, session_count, sessions, status,
# last_modified, home, agents
WorkspaceDict = Dict[str, Any]

# HomeDict contains fields like: home, type, status, session_count, workspace_count,
# last_modified, workspaces, agents
HomeDict = Dict[str, Any]

# ProjectDict contains fields like: project, name, homes, workspaces, session_count
ProjectDict = Dict[str, Any]

# StatsDict contains fields like: total_sessions, total_messages, by_agent, by_home,
# by_workspace
StatsDict = Dict[str, Any]

# Message types
# MessageDict contains fields like: role, content, timestamp, uuid, model, usage
MessageDict = Dict[str, Any]

# ContentBlock is a block within message content (for list-style content)
# Contains fields like: type, text, name, input, output
ContentBlock = Dict[str, Any]

# Metrics types
# MetricsDict contains fields like: input_tokens, output_tokens, latency
MetricsDict = Dict[str, Any]

# Export related types
ExportResultDict = Dict[str, Any]

# Type for grouped sessions by workspace: {workspace_path: [SessionDict, ...]}
WorkspaceSessionsMap = Dict[str, List[SessionDict]]

# Type for grouped workspaces by home: {home: [WorkspaceDict, ...]}
HomeWorkspacesMap = Dict[str, List[WorkspaceDict]]

__all__ = [
    "SessionDict",
    "WorkspaceDict",
    "HomeDict",
    "ProjectDict",
    "StatsDict",
    "MessageDict",
    "ContentBlock",
    "MetricsDict",
    "ExportResultDict",
    "WorkspaceSessionsMap",
    "HomeWorkspacesMap",
]
