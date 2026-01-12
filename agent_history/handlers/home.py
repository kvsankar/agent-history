"""Home management handlers for agent-history.

This module provides handlers for home add/remove commands.
These are special handlers that modify the config file rather than
operating on a scope of sessions.
"""

import sys
from typing import Any, Dict

from agent_history.handlers.base import CommandResult, VerbHandler
from agent_history.scope.context import OutputArgs
from agent_history.scope.types import ConcreteScope
from agent_history.storage.config import load_config, save_config


class HomeAddHandler(VerbHandler):
    """Handler for 'home add' command.

    Adds a new home (SSH remote, WSL, Windows, or web) to the configuration.
    """

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        """Add a home source to configuration.

        Args:
            scope: Not used for this command.
            verb_args: Contains 'source' (user@host string) or flags like
                'windows', 'wsl', 'web'.
            output_args: Output formatting options.

        Returns:
            CommandResult with success status and message.
        """
        source = verb_args.get("source")
        add_windows = verb_args.get("windows", False)
        add_wsl = verb_args.get("wsl")
        add_web = verb_args.get("web", False)

        # Determine what to add
        if add_web:
            source = "web"
        elif add_windows:
            # For now, just use a generic windows identifier
            # Full implementation would detect the Windows user
            source = "windows"
        elif add_wsl is not None:
            if add_wsl == "auto" or add_wsl is True:
                source = "wsl"
            else:
                source = f"wsl:{add_wsl}"
        elif not source:
            return CommandResult(
                success=False,
                data=None,
                data_type="message",
                errors=["Specify a source (user@host), --windows, --wsl, or --web"],
            )
        elif "@" not in source and source not in ("windows", "web") and not source.startswith("wsl:"):
            # Validate SSH remote format
            return CommandResult(
                success=False,
                data=None,
                data_type="message",
                errors=[
                    f"Invalid source format: {source}",
                    "Expected: user@hostname, --windows, --web, or --wsl",
                ],
            )

        config = load_config()
        homes = config.get("homes", [])

        if source in homes:
            return CommandResult(
                success=True,
                data={"message": f"Home '{source}' already configured."},
                data_type="message",
            )

        homes.append(source)
        config["homes"] = homes
        config["sources"] = homes  # keep in sync for backward compatibility

        if save_config(config):
            return CommandResult(
                success=True,
                data={"message": f"Added home: {source}"},
                data_type="message",
            )
        else:
            return CommandResult(
                success=False,
                data=None,
                data_type="message",
                errors=["Failed to save configuration"],
            )


class HomeRemoveHandler(VerbHandler):
    """Handler for 'home remove' command.

    Removes a home from the configuration.
    """

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        """Remove a home source from configuration.

        Args:
            scope: Not used for this command.
            verb_args: Contains 'source' (user@host string) or flags like
                'windows', 'wsl', 'web'.
            output_args: Output formatting options.

        Returns:
            CommandResult with success status and message.
        """
        source = verb_args.get("source")
        remove_windows = verb_args.get("windows", False)
        remove_wsl = verb_args.get("wsl")
        remove_web = verb_args.get("web", False)

        config = load_config()
        homes = config.get("homes", [])

        # Determine what to remove
        if remove_web:
            source = "web"
        elif remove_windows:
            # Find and remove any windows:* source
            windows_sources = [s for s in homes if s.startswith("windows:") or s == "windows"]
            if not windows_sources:
                return CommandResult(
                    success=False,
                    data=None,
                    data_type="message",
                    errors=["No Windows home configured"],
                )
            source = windows_sources[0]
        elif remove_wsl is not None:
            # Find and remove matching wsl:* source
            if remove_wsl == "auto" or remove_wsl is True:
                wsl_sources = [s for s in homes if s.startswith("wsl:") or s == "wsl"]
                if not wsl_sources:
                    return CommandResult(
                        success=False,
                        data=None,
                        data_type="message",
                        errors=["No WSL home configured"],
                    )
                source = wsl_sources[0]
            else:
                source = f"wsl:{remove_wsl}"
        elif not source:
            return CommandResult(
                success=False,
                data=None,
                data_type="message",
                errors=["Specify a source to remove, --windows, --web, or --wsl"],
            )

        if source not in homes:
            configured = ", ".join(homes) if homes else "(none)"
            return CommandResult(
                success=False,
                data=None,
                data_type="message",
                errors=[
                    f"Home '{source}' not found.",
                    f"Configured homes: {configured}",
                ],
            )

        homes.remove(source)
        config["homes"] = homes
        config["sources"] = homes  # keep in sync for backward compatibility

        if save_config(config):
            return CommandResult(
                success=True,
                data={"message": f"Removed home: {source}"},
                data_type="message",
            )
        else:
            return CommandResult(
                success=False,
                data=None,
                data_type="message",
                errors=["Failed to save configuration"],
            )
