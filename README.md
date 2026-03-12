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
- Health Check Endpoint - System health monitoring

### Quality Assurance
- API Integration Tests - Comprehensive endpoint testing
- Input Validation - Request validation using Pydantic
- Error Handling - Centralized error handling middleware
- **790+ Tests Passing** - Comprehensive test coverage

## Tech Stack

### Backend
- Python 3.12+
- FastAPI
- SQLAlchemy 2.0 (async)
- PostgreSQL + pgvector
- Redis
- LangGraph / LangChain

### Frontend
- Next.js 15
- TypeScript
- TailwindCSS
- Zustand
- React Query

## Quick Start

### Prerequisites
- Docker and Docker Compose
- PostgreSQL 15+ with pgvector
- Redis 7.0+
- OpenAI API key

### Using Docker Compose

```bash
# Clone the repository
git clone <repository-url>
cd academiagpt-v2

# Copy environment files
cp .env.example .env
# Edit .env with your API keys

# Start all services
docker-compose up -d

# Run database migrations
docker-compose exec backend uv run alembic upgrade head
```

### Manual Setup

```bash
# Backend setup
cd backend
uv sync --extra dev
cp .env.example .env
# Edit .env with your settings
uv run alembic upgrade head
uv run uvicorn src.gateway.app:app --reload --port 8001

# Frontend setup (in another terminal)
cd frontend
npm install
cp .env.example .env.local
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
│   ├── deployment.md     # Deployment guide
│   └── plans/            # Implementation plans
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
- `GET /api/papers` - List papers
- `POST /api/papers` - Create paper
- `GET /api/papers/{id}` - Get paper details
- `POST /api/papers/{id}/extract` - Trigger extraction
- `POST /api/papers/search` - Search papers

### Artifacts
- `GET /api/artifacts` - List artifacts
- `POST /api/artifacts` - Create artifact
- `GET /api/artifacts/{id}` - Get artifact
- `GET /api/artifacts/{id}/lineage` - Get artifact lineage

### Chat
- `POST /api/threads` - Create chat thread
- `POST /api/chat` - Send message
- `POST /api/chat/stream` - Streaming chat

## Testing

```bash
# Run all tests
cd backend
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=term-missing
```

## Deployment

See [docs/deployment.md](docs/deployment.md) for detailed deployment instructions.

## License

MIT
