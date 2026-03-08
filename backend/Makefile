# AcademiaGPT Backend Makefile

.PHONY: install dev gateway test lint format clean

# Default target
all: install

# Install dependencies
install:
	uv sync

# Run LangGraph server (port 2024)
dev:
	uv run langgraph dev --port 2024

# Run Gateway API (port 8001)
gateway:
	uv run uvicorn src.gateway.app:app --reload --port 8001

# Run all services
all-services:
	@echo "Starting LangGraph on port 2024..."
	@uv run langgraph dev --port 2024 &
	@echo "Starting Gateway on port 8001..."
	@uv run uvicorn src.gateway.app:app --reload --port 8001 &
	@wait

# Run tests
test:
	PYTHONPATH=. uv run pytest tests/ -v

# Run specific test file
test-file:
	PYTHONPATH=. uv run pytest $(file) -v

# Run tests with coverage
test-cov:
	PYTHONPATH=. uv run pytest tests/ --cov=src --cov-report=html

# Lint with ruff
lint:
	uv run ruff check src/

# Format with ruff
format:
	uv run ruff format src/

# Type check with mypy
typecheck:
	uv run mypy src/

# Clean up
clean:
	rm -rf .pytest_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .mypy_cache/
	rm -rf __pycache__/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Database migrations
db-migrate:
	uv run alembic revision --autogenerate -m "$(message)"
	uv run alembic upgrade head

# Create new migration
db-revision:
	uv run alembic revision -m "$(message)"

# Apply migrations
db-upgrade:
	uv run alembic upgrade head

# Rollback migrations
db-downgrade:
	uv run alembic downgrade -1
