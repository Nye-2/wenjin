# AcademiaGPT v2

Academic AI Assistant with Lead Agent + Middleware + Skills architecture.

## Project Status

**Completed Features:**

### Backend Services
- Paper Extraction Service - PDF processing and metadata extraction
- User Service - Authentication, user management, profile handling
- Workspace Service - Project organization and management
- Artifact Service - Research artifact tracking and lineage
- Paper Service - Paper management and search

### Skills
- Skill Execution Framework - Pluggable skill system
- Deep Research Skill - Literature search and gap analysis
- Framework Designer Skill - Abstract and outline generation
- Fullpaper Writer Skill - Section writing and citation management
- Literature Review Skill - Synthesis and comparison matrix

### API Routers
- Auth Router - Login, register, token refresh, user info
- Workspaces Router - CRUD operations, paper management
- Papers Router - Upload, search, extraction, sections
- Artifacts Router - CRUD operations, lineage tracking
- Features Router - Workspace feature discovery and execution
- Tasks Router - Task status and progress streaming
- Health Check Endpoint - System health monitoring

### Quality Assurance
- API Integration Tests - Comprehensive endpoint testing
- Input Validation - Request validation using Pydantic
- Error Handling - Centralized error handling middleware
- Backend pytest suites plus frontend type/lint checks

## Tech Stack

### Backend
- Python 3.12+
- FastAPI
- SQLAlchemy 2.0 (async)
- PostgreSQL + pgvector
- Redis
- LangGraph / LangChain

### Frontend
- Next.js 16
- React 19
- TypeScript
- TailwindCSS
- Zustand
- Axios

## Quick Start

### Prerequisites
- Docker and Docker Compose
- PostgreSQL 16+ with pgvector
- Redis 7.0+
- At least one configured LLM provider

### Using Docker Compose

```bash
# Clone the repository
git clone <repository-url>
cd academiagpt-v2

# Create a local backend env file (not tracked)
cp backend/.env.example backend/.env
# Edit backend/.env with your model/provider settings

# (Optional, for mainland China network) use Docker mirror env
cp .env.docker-cn.example .env

# Start all services
docker compose up -d --build

# Optional: verify one-shot migration container completed
docker compose logs -f migrate
```

### Manual Setup

```bash
# Backend setup
cd backend
uv sync --extra dev
# Create a local backend env file (not tracked)
cp .env.example .env
# Edit .env with your settings
uv run alembic upgrade head
uv run uvicorn src.gateway.app:app --reload --port 8001

# Frontend setup (in another terminal)
cd frontend
npm install
# Optional: create .env.local only if you need to override API/LangGraph URLs
# cp .env.example .env.local
npm run dev
```

## Project Structure

```
academiagpt-v2/
├── backend/
│   ├── src/
│   │   ├── gateway/       # FastAPI gateway
│   │   ├── agents/        # Lead agent and middlewares
│   │   ├── academic/      # Academic services and tools
│   │   ├── database/      # SQLAlchemy models
│   │   ├── models/        # LLM factory
│   │   ├── services/      # Auth and user services
│   │   ├── skills/        # Skill system
│   │   └── tools/         # Built-in tools
│   ├── tests/            # Test suite (790+ tests)
│   ├── alembic/          # Database migrations
│   └── pyproject.toml    # Project configuration
├── frontend/
│   ├── app/              # Next.js app router pages
│   ├── components/       # React components
│   ├── lib/              # Utilities and API client
│   └── stores/           # Zustand stores
├── docs/
│   ├── architecture/     # Architecture decision and API maps
│   ├── infrastructure/   # Deployment and operations runbooks
│   └── product/          # Product capability and contract docs
├── docker-compose.yml    # Docker Compose configuration
└── nginx.conf            # Nginx configuration
```

## API Documentation

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login and get tokens
- `POST /api/auth/refresh` - Refresh access token
- `GET /api/auth/me` - Get current user info

### Workspaces
- `GET /api/workspaces` - List user workspaces
- `POST /api/workspaces` - Create workspace
- `GET /api/workspaces/{id}` - Get workspace details
- `PUT /api/workspaces/{id}` - Update workspace
- `DELETE /api/workspaces/{id}` - Delete workspace

### Papers
- `GET /api/papers` - List papers visible in owned workspaces
- `POST /api/papers` - Create paper in a workspace (`workspace_id` required)
- `POST /api/papers/upload` - Upload PDF into a workspace (`workspace_id` required)
- `GET /api/papers/{id}` - Get paper details
- `POST /api/papers/{id}/extract` - Trigger extraction
- `POST /api/papers/search` - Search papers

### Artifacts
- `GET /api/workspaces/{workspace_id}/artifacts` - Canonical artifact list route
- `POST /api/workspaces/{workspace_id}/artifacts` - Canonical artifact creation route
- `GET /api/workspaces/{workspace_id}/artifacts/{artifact_id}` - Canonical artifact detail route
- `PUT /api/workspaces/{workspace_id}/artifacts/{artifact_id}` - Canonical artifact update route
- `DELETE /api/workspaces/{workspace_id}/artifacts/{artifact_id}` - Canonical artifact delete route
- `GET /api/workspaces/{workspace_id}/artifacts/{artifact_id}/lineage` - Canonical artifact lineage route

### Chat
- `POST /api/threads` - Create chat thread
- `GET /api/threads` - List chat threads
- `GET /api/threads/{id}` - Get chat thread with messages
- `DELETE /api/threads/{id}` - Delete chat thread
- `POST /api/chat` - Send message
- `POST /api/chat/stream` - Streaming chat

Notes:

- Thread skill selection is now persisted at the chat-thread level.
- Sending `skill: null` on chat requests explicitly clears the thread skill.

### Subagents
- `POST /api/subagents/threads/{thread_id}/spawn` - Spawn subagent task
- `GET /api/subagents/threads/{thread_id}/tasks/{task_id}/status` - Get subagent task status
- `POST /api/subagents/threads/{thread_id}/tasks/{task_id}/cancel` - Cancel subagent task
- `GET /api/subagents/events` - Subscribe to subagent SSE events

## Testing

```bash
# Run all tests
cd backend
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=term-missing

# Frontend static checks
cd ../frontend
npx tsc --noEmit
npm run lint
```

## Deployment

See [docs/infrastructure/deployment-runbook.md](docs/infrastructure/deployment-runbook.md) for detailed deployment instructions.

## License

MIT
