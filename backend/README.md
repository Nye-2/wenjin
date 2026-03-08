# AcademiaGPT v2 Backend

Academic AI Assistant with Lead Agent + Middleware + Skills architecture.

## Completed Features

- **Paper Extraction Service** - PDF processing and metadata extraction
- **User Service** - Authentication, user management, and profile handling
- **Workspace Service** - Project organization and management
- **Artifact Service** - Research artifact tracking and lineage
- **Paper Service** - Paper management and search
- **Skill Execution Framework** - Pluggable skill system with:
  - Deep Research Skill
  - Framework Designer Skill
  - Fullpaper Writer Skill
  - Literature Review Skill
- **API Routers**:
  - Auth Router (login, register, token refresh)
  - Workspaces Router (CRUD operations)
  - Papers Router (upload, search, extraction)
  - Artifacts Router (CRUD + lineage)
  - Chat Router (conversation threads)
- **Input Validation** - Request validation using Pydantic
- **Error Handling** - Centralized error handling middleware
- **API Integration Tests** - Comprehensive endpoint testing

## Tech Stack
- Python 3.12+
- FastAPI
- SQLAlchemy 2.0 (async)
- PostgreSQL + pgvector
- Redis
- LangGraph / LangChain
- OpenAI / Anthropic APIs

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
│   ├── app.py           # Main application
│   ├── routers/        # API endpoints
│   ├── middleware/     # Error handling, validation
│   └── validators/     # Request validators
├── agents/           # Lead agent and middlewares
│   ├── lead_agent/     # Main orchestrating agent
│   └── middlewares/    # Request processing pipeline
├── academic/         # Academic services and tools
│   ├── services/       # Business logic services
│   ├── tools/          # Academic tools (search, extraction)
│   ├── cache/          # Redis caching
│   └── database/       # Database session management
├── database/         # SQLAlchemy models
│   ├── models/        # ORM models
│   └── session.py     # Database session
├── models/           # LLM factory
│   └── factory.py     # Model creation
├── services/         # Shared services
│   ├── auth.py        # Authentication utilities
│   └── user_service.py # User management
├── skills/           # Skill system
│   ├── base.py        # Base skill classes
│   ├── executor.py    # Skill execution
│   └── implementations/  # Skill implementations
└── tools/            # Built-in tools
```

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login
- `POST /api/auth/refresh` - Refresh access token
- `GET /api/auth/me` - Get current user

### Workspaces
- `GET /api/workspaces` - List workspaces
- `POST /api/workspaces` - Create workspace
- `GET /api/workspaces/{id}` - Get workspace
- `PUT /api/workspaces/{id}` - Update workspace
- `DELETE /api/workspaces/{id}` - Delete workspace
- `GET /api/workspaces/{id}/papers` - List workspace papers

### Papers
- `GET /api/papers` - List papers
- `POST /api/papers` - Create paper
- `GET /api/papers/{id}` - Get paper
- `PUT /api/papers/{id}` - Update paper
- `DELETE /api/papers/{id}` - Delete paper
- `POST /api/papers/{id}/extract` - Trigger extraction
- `GET /api/papers/{id}/sections` - Get paper sections
- `POST /api/papers/search` - Search papers

### Artifacts
- `GET /api/artifacts` - List artifacts
- `POST /api/artifacts` - Create artifact
- `GET /api/artifacts/{id}` - Get artifact
- `PUT /api/artifacts/{id}` - Update artifact
- `DELETE /api/artifacts/{id}` - Delete artifact
- `GET /api/artifacts/{id}/lineage` - Get artifact lineage

### Chat
- `POST /api/threads` - Create thread
- `GET /api/threads/{id}` - Get thread
- `DELETE /api/threads/{id}` - Delete thread
- `POST /api/chat` - Send message (non-streaming)
- `POST /api/chat/stream` - Send message (streaming)

## Testing

The project has 790+ tests covering:
- Services (extraction, user, workspace, artifact, paper)
- API endpoints (auth, workspaces, papers, artifacts)
- Skills (deep research, framework designer, fullpaper writer, literature review)
- Academic tools (PDF extraction, semantic scholar)

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=term-missing
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection URL | Yes |
| `REDIS_URL` | Redis connection URL | Yes |
| `JWT_SECRET_KEY` | Secret key for JWT tokens | Yes |
| `OPENAI_API_KEY` | OpenAI API key | Yes |
| `ANTHROPIC_API_KEY` | Anthropic API key | No |
| `SEMANTIC_SCHOLAR_API_KEY` | Semantic Scholar API key | No |

## License

MIT
