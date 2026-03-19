# AcademiaGPT v2 Backend

Academic AI Assistant with Lead Agent + Middleware + Skills architecture.

## Completed Features

- **Paper Extraction Service** - PDF processing and metadata extraction
- **User Service** - Authentication, user management, and profile handling
- **Workspace Service** - Project organization and management
- **Artifact Service** - Research artifact tracking and lineage
- **Paper Service** - Paper management and search
- **LangGraph Workspace Features** - Unified feature execution for all workspace types:
  - Thesis: literature_management, opening_research, figure_generation, compile_export, deep_research
  - SCI: literature_search, paper_analysis, writing
  - Patent: patent_outline, prior_art_search
  - Proposal: proposal_outline, background_research
  - Software Copyright: copyright_materials, technical_description
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
  - Workspace Features Router (feature execution)
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
uv sync --extra dev

# Create a local backend env file (not tracked)
cp .env.example .env

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
│   ├── workspace_lead_agent.py  # Unified graph registry and executor
│   ├── graphs/           # LangGraph sub-graphs by workspace type
│   │   ├── _shared/      # Shared utilities (JSON parsing, normalization)
│   │   ├── thesis/       # Thesis workspace graphs
│   │   ├── sci/          # SCI paper workspace graphs
│   │   ├── patent/       # Patent workspace graphs
│   │   ├── proposal/     # Proposal workspace graphs
│   │   └── software_copyright/  # Software copyright graphs
│   └── middlewares/    # Request processing pipeline
├── academic/         # Academic services and tools
│   ├── services/       # Business logic services
│   ├── tools/          # Academic tools (search, extraction)
│   └── cache/          # Redis caching
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
├── task/             # Async task system
│   ├── service.py       # Task submission and management
│   ├── progress.py      # Progress tracking
│   └── handlers/        # Task handlers
├── workspace_features/  # Workspace feature registry and services
│   ├── registry.py      # Feature definitions
│   └── services/        # Feature service layer
└── tools/            # Built-in tools
```

## LangGraph Workspace Architecture

All workspace types now use a unified LangGraph architecture:

```
workspace_lead_agent.py
├── register_feature_graph()  # Decorator to register graph functions
├── execute_feature_graph()   # Unified entry point for all features
└── _ensure_graphs_loaded()   # Lazy loading of workspace modules

Each workspace type has its own graph directory:
- graphs/thesis/     → thesis_lead_agent.py (backward compatible)
- graphs/sci/        → literature_search, paper_analysis, writing
- graphs/patent/     → patent_outline, prior_art_search
- graphs/proposal/   → proposal_outline, background_research
- graphs/software_copyright/ → copyright_materials, technical_description
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
- `GET /api/papers` - List papers visible in owned workspaces
- `POST /api/papers` - Create paper in a workspace (`workspace_id` required)
- `POST /api/papers/upload` - Upload PDF into a workspace (`workspace_id` required)
- `GET /api/papers/{id}` - Get paper
- `PUT /api/papers/{id}` - Update paper
- `DELETE /api/papers/{id}` - Delete paper
- `POST /api/papers/{id}/extract` - Trigger extraction
- `GET /api/papers/{id}/sections` - Get paper sections
- `POST /api/papers/search` - Search papers

### Artifacts
- `GET /api/workspaces/{workspace_id}/artifacts` - Canonical artifact list route
- `POST /api/workspaces/{workspace_id}/artifacts` - Canonical artifact creation route
- `GET /api/workspaces/{workspace_id}/artifacts/{artifact_id}` - Canonical artifact detail route
- `PUT /api/workspaces/{workspace_id}/artifacts/{artifact_id}` - Canonical artifact update route
- `DELETE /api/workspaces/{workspace_id}/artifacts/{artifact_id}` - Canonical artifact delete route
- `GET /api/workspaces/{workspace_id}/artifacts/{artifact_id}/lineage` - Canonical artifact lineage route

### Chat
- `POST /api/threads` - Create thread
- `GET /api/threads` - List threads
- `GET /api/threads/{id}` - Get thread
- `DELETE /api/threads/{id}` - Delete thread
- `POST /api/chat` - Send message (non-streaming)
- `POST /api/chat/stream` - Send message (streaming)

Notes:

- `ChatThread.skill` is the persisted session-level capability selection.
- Chat requests may explicitly set `skill` to update the thread capability, or `null` to clear it.

### Subagents
- `POST /api/subagents/threads/{thread_id}/spawn` - Spawn subagent task
- `GET /api/subagents/threads/{thread_id}/tasks/{task_id}/status` - Get subagent task status
- `POST /api/subagents/threads/{thread_id}/tasks/{task_id}/cancel` - Cancel subagent task
- `GET /api/subagents/events` - Subscribe to subagent SSE events

## Testing

The project has comprehensive tests covering:
- Services (extraction, user, workspace, artifact, paper)
- API endpoints (auth, workspaces, papers, artifacts)
- LangGraph sub-graphs (all workspace types)
- Skills (deep research, framework designer, fullpaper writer, literature review)
- Academic tools (PDF extraction, semantic scholar)

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=term-missing

# Run specific graph tests
uv run pytest tests/agents/graphs/ -v
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
