# 问津 Wenjin

> 向研究深处问津。
> 面向论文、申报、专利与项目写作的 AI 工作台。

Find the way, move the work forward.

Wenjin is an AI-powered academic workspace that supports thesis, SCI paper, research proposal, software copyright, and patent workflows through a unified Lead Agent + Middleware + Skill architecture.

## Core Features

### Workspace Types
- **学位论文** (Thesis) — Literature research, outline design, chapter writing, figure generation, compilation & export
- **学术论文** (SCI/EI) — Literature search, paper analysis, section writing, peer review simulation, journal recommendation
- **研究计划** (Proposal) — Background research, experiment design, proposal writing
- **软件著作权** (Software Copyright) — Copyright materials, technical documentation
- **专利申请** (Patent) — Patent drafting, prior art search

### AI Architecture
- **Lead Agent** — Conversational AI with type-specific Chinese system prompts per workspace type
- **21 Skills** — Each with a guidance prompt for conversational parameter collection; served from backend API
- **17 Middlewares** — In strict pipeline order: thread data → uploads → sandbox → memory → discipline norms → workspace context → clarification → tool execution
- **Single Thread Model** — One workspace = one persistent conversation. SummarizationMiddleware compresses at 80k tokens, MemoryMiddleware extracts long-term knowledge facts
- **Template System** — Upload school/journal/fund templates (.docx, .tex, .txt, .md) that influence the full writing pipeline via LLM-parsed structure + format specs
- **Subagent Delegation** — Complex multi-step features dispatched as background Celery tasks with SSE progress streaming

### Frontend
- **Dashboard** — Hero guidance area with smart stage-based recommendations (no artifacts → research, has outline → writing, etc.)
- **Chat Panel** — Collapsible one-line status bar (stage + skill + artifact count + next action), expands to full detail
- **Sidebar** — Workspace info + 5-stage stepper + single chat entry point
- **Markdown Rendering** — Assistant messages rendered with react-markdown + remark-gfm, including code blocks, tables, and lists
- **Streaming** — Real-time SSE streaming with live markdown rendering
- **Workspace Inspector** — Artifact timeline, literature library, activity log, template management

## Tech Stack

### Backend
- Python 3.12+
- FastAPI + Uvicorn
- SQLAlchemy 2.0 (async) + PostgreSQL 16 + pgvector
- Redis 7 (caching, pub/sub, task queue)
- LangGraph / LangChain
- Celery (background task workers)

### Frontend
- Next.js 16 (App Router)
- React 19
- TypeScript
- TailwindCSS
- Framer Motion
- Zustand
- react-markdown + remark-gfm

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
cd <repo-dir>

# Create a local backend env file (not tracked)
cp backend/.env.example backend/.env
# Edit backend/.env with your LLM provider keys and DB settings

# (Optional, for mainland China network) use Docker mirror env
cp .env.docker-cn.example .env

# Start all services
docker compose up -d --build

# Verify migration completed
docker compose logs -f migrate
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

# Worker (in another terminal)
cd backend
uv run celery -A src.task.celery_app worker --loglevel=info

# Frontend setup (in another terminal)
cd frontend
npm install
npm run dev
```

## Project Structure

```
repo-root/
├── backend/
│   ├── src/
│   │   ├── gateway/                # FastAPI gateway + routers
│   │   ├── agents/
│   │   │   ├── lead_agent/         # Main conversational agent + skill catalog
│   │   │   ├── middlewares/        # 17-stage middleware pipeline
│   │   │   └── workspace_lead_agent.py  # Workspace feature execution agent
│   │   ├── academic/               # Academic services and tools
│   │   ├── database/               # SQLAlchemy models
│   │   ├── models/                 # LLM factory and routing
│   │   ├── services/               # Auth, memory, template, knowledge services
│   │   ├── task/                   # Celery task framework
│   │   └── workspace_features/     # Feature registry and execution graphs
│   ├── alembic/                    # Database migrations
│   └── pyproject.toml
├── frontend/
│   ├── app/
│   │   ├── (workbench)/workspaces/[id]/  # Workspace dashboard + chat + inspector
│   │   └── workspaces/             # Workspace list and creation
│   ├── components/                 # Shared UI components
│   ├── lib/                        # API client, icon map, feature routes, entry prompts
│   └── stores/                     # Zustand stores (chat, workspace, features, task)
├── docs/
│   ├── architecture/               # Architecture decisions and API maps
│   ├── infrastructure/             # Deployment and operations runbooks
│   ├── plans/                      # Feature design and implementation plans
│   └── product/                    # Product capability and contract docs
├── docker-compose.yml
└── nginx.conf
```

## API Reference

### Authentication
- `POST /api/auth/register` — Register new user
- `POST /api/auth/login` — Login and get tokens
- `POST /api/auth/refresh` — Refresh access token
- `GET /api/auth/me` — Get current user info

### Workspaces
- `GET /api/workspaces` — List user workspaces
- `POST /api/workspaces` — Create workspace
- `GET /api/workspaces/{id}` — Get workspace details
- `PUT /api/workspaces/{id}` — Update workspace
- `DELETE /api/workspaces/{id}` — Delete workspace

### Chat
- `POST /api/chat/stream` — Streaming chat (SSE)
- `GET /api/threads` — List threads for workspace
- `GET /api/threads/{id}` — Get thread with messages
- `DELETE /api/threads/{id}` — Delete thread

Notes:
- Each workspace uses a single persistent thread. The frontend resolves the first existing thread or starts a new one.
- Skill selection is persisted at the thread level.
- Feature entry routes converge on `/workspaces/{id}/chat` with optional `?feature=xxx&skill=yyy` params.

### Workspace Features & Skills
- `GET /api/workspaces/{workspace_id}/features` — List features for workspace type
- `POST /api/workspaces/{workspace_id}/features/{feature_id}/execute` — Execute a feature
- `GET /api/workspaces/{workspace_id}/skills` — List skills with guidance prompts

### Papers
- `GET /api/papers` — List papers in owned workspaces
- `POST /api/papers/upload` — Upload PDF (`workspace_id` required)
- `POST /api/papers/search` — Search papers
- `POST /api/papers/{id}/extract` — Trigger extraction task

### Artifacts
- `GET /api/workspaces/{workspace_id}/artifacts` — List artifacts
- `POST /api/workspaces/{workspace_id}/artifacts` — Create artifact
- `GET /api/workspaces/{workspace_id}/artifacts/{id}` — Get artifact
- `PUT /api/workspaces/{workspace_id}/artifacts/{id}` — Update artifact
- `DELETE /api/workspaces/{workspace_id}/artifacts/{id}` — Delete artifact
- `GET /api/workspaces/{workspace_id}/artifacts/{id}/lineage` — Artifact lineage

### Templates
- `POST /api/workspaces/{workspace_id}/templates/upload` — Upload and parse template file
- `GET /api/workspaces/{workspace_id}/templates` — List workspace templates
- `GET /api/workspaces/{workspace_id}/templates/active` — Get active template
- `PUT /api/workspaces/{workspace_id}/templates/{id}/activate` — Activate a template
- `DELETE /api/workspaces/{workspace_id}/templates/{id}` — Delete template

### Tasks
- `GET /api/tasks/{id}` — Get task status
- `GET /api/tasks/{id}/stream` — Subscribe to task progress (SSE)
- `GET /api/workspaces/{workspace_id}/events` — Workspace event stream (SSE)

### Subagents
- `POST /api/subagents/threads/{thread_id}/spawn` — Spawn subagent task
- `GET /api/subagents/threads/{thread_id}/tasks/{task_id}/status` — Get status
- `POST /api/subagents/threads/{thread_id}/tasks/{task_id}/cancel` — Cancel task

## Testing

```bash
# Backend tests
cd backend
uv run pytest

# With coverage
uv run pytest --cov=src --cov-report=term-missing

# Frontend static checks
cd frontend
npx tsc --noEmit
npm run lint
npx next build
```

## Deployment

See [docs/infrastructure/deployment-runbook.md](docs/infrastructure/deployment-runbook.md) for detailed deployment instructions.

## License

MIT
