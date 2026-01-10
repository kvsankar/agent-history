"""Entry point for agent-history package.

This module allows running the package as a module:
    python -m agent_history [args]

It delegates to the CLI orchestrator which handles the full command pipeline.
"""

import sys

from agent_history.cli.orchestrator import main

if __name__ == "__main__":
    sys.exit(main())
