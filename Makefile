.PHONY: test test-unit test-integration

# Use uv to run pytest in the project venv/environment.
# If you prefer plain pytest, replace `uv run` with `python -m`.

test:
	uv run python -m pytest -q

test-unit:
	uv run python -m pytest -q -m "not integration"

test-integration:
	uv run python -m pytest -q -m integration tests/integration
