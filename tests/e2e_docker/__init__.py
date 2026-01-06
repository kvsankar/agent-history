"""Docker-based E2E tests for agent-history.

Run these tests via Docker:

    cd docker
    docker compose up -d --build
    docker compose run --rm test-runner pytest tests/e2e_docker/ -v
    docker compose down -v
"""
