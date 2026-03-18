# AcademiaGPT v2 Deployment Guide

This guide covers deploying AcademiaGPT v2 in production environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Variables](#environment-variables)
3. [Docker Compose Deployment](#docker-compose-deployment)
4. [Manual Deployment](#manual-deployment)
5. [Database Migrations](#database-migrations)
6. [Production Configuration](#production-configuration)
7. [Monitoring and Logging](#monitoring-and-logging)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

- Docker 24.0+
- Docker Compose 2.0+
- PostgreSQL 15+ with pgvector extension
- Redis 7.0+

### Required API Keys

- OpenAI API key (for GPT-4 models)
- Anthropic API key (for Claude models)
- Semantic Scholar API key (optional, for enhanced rate limits)

### Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 2 cores | 4+ cores |
| RAM | 4 GB | 8+ GB |
| Storage | 20 GB | 50+ GB SSD |

---

## Environment Variables

### Backend Service

Create a `.env` file in the `backend/` directory:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@postgres:5432/academiagpt

# Redis
REDIS_URL=redis://redis:6379/0

# Authentication
JWT_SECRET_KEY=your-super-secret-key-change-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# LLM Providers
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Academic APIs (optional)
SEMANTIC_SCHOLAR_API_KEY=...

# Application
APP_ENV=production
DEBUG=false
LOG_LEVEL=INFO
```

### Frontend Service

Create a `.env.local` file in the `frontend/` directory:

```bash
# If frontend and gateway are on different ports (local dev):
NEXT_PUBLIC_API_URL=http://localhost:8001

# If frontend is behind Nginx reverse proxy (recommended):
# NEXT_PUBLIC_API_URL=/api
```

---

## Docker Compose Deployment

### Quick Start

1. Clone the repository:
   ```bash
   git clone https://github.com/your-org/academiagpt-v2.git
   cd academiagpt-v2
   ```

2. Create environment files:
   ```bash
   cp backend/.env.example backend/.env
   # Edit backend/.env with your values
   ```

3. Start all services:
   ```bash
   docker-compose up -d
   ```

4. Run database migrations:
   ```bash
   docker-compose exec backend uv run alembic upgrade head
   ```

5. Access the application:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8001
   - API Docs: http://localhost:8001/docs

### Docker Compose Configuration

The included `docker-compose.yml` includes:

- **nginx**: Reverse proxy on port 80
- **frontend**: Next.js application
- **backend**: FastAPI application on port 8001
- **postgres**: PostgreSQL with pgvector
- **redis**: Redis for caching and sessions

---

## Manual Deployment

### Backend Setup

1. Install Python 3.12+ and uv package manager:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Clone and setup:
   ```bash
   cd backend
   uv sync
   ```

3. Configure environment:
   ```bash
   cp .env.example .env
   # Edit .env with production values
   ```

4. Run migrations:
   ```bash
   uv run alembic upgrade head
   ```

5. Start the server:
   ```bash
   # Gateway API
   uv run uvicorn src.gateway.app:app --host 0.0.0.0 --port 8001

   # LangGraph Server (optional, for agent workflows)
   uv run langgraph dev --port 2024
   ```

### Frontend Setup

1. Install Node.js 20+:
   ```bash
   # Using nvm
   nvm install 20
   nvm use 20
   ```

2. Setup:
   ```bash
   cd frontend
   npm install
   ```

3. Build for production:
   ```bash
   npm run build
   ```

4. Start:
   ```bash
   npm run start
   ```

---

## Database Migrations

### Creating a Migration

```bash
cd backend
uv run alembic revision --autogenerate -m "Description of changes"
```

### Applying Migrations

```bash
# Apply all pending migrations
uv run alembic upgrade head

# Rollback one migration
uv run alembic downgrade -1

# View migration history
uv run alembic history
```

### Production Database Setup

Ensure PostgreSQL has the pgvector extension:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

---

## Production Configuration

### Nginx Configuration

The included `nginx.conf` provides:
- SSL/TLS termination (configure your certificates)
- Reverse proxy to frontend and backend
- WebSocket support for streaming chat
- Static file caching

### Security Recommendations

1. **Enable HTTPS**: Configure SSL certificates in nginx
2. **Secure JWT Secret**: Use a strong, unique secret key
3. **Database Security**:
   - Use strong passwords
   - Limit network access
   - Enable SSL connections
4. **Redis Security**: Require authentication
5. **Rate Limiting**: Configure nginx rate limiting

### Environment-Specific Settings

| Setting | Development | Production |
|---------|-------------|------------|
| DEBUG | true | false |
| LOG_LEVEL | DEBUG | INFO |
| CORS Origins | * | your-domain.com |
| Token Expiry | Longer | Shorter |

---

## Monitoring and Logging

### Health Checks

- Backend: `GET /health` returns `{"status": "healthy", "version": "2.0.0"}`
- Database: Check PostgreSQL connection
- Redis: Check Redis connection

### Logging

Logs are written to stdout/stderr. Configure your log aggregation:

```yaml
# docker-compose.yml logging configuration
services:
  backend:
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

### Metrics Collection

Consider adding:
- Prometheus metrics endpoint
- OpenTelemetry tracing
- APM tool integration

---

## Troubleshooting

### Common Issues

#### Database Connection Errors

```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Check connection string
echo $DATABASE_URL

# Test connection
uv run python -c "from src.database import *; print('OK')"
```

#### Redis Connection Errors

```bash
# Check Redis is running
docker-compose ps redis

# Test connection
redis-cli ping
```

#### Migration Failures

```bash
# Check current revision
uv run alembic current

# Stamp to specific revision
uv run alembic stamp head
```

#### Frontend Build Errors

```bash
# Clear Next.js cache
rm -rf frontend/.next

# Rebuild
cd frontend && npm run build
```

### Getting Help

1. Check logs: `docker-compose logs -f backend`
2. Check health endpoint: `curl http://localhost:8001/health`
3. Review environment variables
4. Open an issue on GitHub

---

## Architecture Overview

```
                    ┌─────────────┐
                    │   Nginx     │
                    │   (:80)     │
                    └──────┬──────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │ Frontend │    │ Backend  │    │ LangGraph│
    │ (Next.js)│    │ (FastAPI)│    │ (Agent)  │
    └────┬─────┘    └────┬─────┘    └────┬─────┘
         │               │               │
         │    ┌──────────┼──────────┐    │
         │    │          │          │    │
         ▼    ▼          ▼          ▼    ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │  Redis   │   │ PostgreSQL│   │ LLM APIs │
    │ (Cache)  │   │ (Data)    │   │(OpenAI/  │
    └──────────┘   └──────────┘   │ Anthropic)│
                                  └──────────┘
```

---

## Next Steps

After deployment:

1. Create an admin user account
2. Configure workspace types and disciplines
3. Set up backup schedules for PostgreSQL
4. Configure monitoring and alerting
5. Review and adjust rate limits
6. Set up CI/CD pipelines for updates
