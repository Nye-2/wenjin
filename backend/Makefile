# Wenjin Backend Makefile

.PHONY: install dev gateway worker dev-all debug-langgraph test test-file test-cov lint format typecheck clean db-migrate db-revision db-upgrade db-downgrade

all: install

install:
	uv sync --extra dev

# Canonical local API entry
dev: gateway

gateway:
	uv run uvicorn src.gateway.app:app --reload --port 8001

worker:
	uv run python -m src.task.worker

dev-all:
	@echo "Start the gateway and worker in separate terminals:"
	@echo "  make gateway"
	@echo "  make worker"

# Optional debug entry for inspecting the lead-agent graph directly.
debug-langgraph:
	uv run langgraph dev --port 2024 --config langgraph.json

test:
	PYTHONPATH=. uv run pytest tests/ -v

test-file:
	PYTHONPATH=. uv run pytest $(file) -v

test-cov:
	PYTHONPATH=. uv run pytest tests/ --cov=src --cov-report=html

lint:
	uv run ruff check src/

format:
	uv run ruff format src/

typecheck:
	uv run mypy src/

clean:
	rm -rf .pytest_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .mypy_cache/
	rm -rf __pycache__/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

db-migrate:
	uv run alembic revision --autogenerate -m "$(message)"
	uv run alembic upgrade head

db-revision:
	uv run alembic revision -m "$(message)"

db-upgrade:
	uv run alembic upgrade head

db-downgrade:
	uv run alembic downgrade -1
