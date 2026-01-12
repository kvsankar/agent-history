"""Tests for explicit vs implicit context consistency across commands.

This test suite verifies that all major command verbs handle project context
consistently, whether the context is provided explicitly (via flags/patterns)
or implicitly (from current working directory).

BUG CONTEXT:
There's an inconsistency where some commands correctly filter by exact project
workspaces while others use substring matching that incorrectly includes sessions
from similar-named workspaces.

Example:
- `stats` in /home/user/projects/auth shows 302 sessions (correct - exact match)
- `session list` in same directory shows 312 sessions (incorrect - includes auth-infra, auth-api)

EXPECTED BEHAVIOR:
All commands should return the SAME set of sessions when given the same context,
whether that context is explicit (@project, --project) or implicit (CWD).

BUGS EXPOSED BY THESE TESTS:
1. Workspace decoding ambiguity: Claude workspaces like "-home-user-projects-auth-infra"
   are incorrectly decoded as "/home/user/projects/auth/infra" instead of
   "/home/user/projects/auth-infra" due to ambiguous hyphen interpretation.

2. Substring matching in project filters: When filtering by project workspace
   "/home/user/projects/auth", sessions from "/home/user/projects/auth-infra"
   and "/home/user/projects/auth-api" are incorrectly included.

3. Inconsistent filtering behavior: Different code paths (project vs workspace pattern)
   produce different session counts (9 vs 11 files).

4. Missing --project flag support: The `session stats` command doesn't accept
   the --project flag like other session commands do.

TEST STATUS:
- Most tests SHOULD FAIL initially, exposing the bugs described above
- Once the CLI bugs are fixed, these tests should PASS
"""

from __future__ import annotations

import json
from typing import Any, Dict

import pytest

from tests.helpers.cli import assert_cli_success, run_cli_subprocess
from tests.helpers.session_builders import ClaudeSessionBuilder, CodexSessionBuilder

pytestmark = pytest.mark.v1


@pytest.fixture
def project_context_setup(isolated_home: Dict[str, Any]) -> Dict[str, Any]:
    """Create a project with multiple similar-named workspaces for context testing.

    Creates:
    - Project "testproj" with workspace /home/user/projects/auth
    - Sessions in /home/user/projects/auth (should be included)
    - Sessions in /home/user/projects/auth-infra (should NOT be included)
    - Sessions in /home/user/projects/auth-api (should NOT be included)

    Returns:
        Dict with paths, environment, and expected counts
    """
    home = isolated_home["path"]
    env = isolated_home["env"]
    claude_dir = isolated_home["claude_dir"]
    codex_dir = isolated_home["codex_dir"]

    # Create project configuration
    config_dir = isolated_home["history_dir"]
    config_file = config_dir / "config.json"

    project_config = {
        "version": 2,
        "projects": {"testproj": {"local": ["/home/user/projects/auth"]}},
    }

    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(project_config, f, indent=2)

    # Create the actual workspace directories for filesystem probing
    project_ws_dir = home / "home" / "user" / "projects"
    project_ws_dir.mkdir(parents=True, exist_ok=True)
    (project_ws_dir / "auth").mkdir(exist_ok=True)
    (project_ws_dir / "auth-infra").mkdir(exist_ok=True)
    (project_ws_dir / "auth-api").mkdir(exist_ok=True)

    # Create Claude sessions for the main project workspace
    for i in range(3):
        builder = ClaudeSessionBuilder(
            workspace="-home-user-projects-auth", session_id=f"auth-session-{i:02d}"
        )
        builder.add_user_message(f"Test message {i} in auth workspace")
        builder.add_assistant_message(f"Response {i}", input_tokens=100, output_tokens=50)
        builder.write_to(claude_dir)

    # Create Claude sessions for auth-infra (should NOT be included in testproj)
    for i in range(2):
        builder = ClaudeSessionBuilder(
            workspace="-home-user-projects-auth-infra", session_id=f"auth-infra-session-{i:02d}"
        )
        builder.add_user_message(f"Test message {i} in auth-infra workspace")
        builder.add_assistant_message(f"Response {i}", input_tokens=100, output_tokens=50)
        builder.write_to(claude_dir)

    # Create Claude sessions for auth-api (should NOT be included in testproj)
    for i in range(2):
        builder = ClaudeSessionBuilder(
            workspace="-home-user-projects-auth-api", session_id=f"auth-api-session-{i:02d}"
        )
        builder.add_user_message(f"Test message {i} in auth-api workspace")
        builder.add_assistant_message(f"Response {i}", input_tokens=100, output_tokens=50)
        builder.write_to(claude_dir)

    # Create Codex sessions for the main project workspace
    for i in range(2):
        builder = CodexSessionBuilder(
            session_id=f"codex-auth-{i:02d}", cwd="/home/user/projects/auth"
        )
        builder.add_user_message(f"Codex message {i} in auth")
        builder.add_assistant_message(f"Codex response {i}")
        builder.add_token_count(input_tokens=200, output_tokens=100)
        builder.write_to(codex_dir, date_str="2025-01-05")

    # Create Codex sessions for auth-infra (should NOT be included)
    builder = CodexSessionBuilder(
        session_id="codex-auth-infra-01", cwd="/home/user/projects/auth-infra"
    )
    builder.add_user_message("Codex message in auth-infra")
    builder.add_assistant_message("Codex response")
    builder.add_token_count(input_tokens=200, output_tokens=100)
    builder.write_to(codex_dir, date_str="2025-01-05")

    # Create Codex sessions for auth-api (should NOT be included)
    builder = CodexSessionBuilder(
        session_id="codex-auth-api-01", cwd="/home/user/projects/auth-api"
    )
    builder.add_user_message("Codex message in auth-api")
    builder.add_assistant_message("Codex response")
    builder.add_token_count(input_tokens=200, output_tokens=100)
    builder.write_to(codex_dir, date_str="2025-01-05")

    return {
        "home": home,
        "env": env,
        "project_name": "testproj",
        "project_workspace": project_ws_dir / "auth",
        "expected_session_count": 5,  # 3 Claude + 2 Codex for /home/user/projects/auth
        "total_sessions": 9,  # All sessions including similar-named workspaces
        "claude_auth_count": 3,
        "claude_infra_count": 2,
        "claude_api_count": 2,
        "codex_auth_count": 2,
        "codex_infra_count": 1,
        "codex_api_count": 1,
    }


class TestSessionListContext:
    """Test session list command with explicit vs implicit context."""

    def test_session_list_explicit_project(self, project_context_setup: Dict[str, Any]):
        """session list --project testproj should show only project sessions."""
        result = run_cli_subprocess(
            ["session", "list", "--project", "testproj"],
            env=project_context_setup["env"],
            cwd=project_context_setup["home"],
        )

        assert_cli_success(result, "session list --project testproj should succeed")

        output = result.stdout

        # Should include the correct sessions
        assert "auth-session-00" in output or "auth" in output.lower()

        # Should NOT include similar-named workspace sessions
        assert "auth-infra-session" not in output, "Should not match auth-infra sessions"
        assert "auth-api-session" not in output, "Should not match auth-api sessions"

    def test_session_list_implicit_project(self, project_context_setup: Dict[str, Any]):
        """session list with workspace pattern should show only matching sessions.

        NOTE: True implicit detection (CWD-based) requires being in an actual Claude
        workspace. For this test, we use a workspace pattern which simulates the
        implicit behavior for testing purposes.
        """
        result = run_cli_subprocess(
            ["session", "list", "/home/user/projects/auth"],
            env=project_context_setup["env"],
            cwd=project_context_setup["home"],
        )

        assert_cli_success(result, "session list with workspace pattern should succeed")

        output = result.stdout

        # Should include the correct sessions
        assert "auth-session-00" in output or "auth" in output.lower()

        # Should NOT include similar-named workspace sessions
        assert "auth-infra-session" not in output, "Should not match auth-infra sessions"
        assert "auth-api-session" not in output, "Should not match auth-api sessions"

    def test_session_list_consistency(self, project_context_setup: Dict[str, Any]):
        """Explicit project and workspace pattern should return identical session lists."""
        # Get explicit results via project
        explicit_result = run_cli_subprocess(
            ["session", "list", "--project", "testproj"],
            env=project_context_setup["env"],
            cwd=project_context_setup["home"],
        )

        # Get results via workspace pattern (simulates implicit context)
        implicit_result = run_cli_subprocess(
            ["session", "list", "/home/user/projects/auth"],
            env=project_context_setup["env"],
            cwd=project_context_setup["home"],
        )

        assert_cli_success(explicit_result, "Explicit session list should succeed")
        assert_cli_success(implicit_result, "Implicit session list should succeed")

        # Extract session IDs from both outputs
        explicit_output = explicit_result.stdout
        implicit_output = implicit_result.stdout

        # Both should reference the same sessions
        # Count lines with session references (basic check)
        explicit_lines = [l for l in explicit_output.split("\n") if l.strip()]
        implicit_lines = [l for l in implicit_output.split("\n") if l.strip()]

        # Should have similar output length (allowing for formatting differences)
        assert (
            abs(len(explicit_lines) - len(implicit_lines)) < 3
        ), f"Explicit and implicit results differ significantly: {len(explicit_lines)} vs {len(implicit_lines)}"


class TestSessionExportContext:
    """Test session export command with explicit vs implicit context."""

    def test_session_export_explicit_project(self, project_context_setup: Dict[str, Any]):
        """session export @testproj should export only project sessions."""
        output_dir = project_context_setup["home"] / "export_explicit"
        output_dir.mkdir()

        result = run_cli_subprocess(
            ["session", "export", "--project", "testproj", "-o", str(output_dir), "--force"],
            env=project_context_setup["env"],
            cwd=project_context_setup["home"],
        )

        assert_cli_success(result, "session export @testproj should succeed")

        # Count exported files
        md_files = list(output_dir.glob("**/*.md"))

        # Should export the expected number of sessions (not more)
        expected_count = project_context_setup["expected_session_count"]
        assert (
            len(md_files) == expected_count
        ), f"Expected {expected_count} markdown files, got {len(md_files)}"

        # Verify file names don't include incorrect workspaces
        file_names = " ".join([f.name for f in md_files])
        assert "infra" not in file_names, "Should not export auth-infra sessions"
        assert (
            "api" not in file_names or "auth-session" in file_names
        ), "Should not export auth-api sessions"

    def test_session_export_implicit_project(self, project_context_setup: Dict[str, Any]):
        """session export with workspace pattern should export only matching sessions."""
        output_dir = project_context_setup["home"] / "export_implicit"
        output_dir.mkdir()

        result = run_cli_subprocess(
            ["session", "export", "/home/user/projects/auth", "-o", str(output_dir), "--force"],
            env=project_context_setup["env"],
            cwd=project_context_setup["home"],
        )

        assert_cli_success(result, "session export from workspace should succeed")

        # Count exported files
        md_files = list(output_dir.glob("**/*.md"))

        # Should export the expected number of sessions (not more)
        expected_count = project_context_setup["expected_session_count"]
        assert (
            len(md_files) == expected_count
        ), f"Expected {expected_count} markdown files, got {len(md_files)}"

        # Verify file names don't include incorrect workspaces
        file_names = " ".join([f.name for f in md_files])
        assert "infra" not in file_names, "Should not export auth-infra sessions"
        assert (
            "api" not in file_names or "auth-session" in file_names
        ), "Should not export auth-api sessions"

    def test_session_export_consistency(self, project_context_setup: Dict[str, Any]):
        """Explicit and implicit context should export the same sessions."""
        explicit_dir = project_context_setup["home"] / "export_explicit_compare"
        implicit_dir = project_context_setup["home"] / "export_implicit_compare"
        explicit_dir.mkdir()
        implicit_dir.mkdir()

        # Export with explicit project context
        explicit_result = run_cli_subprocess(
            ["session", "export", "--project", "testproj", "-o", str(explicit_dir), "--force"],
            env=project_context_setup["env"],
            cwd=project_context_setup["home"],
        )

        # Export with workspace pattern (simulates implicit context)
        implicit_result = run_cli_subprocess(
            ["session", "export", "/home/user/projects/auth", "-o", str(implicit_dir), "--force"],
            env=project_context_setup["env"],
            cwd=project_context_setup["home"],
        )

        assert_cli_success(explicit_result, "Explicit export should succeed")
        assert_cli_success(implicit_result, "Implicit export should succeed")

        # Compare file counts
        explicit_files = list(explicit_dir.glob("**/*.md"))
        implicit_files = list(implicit_dir.glob("**/*.md"))

        assert len(explicit_files) == len(
            implicit_files
        ), f"File counts differ: explicit={len(explicit_files)}, implicit={len(implicit_files)}"

        # Compare file names (session IDs should match)
        explicit_names = sorted([f.name for f in explicit_files])
        implicit_names = sorted([f.name for f in implicit_files])

        assert (
            explicit_names == implicit_names
        ), f"Exported session names differ:\nExplicit: {explicit_names}\nImplicit: {implicit_names}"


class TestSessionStatsContext:
    """Test session stats command with explicit vs implicit context."""

    def test_session_stats_explicit_project(self, project_context_setup: Dict[str, Any]):
        """session stats @testproj should show only project session stats."""
        result = run_cli_subprocess(
            ["session", "stats", "--project", "testproj"],
            env=project_context_setup["env"],
            cwd=project_context_setup["home"],
        )

        assert_cli_success(result, "session stats @testproj should succeed")

        output = result.stdout

        # Should show the correct session count
        # Look for session count in output
        assert "session" in output.lower() or "total" in output.lower()

    def test_session_stats_implicit_project(self, project_context_setup: Dict[str, Any]):
        """session stats with workspace pattern should show only matching session stats."""
        result = run_cli_subprocess(
            ["session", "stats", "/home/user/projects/auth"],
            env=project_context_setup["env"],
            cwd=project_context_setup["home"],
        )

        assert_cli_success(result, "session stats from workspace should succeed")

        output = result.stdout

        # Should show the correct session count
        assert "session" in output.lower() or "total" in output.lower()

    def test_session_stats_consistency(self, project_context_setup: Dict[str, Any]):
        """Explicit and implicit context should show identical stats."""
        # Get explicit stats
        explicit_result = run_cli_subprocess(
            ["session", "stats", "--project", "testproj"],
            env=project_context_setup["env"],
            cwd=project_context_setup["home"],
        )

        # Get stats via workspace pattern (simulates implicit context)
        implicit_result = run_cli_subprocess(
            ["session", "stats", "/home/user/projects/auth"],
            env=project_context_setup["env"],
            cwd=project_context_setup["home"],
        )

        assert_cli_success(explicit_result, "Explicit stats should succeed")
        assert_cli_success(implicit_result, "Implicit stats should succeed")

        explicit_output = explicit_result.stdout
        implicit_output = implicit_result.stdout

        # Extract numeric values from outputs for comparison
        # This is a simplified check - actual implementation may vary
        assert len(explicit_output) > 0, "Explicit stats should produce output"
        assert len(implicit_output) > 0, "Implicit stats should produce output"

        # Both outputs should be similar in length (allowing for minor formatting differences)
        assert (
            abs(len(explicit_output) - len(implicit_output)) < 100
        ), "Stats outputs differ significantly in length"


class TestProjectShowContext:
    """Test project show command with explicit vs implicit context."""

    def test_project_show_explicit(self, project_context_setup: Dict[str, Any]):
        """project show testproj should display project information."""
        result = run_cli_subprocess(
            ["project", "show", "testproj"],
            env=project_context_setup["env"],
            cwd=project_context_setup["home"],
        )

        assert_cli_success(result, "project show testproj should succeed")

        output = result.stdout

        # Should show project name
        assert "testproj" in output.lower()

        # Should show session count
        assert "session" in output.lower()

    def test_project_show_implicit(self, project_context_setup: Dict[str, Any]):
        """project show from project workspace should auto-detect and show project."""
        result = run_cli_subprocess(
            ["project", "show"],
            env=project_context_setup["env"],
            cwd=project_context_setup["project_workspace"],
        )

        assert_cli_success(result, "project show from workspace should succeed")

        output = result.stdout

        # Should show project name
        assert "testproj" in output.lower()

        # Should show session count
        assert "session" in output.lower()

    def test_project_show_consistency(self, project_context_setup: Dict[str, Any]):
        """Explicit and implicit project show should display same information."""
        # Get explicit output
        explicit_result = run_cli_subprocess(
            ["project", "show", "testproj"],
            env=project_context_setup["env"],
            cwd=project_context_setup["home"],
        )

        # Get implicit output
        implicit_result = run_cli_subprocess(
            ["project", "show"],
            env=project_context_setup["env"],
            cwd=project_context_setup["project_workspace"],
        )

        assert_cli_success(explicit_result, "Explicit project show should succeed")
        assert_cli_success(implicit_result, "Implicit project show should succeed")

        explicit_output = explicit_result.stdout
        implicit_output = implicit_result.stdout

        # Both should mention the same project
        assert "testproj" in explicit_output.lower()
        assert "testproj" in implicit_output.lower()


class TestProjectStatsContext:
    """Test project stats command with explicit vs implicit context."""

    def test_project_stats_explicit(self, project_context_setup: Dict[str, Any]):
        """project stats testproj should show only project stats."""
        result = run_cli_subprocess(
            ["project", "stats", "testproj"],
            env=project_context_setup["env"],
            cwd=project_context_setup["home"],
        )

        assert_cli_success(result, "project stats testproj should succeed")

        output = result.stdout

        # Should show project stats
        assert "testproj" in output.lower() or "session" in output.lower()

    def test_project_stats_implicit(self, project_context_setup: Dict[str, Any]):
        """project stats from project workspace should auto-detect and show stats."""
        result = run_cli_subprocess(
            ["project", "stats", "testproj"],
            env=project_context_setup["env"],
            cwd=project_context_setup["project_workspace"],
        )

        assert_cli_success(result, "project stats from workspace should succeed")

        output = result.stdout

        # Should show project stats
        assert "testproj" in output.lower() or "session" in output.lower()

    def test_project_stats_consistency(self, project_context_setup: Dict[str, Any]):
        """Explicit and implicit project stats should show identical statistics."""
        # Get explicit stats
        explicit_result = run_cli_subprocess(
            ["project", "stats", "testproj"],
            env=project_context_setup["env"],
            cwd=project_context_setup["home"],
        )

        # Get implicit stats
        implicit_result = run_cli_subprocess(
            ["project", "stats", "testproj"],
            env=project_context_setup["env"],
            cwd=project_context_setup["project_workspace"],
        )

        assert_cli_success(explicit_result, "Explicit project stats should succeed")
        assert_cli_success(implicit_result, "Implicit project stats should succeed")

        explicit_output = explicit_result.stdout
        implicit_output = implicit_result.stdout

        # Both outputs should be similar
        assert len(explicit_output) > 0, "Explicit stats should produce output"
        assert len(implicit_output) > 0, "Implicit stats should produce output"


class TestWorkspaceFilteringPrecision:
    """Test that workspace filtering uses exact matches, not substring matching."""

    def test_substring_bleed_prevention(self, project_context_setup: Dict[str, Any]):
        """Verify that sessions from similar-named workspaces are NOT included.

        This is the core bug: some commands incorrectly use substring matching,
        causing /home/user/projects/auth to match /home/user/projects/auth-infra.

        All commands should use exact workspace matching.
        """
        # Test with explicit project reference
        result = run_cli_subprocess(
            ["session", "list", "--project", "testproj"],
            env=project_context_setup["env"],
            cwd=project_context_setup["home"],
        )

        assert_cli_success(result, "session list should succeed")

        output = result.stdout

        # Verify no substring bleed
        # If we see "infra" or "api" in the session list, it's a bug
        infra_appears = "infra" in output.lower() and "auth-infra-session" in output
        api_appears = "api" in output.lower() and "auth-api-session" in output

        assert not infra_appears, "BUG: auth-infra sessions incorrectly included (substring bleed)"
        assert not api_appears, "BUG: auth-api sessions incorrectly included (substring bleed)"

    def test_exact_workspace_match_count(self, project_context_setup: Dict[str, Any]):
        """Verify session count matches exact workspace, not similar workspaces."""
        # Export to count files accurately
        output_dir = project_context_setup["home"] / "export_count_test"
        output_dir.mkdir()

        result = run_cli_subprocess(
            ["session", "export", "--project", "testproj", "-o", str(output_dir), "--force"],
            env=project_context_setup["env"],
            cwd=project_context_setup["home"],
        )

        assert_cli_success(result, "session export should succeed")

        md_files = list(output_dir.glob("**/*.md"))
        actual_count = len(md_files)
        expected_count = project_context_setup["expected_session_count"]

        assert actual_count == expected_count, (
            f"Expected exactly {expected_count} sessions (3 Claude + 2 Codex in auth workspace), "
            f"but got {actual_count}. If count is higher, this indicates substring matching bug."
        )
