# AcademiaGPT v2

Academic AI Assistant with Lead Agent + Middleware + Skills architecture.

## Features

- Literature research and analysis
- Research idea generation
- Academic paper writing assistance
- Citation management

## Tech Stack

- Python 3.12+
- FastAPI
- SQLAlchemy 2.0 (async)
- PostgreSQL + pgvector
- Redis
- LangGraph / LangChain

## Quick Start

```bash
# Install dependencies
uv sync

# Run database migrations
uv run alembic upgrade head

# Start the gateway API
uv run uvicorn src.gateway.app:app --reload --port 8001

# Start the LangGraph server
uv run langgraph dev --port 2024
```

## Project Structure

```
src/
├── gateway/          # FastAPI gateway
├── agents/           # Lead agent and middlewares
├── academic/         # Academic services and tools
├── database/         # SQLAlchemy models
├── models/           # LLM factory
├── tools/            # Built-in tools
├── subagents/        # Subagent registry
├── skills/           # Skill loader
└── config/           # Configuration
```

## License

MIT
