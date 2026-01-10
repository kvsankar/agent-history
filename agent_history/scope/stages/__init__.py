"""
Stage-specific modules for the 4-stage scope resolution pipeline.

Each stage transforms the scope specification progressively:
- Stage 1 (project.py): Expand ProjectRecords to ScopeRecords
- Stage 2 (home.py): Resolve HomeSpecs to concrete home strings
- Stage 3 (workspace.py): Resolve WorkspaceSpecs to concrete paths
- Stage 4 (session.py): Collect sessions for each workspace
"""

from agent_history.scope.stages.home import HomeStage
from agent_history.scope.stages.project import ProjectStage
from agent_history.scope.stages.session import SessionStage
from agent_history.scope.stages.workspace import WorkspaceStage

__all__ = [
    "ProjectStage",
    "HomeStage",
    "WorkspaceStage",
    "SessionStage",
]
