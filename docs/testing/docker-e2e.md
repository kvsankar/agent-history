# Docker E2E Testing Infrastructure

<!-- doc-meta
doc_role: guide
audience: maintainer
lifecycle: current
content_type: workflow
surface: internal
canonicality: primary
-->

This directory contains Docker configuration for end-to-end testing of `cagelens` with real SSH connections.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Network                           │
│                                                             │
│  ┌─────────────────┐              ┌─────────────────┐      │
│  │   node-alpha    │◄────SSH────►│   node-beta     │      │
│  │  (Ubuntu 22.04) │              │  (Ubuntu 22.04) │      │
│  ├─────────────────┤              ├─────────────────┤      │
│  │ Users:          │              │ Users:          │      │
│  │  - alice        │              │  - charlie      │      │
│  │  - bob          │              │  - dave         │      │
│  │                 │              │                 │      │
│  │ Synthetic data: │              │ Synthetic data: │      │
│  │  ~/.claude/     │              │  ~/.claude/     │      │
│  │  ~/.codex/      │              │  ~/.codex/      │      │
│  │  ~/.gemini/     │              │  ~/.gemini/     │      │
│  │  ~/.pi/         │              │  ~/.pi/         │      │
│  └─────────────────┘              └─────────────────┘      │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   test-runner                        │   │
│  │              (Python 3.11 + pytest)                  │   │
│  │         Mounts /app (project code, read-only)        │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Build and start all containers
cd docker
docker-compose up -d --build

# Run E2E tests
docker-compose run test-runner

# Run specific test file
docker-compose run test-runner pytest tests/e2e_docker/test_ssh_remote.py -v

# Run with verbose output
docker-compose run test-runner pytest tests/e2e_docker/ -v -s

# Cleanup
docker-compose down -v
```

## Test Users

| Node | Users | Purpose |
|------|-------|---------|
| node-alpha | alice, bob | First SSH target |
| node-beta | charlie, dave | Second SSH target |

All users have:
- SSH key-based authentication (passwordless)
- Synthetic Claude, Codex, Gemini, and Pi sessions
- Home directories with project workspaces

## Synthetic Data

The `generate-sessions.sh` script creates:

- **Claude sessions**: `~/.claude/projects/-home-{user}-myproject/session-claude-001.jsonl`
- **Codex sessions**: `~/.codex/sessions/2025/01/15/rollout-*.jsonl`
- **Gemini sessions**: `~/.gemini/tmp/{project-id}/chats/session-*.jsonl`
  plus one legacy `session-*.json`
- **Pi sessions**: `~/.pi/agent/sessions/--home-{user}-myproject--/session-pi-001.jsonl`

Each user has sessions in:
- `myproject` - main test workspace
- `another-project` - secondary workspace (Claude only)

## Test Categories

| File | Tests |
|------|-------|
| `test_ssh_connection.py` | SSH connectivity and generated session data |
| `test_remote_operations.py` | `ws -r`, `session list -r`, `export -r`, and `--agent` filters |
| `test_multi_home.py` | Local plus remote homes and multi-user scenarios |

## Debugging

```bash
# Start containers in foreground to see logs
docker-compose up

# Shell into a node
docker-compose exec node-alpha bash

# Shell into test-runner
docker-compose run test-runner bash

# Test SSH from runner to node
docker-compose run test-runner ssh alice@node-alpha whoami

# View generated session data
docker-compose exec node-alpha ls -la /home/alice/.claude/projects/
```

## Files

```
docker/
├── Dockerfile.node           # SSH-enabled Ubuntu with test users
├── Dockerfile.runner         # Python + pytest + SSH client
├── docker-compose.yml        # Multi-container orchestration
├── scripts/
│   ├── create-users.sh       # Creates users with SSH keys
│   ├── generate-sessions.sh  # Creates synthetic AI sessions
│   ├── setup-ssh-client.sh   # Configures SSH for test-runner
│   ├── entrypoint-node.sh    # Node container startup
│   └── entrypoint-runner.sh  # Runner container startup
└── README.md                 # This file
```

## Adding New Tests

1. Create test file in `tests/e2e_docker/`
2. Import fixtures from `conftest.py`
3. Use `run_cli()` to execute cagelens commands
4. Use `ssh_run()` for direct SSH commands
5. Mark tests with `pytestmark = pytest.mark.e2e_docker`

## CI Integration

To run in CI, add a workflow step:

```yaml
- name: Run Docker E2E tests
  run: |
    cd docker
    docker-compose up -d --build
    docker-compose run test-runner pytest tests/e2e_docker/ -v
    docker-compose down -v
```
