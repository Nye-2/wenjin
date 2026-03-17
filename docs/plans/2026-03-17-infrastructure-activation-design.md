# Infrastructure Activation Design

Date: 2026-03-17
Status: Approved

## 1. Background

Phase 3 review (2026-03-16) identified six pieces of idle infrastructure in the AcademiaGPT-V2 backend. This document describes a three-sprint plan to activate all of them.

### Idle Infrastructure Inventory

| Infrastructure | Code Completeness | Runtime Status | Action Required |
|---------------|-------------------|---------------|-----------------|
| Celery Task Execution | Complete (queues/worker/task defs) | CELERY_ENABLED=false, submit_task has no fallback | Fix fallback + enable |
| Redis Caches | 9 advanced cache functions defined | Core features in use (progress/idempotency/SSE), advanced caches (RAG/Agent/Lock/Queue) idle | Wire up callers |
| pgvector / RAG | DB table + extension ready, source deleted | Only .pyc remnants, needs rebuild | Enhance existing TOC-based retrieval instead |
| Rate Limiting | Complete implementation (Redis + memory backends) | Middleware not registered in app.py | One-line registration |
| Prometheus | Config class only | No collection code/endpoint/container | Install SDK + implement middleware + deploy container |
| Sentry | Config class only | No SDK install/init | Install SDK + init + integrate error handling |

### Strategy

**Approach A (risk-descending)** was selected:
- Sprint 1: Fix core runtime (Celery fallback + Rate Limiting)
- Sprint 2: Production observability (Sentry + Prometheus + Redis cache wiring)
- Sprint 3: Literature retrieval enhancement (LLM + TOC retrieval augmentation)

### Deployment Environment

Docker Compose single-machine deployment.

---

## 2. Sprint 1: Celery Dual-Mode Executor + Rate Limiting Activation

### 2.1 Celery Dual-Mode Executor

**Problem:** `TaskService.submit_task()` unconditionally calls `celery_app.send_task()`. When broker is unavailable, this throws a 500 error. When broker is available but no worker is running, tasks stay PENDING forever. There is no fallback execution mechanism.

**Solution:** Introduce a Dual-Mode Executor abstraction.

```
CELERY_ENABLED=true  -> Celery queue (existing logic)
CELERY_ENABLED=false -> asyncio in-process execution (new)
```

#### New File: `src/task/executor.py`

```python
class TaskExecutor(Protocol):
    async def execute(self, task_id: str, task_type: str, payload: dict) -> None: ...

class CeleryExecutor:
    """Wraps existing celery_app.send_task() call."""
    async def execute(self, task_id, task_type, payload):
        celery_app.send_task(...)  # existing logic

class LocalExecutor:
    """Runs tasks in-process via asyncio.create_task()."""
    _semaphore: asyncio.Semaphore  # default concurrency limit: 3

    async def execute(self, task_id, task_type, payload):
        asyncio.create_task(self._run(task_id, task_type, payload))

    async def _run(self, task_id, task_type, payload):
        # Reuses _execute_task_async() from src/task/tasks/base.py
        # Reports progress via ProgressTracker (SSE chain unchanged)
        # Catches exceptions -> marks task FAILED + pushes error via ProgressTracker

def get_executor() -> TaskExecutor:
    if celery_settings.enabled:
        return CeleryExecutor()
    return LocalExecutor()
```

#### Modified File: `src/task/service.py`

- `submit_task()` calls `get_executor().execute()` instead of `celery_app.send_task()` directly.
- Frontend interaction unchanged: immediate task_id return -> SSE progress stream.

#### LocalExecutor Design Notes

- In-process execution, no worker-level isolation. Suitable for dev/test/low-traffic.
- `asyncio.Semaphore(3)` controls max concurrent tasks.
- Exception capture -> update task status to FAILED + push via ProgressTracker.

### 2.2 Rate Limiting Activation

Minimal changes required — the middleware is fully implemented.

1. **`src/gateway/middleware/__init__.py`**: Export `setup_rate_limiting`.
2. **`src/gateway/app.py`**: Call `setup_rate_limiting(app)` in middleware registration section.
3. Default config: 30 requests / 60-second window (already defined in `RedisSettings`).
4. Redis available -> Redis sliding window; Redis unavailable -> memory fallback (already implemented).

### 2.3 Sprint 1 Verification Criteria

- `CELERY_ENABLED=false`: submit task -> progress events -> task completes (no broker dependency)
- `CELERY_ENABLED=true`: existing behavior unchanged
- Rate Limiting: 30+ rapid requests -> 429 response
- All existing 122+ tests pass

---

## 3. Sprint 2: Observability Stack (Sentry + Prometheus + Redis Cache Wiring)

### 3.1 Sentry Error Monitoring

#### New Dependency

`pyproject.toml`: add `sentry-sdk[fastapi]`

#### New File: `src/observability/sentry.py`

```python
def init_sentry() -> None:
    settings = get_sentry_settings()
    if not settings.enabled or not settings.dsn:
        return
    sentry_sdk.init(
        dsn=settings.dsn,
        environment=settings.environment,
        traces_sample_rate=settings.traces_sample_rate,
        profiles_sample_rate=settings.profiles_sample_rate,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
            RedisIntegration(),
        ],
    )
```

#### Integration Points

- **`src/gateway/app.py`**: Call `init_sentry()` in lifespan startup.
- **`src/gateway/middleware/error_handler.py`**: Add `sentry_sdk.capture_exception(exc)` in `generic_exception_handler`.
- **`src/gateway/middleware/correlation.py`**: Set `correlation_id` as Sentry tag in scope.

### 3.2 Prometheus Metrics

#### New Dependency

`pyproject.toml`: add `prometheus-client` (currently only indirect via flower).

#### New File: `src/observability/prometheus.py`

Core metrics:
- `http_requests_total` (Counter) — labels: method, path, status
- `http_request_duration_seconds` (Histogram) — request latency
- `active_tasks_total` (Gauge) — currently running tasks
- `task_duration_seconds` (Histogram) — task execution duration

```python
def setup_prometheus(app: FastAPI) -> None:
    if not prometheus_settings.enabled:
        return
    # Register HTTP metrics middleware
    # Mount /metrics endpoint (prometheus_client ASGI app)
```

#### Task Metrics Integration

- `TaskExecutor.execute()` updates `active_tasks_total` gauge and records `task_duration_seconds`.

#### Docker Compose Additions

```yaml
prometheus:
  image: prom/prometheus:latest
  volumes:
    - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
  ports:
    - "9090:9090"

grafana:
  image: grafana/grafana:latest
  volumes:
    - ./monitoring/grafana/provisioning:/etc/grafana/provisioning
  ports:
    - "3001:3000"
```

Provide base dashboard JSON: HTTP QPS + error rate + task metrics.

### 3.3 Redis Cache Wiring

| Cache Function | Integration Point | Notes |
|---------------|-------------------|-------|
| `workspace_lock()` | `feature_execution_handler.py` | Replace optimistic lock with distributed mutex |
| `set/get_agent_status()` | `tasks/base.py` task execution | Agent thread-level status queries |
| `enqueue/dequeue_extraction()` | `extraction_service.py` Tier2 | Redis queue for Tier2 PDF extraction tasks |
| `get/set_rag_cache()` | Sprint 3 search cache | Wired with Sprint 3 search_workspace() |
| `append_sse_event()` / `get_sse_buffer()` | **Do not wire** | Superseded by Pub/Sub; mark deprecated or delete |

### 3.4 Sprint 2 Verification Criteria

- Sentry: trigger exception -> visible in Sentry dashboard (requires real DSN)
- Prometheus: GET `/metrics` returns metrics -> Grafana dashboard renders
- Redis cache: workspace_lock blocks concurrent duplicate task submission
- All existing tests pass

---

## 4. Sprint 3: LLM + TOC Retrieval Enhancement

### 4.1 Design Rationale

The existing retrieval architecture uses LLM as the "intelligent retriever" — the Agent reads paper TOCs and decides which sections to fetch. This approach is preserved and enhanced rather than replaced with vector embeddings.

Identified gaps:
1. Tier 2 extraction is a placeholder (section_summaries, key_concepts, entities all empty)
2. No cross-paper search within a workspace
3. Section matching requires exact title match
4. No content caching
5. TOC entries lack word count, page range, and summaries

### 4.2 Module Designs

#### A. Tier 2 Extraction Implementation — `extraction_service.py`

Fill the three placeholder fields in `PaperExtraction.structured_data`:

- **`section_summaries`**: Call LLM (Claude Haiku / Qwen-Turbo) per section to generate 2-3 sentence summary.
  - Input: section content (truncated to 4000 chars)
  - Output: `{section_path: summary_text}` dict
  - Stored in `PaperExtraction.structured_data.section_summaries`
- **`key_concepts`**: Extract 10-20 key terms/concepts from full text.
- **`entities`**: Extract method names, datasets, baseline models, and other academic entities.

Trigger: async execution after paper upload (via Sprint 1 TaskExecutor).

#### B. Enriched TOC Information — `tools.py` `list_papers()`

Modify `list_papers()` return format from:
```python
{"title": "3. Methodology", "level": 1}
```
to:
```python
{
  "title": "3. Methodology",
  "level": 1,
  "page_range": "12-18",
  "word_count": 2340,
  "summary": "This chapter proposes a Transformer-based multimodal fusion method..."
}
```

Agent can now judge whether to deep-read a section based on summary + word count + page range.

#### C. Fuzzy Section Matching — `section_loader.py`

Current `find_entry(section_title)` requires exact match. Enhanced to:

1. Exact match first
2. On failure, use `difflib.get_close_matches()` with threshold 0.6
3. Support `section_path` (e.g., "3.2.1") lookup, not just title

#### D. Workspace Full-Text Search — New `search_workspace()` Tool

Leverages existing `PaperSection` table with PostgreSQL full-text search:

```python
@tool
async def search_workspace(query: str, workspace_id: str, limit: int = 10) -> list[dict]:
    """Search section content across all papers in a workspace."""
    # Uses PostgreSQL ts_vector + ts_query
    # Returns: [{paper_title, section_title, snippet, relevance_score}]
```

- No vector embeddings needed — uses PostgreSQL `to_tsvector('simple', content)` + `ts_rank()`
- Requires GIN index on `paper_sections.content`
- Supports Chinese + English mixed search (using `'simple'` config)

#### E. Redis Cache Layer

Wire Sprint 2 Redis caches:

- `get_section()` results cached in Redis (key: `section:{paper_id}:{section_path}`, TTL: 1 hour)
- `list_papers()` TOC summary cached (key: `toc_summary:{workspace_id}`, TTL: 10 minutes)
- Cache invalidation on paper update/re-extraction

#### F. Alembic Migration

Add GIN full-text search index:
```sql
CREATE INDEX ix_paper_sections_content_fts
ON paper_sections USING gin(to_tsvector('simple', content));
```

### 4.3 Out of Scope

- No vector embeddings introduced (LLM remains the "intelligent retriever")
- `paper_chunks.embedding` column preserved but not activated
- No LangGraph graph structure changes (only new tools added)

### 4.4 Sprint 3 Verification Criteria

- Tier 2 extraction: upload paper -> `section_summaries` non-empty -> `list_papers` returns summaries
- Fuzzy matching: `get_section("Methodology")` matches `"3. Methodology and Approach"`
- Workspace search: `search_workspace("transformer", ws_id)` returns relevant section snippets
- Redis cache: same section second read hits cache
- All existing tests pass + new feature tests

---

## 5. Summary

| Sprint | Core Deliverables | Key Files |
|--------|-------------------|-----------|
| **1** | Celery dual-mode executor, Rate limiting activation | `src/task/executor.py` (new), `src/task/service.py`, `src/gateway/app.py` |
| **2** | Sentry init, Prometheus metrics + /metrics endpoint + Grafana, Redis cache wiring | `src/observability/` (new), `docker-compose.yml`, `src/gateway/app.py` |
| **3** | Tier 2 extraction impl, enriched TOC, fuzzy section match, workspace search, Redis caching | `src/academic/services/extraction_service.py`, `src/academic/literature/tools.py`, `src/academic/literature/navigation/` |
