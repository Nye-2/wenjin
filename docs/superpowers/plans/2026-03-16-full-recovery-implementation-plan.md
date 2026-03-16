# AcademiaGPT-V2 Full Recovery (Phase 1 + Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不重写主架构的前提下，完整恢复 Thesis 功能闭环并收敛计费/任务治理，达到“可执行、可追踪、可治理”的生产可用状态。

**Architecture:** 采用两阶段推进。Phase 1 聚焦用户可见功能恢复（写作、图表、导入、上传）；Phase 2 聚焦治理收口（计费单源、幂等、任务一致性、失败态语义）。全程遵循 `@superpowers/test-driven-development`：先写失败测试，再做最小实现，最后回归。

**Tech Stack:** FastAPI, SQLAlchemy Async, Celery, Redis, Next.js 15, TypeScript, Zustand, Pytest.

---

## File Structure

### Backend (Create)

- `backend/src/workspace_features/services/thesis_writing_service.py`
  - Thesis 大纲/章节生成服务，统一 `generation_mode` 与 `schema_version`。
- `backend/src/execution/providers/mermaid.py`
  - Mermaid 图表执行 provider。
- `backend/src/services/feature_credit_policy.py`
  - 计费与可计费 task 阻断规则的单一真源。
- `backend/src/academic/services/paper_upload_service.py`
  - 上传文件保存与元信息标准化输出。

### Backend (Modify)

- `backend/src/task/handlers/workspace_feature_handler.py`
  - 使用 `thesis_writing_service` 替换模板化写作路径。
- `backend/src/thesis/workflow/nodes/section_writer.py`
  - 生成可完成状态章节内容，避免仅 `writing` 标记。
- `backend/src/execution/service.py`
  - 注册 MermaidProvider。
- `backend/src/gateway/routers/academic.py`
  - 实现 `/papers/upload` 最小可用。
- `backend/src/gateway/routers/tasks.py`
  - 引用集中 policy 判定直投阻断。
- `backend/src/services/credit_service.py`
  - 引用集中 policy 计算 cost。
- `backend/src/gateway/routers/features.py`
  - 增加 execute 幂等保护。
- `backend/src/task/service.py`
  - 队列失败状态落库（`failed(queue_submit_failed)`）。
- `backend/src/services/dashboard_service.py`
  - 模块状态枚举增加 `failed`。

### Frontend (Modify)

- `frontend/app/(workbench)/workspaces/[id]/thesis-writing/page.tsx`
  - 展示章节正文（artifact markdown）和可读内容区域。
- `frontend/stores/thesis-writing.ts`
  - 增加章节内容存储字段。
- `frontend/app/(workbench)/workspaces/[id]/literature/page.tsx`
  - 增加 Deep Research 导入入口。
- `frontend/app/(workbench)/workspaces/[id]/components/ModuleCard.tsx`
  - 新增 `failed` 状态文案/样式。

### Tests (Create/Modify)

- Create: `backend/tests/workspace_features/services/test_thesis_writing_service.py`
- Create: `backend/tests/execution/providers/test_mermaid_provider.py`
- Create: `backend/tests/services/test_feature_credit_policy.py`
- Create: `backend/tests/task/test_task_service_submission_failures.py`
- Modify: `backend/tests/task/test_workspace_feature_handler.py`
- Modify: `backend/tests/gateway/routers/test_features.py`
- Modify: `backend/tests/services/test_dashboard_service.py`
- Modify: `backend/tests/gateway/routers/test_academic.py`

---

## Chunk 1: Phase 1 Functional Recovery

### Task 1: Thesis 写作服务化（outline/chapter）

**Files:**
- Create: `backend/src/workspace_features/services/thesis_writing_service.py`
- Modify: `backend/src/workspace_features/services/__init__.py`
- Modify: `backend/src/task/handlers/workspace_feature_handler.py`
- Test: `backend/tests/workspace_features/services/test_thesis_writing_service.py`
- Test: `backend/tests/task/test_workspace_feature_handler.py`

- [ ] **Step 1: 写失败测试（service 层）**

```python
def test_build_outline_payload_returns_v1_schema():
    payload = build_outline_payload(
        paper_title="测试论文",
        target_words=20000,
        literature_count=12,
        deep_research_artifact_ids=["a1", "a2"],
    )
    assert payload["schema_version"] == "v1"
    assert payload["generation_mode"] in {"llm", "template_fallback"}
    assert payload["outline"]["chapters"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/workspace_features/services/test_thesis_writing_service.py -v`
Expected: FAIL（模块或函数不存在）

- [ ] **Step 3: 最小实现 service + handler 接入**

```python
# thesis_writing_service.py

def build_outline_payload(...):
    return {
        "paper_title": paper_title,
        "outline": normalized_outline,
        "generation_mode": generation_mode,
        "source_context": {
            "literature_count": literature_count,
            "deep_research_artifact_ids": deep_research_artifact_ids,
        },
        "schema_version": "v1",
    }
```

- [ ] **Step 4: 运行定向测试确认通过**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/workspace_features/services/test_thesis_writing_service.py tests/task/test_workspace_feature_handler.py -v -k "outline or chapter"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /home/cjz/AcademiaGPT-V2 add \
  backend/src/workspace_features/services/thesis_writing_service.py \
  backend/src/workspace_features/services/__init__.py \
  backend/src/task/handlers/workspace_feature_handler.py \
  backend/tests/workspace_features/services/test_thesis_writing_service.py \
  backend/tests/task/test_workspace_feature_handler.py
git -C /home/cjz/AcademiaGPT-V2 commit -m "feat(thesis): service-ize outline and chapter payload generation"
```

### Task 2: 修复 write_all 路径章节完成语义

**Files:**
- Modify: `backend/src/thesis/workflow/nodes/section_writer.py`
- Test: `backend/tests/thesis/workflow/nodes/test_section_writer.py`
- Test: `backend/tests/thesis/workflow/test_graph.py`

- [ ] **Step 1: 写失败测试（章节应可 completed）**

```python
def test_section_writer_marks_section_completed_with_content(sample_state):
    result = section_writer_node(sample_state)
    section = result["sections"][0]
    assert section.status == "completed"
    assert section.content
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/thesis/workflow/nodes/test_section_writer.py::test_section_writer_marks_section_completed_with_content -v`
Expected: FAIL（当前为 writing + 空内容）

- [ ] **Step 3: 最小实现完成状态章节内容**

```python
# section_writer_node minimal behavior
completed_section = SectionContent(
    index=next_idx,
    title=...,
    content=generated_markdown,
    status="completed",
    word_count=len(generated_markdown),
)
return {"sections": [completed_section], "current_phase": "writing", ...}
```

- [ ] **Step 4: 运行 workflow 相关测试**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/thesis/workflow/nodes/test_section_writer.py tests/thesis/workflow/test_graph.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /home/cjz/AcademiaGPT-V2 add \
  backend/src/thesis/workflow/nodes/section_writer.py \
  backend/tests/thesis/workflow/nodes/test_section_writer.py \
  backend/tests/thesis/workflow/test_graph.py
git -C /home/cjz/AcademiaGPT-V2 commit -m "fix(thesis-workflow): complete section output in write_all path"
```

### Task 3: Thesis 写作前端展示章节正文

**Files:**
- Modify: `frontend/stores/thesis-writing.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/thesis-writing/page.tsx`

- [ ] **Step 1: 添加 store 状态字段与类型（先写 TS 断言）**

```ts
interface ChapterStatus {
  content?: string;
}
```

- [ ] **Step 2: 运行类型检查确认失败**

Run: `cd /home/cjz/AcademiaGPT-V2/frontend && npx tsc --noEmit`
Expected: FAIL（引用新字段但未实现更新逻辑）

- [ ] **Step 3: 最小实现章节内容装载**

```ts
updateChapterStatus(index, status, words, content?)
```

- [ ] **Step 4: 再次运行类型检查**

Run: `cd /home/cjz/AcademiaGPT-V2/frontend && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /home/cjz/AcademiaGPT-V2 add \
  frontend/stores/thesis-writing.ts \
  frontend/app/\(workbench\)/workspaces/\[id\]/thesis-writing/page.tsx
git -C /home/cjz/AcademiaGPT-V2 commit -m "feat(frontend): render chapter markdown in thesis writing workspace"
```

### Task 4: MermaidProvider 实现与注册

**Files:**
- Create: `backend/src/execution/providers/mermaid.py`
- Modify: `backend/src/execution/providers/__init__.py`
- Modify: `backend/src/execution/service.py`
- Test: `backend/tests/execution/providers/test_mermaid_provider.py`

- [ ] **Step 1: 写失败测试（provider contract）**

```python
@pytest.mark.asyncio
async def test_mermaid_provider_generates_svg(tmp_path):
    provider = MermaidProvider()
    result = await provider.execute("graph TD; A-->B", str(tmp_path), {})
    assert result.success is True
    assert result.output_files
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/execution/providers/test_mermaid_provider.py -v`
Expected: FAIL（provider 不存在）

- [ ] **Step 3: 实现 provider + service 注册**

```python
class MermaidProvider(BaseExecutionProvider):
    docker_image = "minlag/mermaid-cli:latest"
    def build_command(...):
        return ["mmdc", "-i", "/workspace/input.mmd", "-o", "/workspace/output/diagram.svg"]
```

- [ ] **Step 4: 运行 provider 与 thesis 图表相关测试**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/execution/providers/test_mermaid_provider.py tests/task/test_thesis_handlers.py -v -k "figure or mermaid"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /home/cjz/AcademiaGPT-V2 add \
  backend/src/execution/providers/mermaid.py \
  backend/src/execution/providers/__init__.py \
  backend/src/execution/service.py \
  backend/tests/execution/providers/test_mermaid_provider.py
git -C /home/cjz/AcademiaGPT-V2 commit -m "feat(execution): add MermaidProvider and register mermaid execution type"
```

### Task 5: Literature 页面接通 Deep Research 导入

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/literature/page.tsx`
- Modify: `frontend/stores/literature.ts` (如需参数校验增强)

- [ ] **Step 1: 先补 UI 触发逻辑并写类型约束**

```ts
await importFromDeepResearch(workspaceId, parsedPaperIds)
```

- [ ] **Step 2: 运行类型检查确认当前失败点**

Run: `cd /home/cjz/AcademiaGPT-V2/frontend && npx tsc --noEmit`
Expected: FAIL（新 UI 状态与事件未完全连线）

- [ ] **Step 3: 完成导入入口、提示与刷新联动**

```ts
setStatus(`成功导入 ${count} 篇文献`)
await fetchLiterature(workspaceId)
```

- [ ] **Step 4: 运行类型检查**

Run: `cd /home/cjz/AcademiaGPT-V2/frontend && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /home/cjz/AcademiaGPT-V2 add \
  frontend/app/\(workbench\)/workspaces/\[id\]/literature/page.tsx \
  frontend/stores/literature.ts
git -C /home/cjz/AcademiaGPT-V2 commit -m "feat(frontend): add deep research import entry in literature page"
```

### Task 6: /papers/upload 最小可用实现

**Files:**
- Create: `backend/src/academic/services/paper_upload_service.py`
- Modify: `backend/src/gateway/routers/academic.py`
- Test: `backend/tests/gateway/routers/test_academic.py`

- [ ] **Step 1: 写失败测试（不应再是 TODO 假成功）**

```python
async def test_upload_paper_returns_saved_file_info(client, auth_headers, tmp_path):
    response = await client.post("/api/papers/upload", files={...}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["file"]["saved_path"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/gateway/routers/test_academic.py -v -k upload`
Expected: FAIL（当前返回结构不符合）

- [ ] **Step 3: 实现最小保存与结构化返回**

```python
saved_path = await upload_service.save(file=file, workspace_id=workspace_id)
return {"success": True, "paper_id": None, "file": {...}, "extract": {"status": "saved"}}
```

- [ ] **Step 4: 运行 academic router 测试**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/gateway/routers/test_academic.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /home/cjz/AcademiaGPT-V2 add \
  backend/src/academic/services/paper_upload_service.py \
  backend/src/gateway/routers/academic.py \
  backend/tests/gateway/routers/test_academic.py
git -C /home/cjz/AcademiaGPT-V2 commit -m "feat(academic): implement minimal paper upload persistence and response contract"
```

---

## Chunk 2: Phase 2 Governance Recovery

### Task 7: 计费规则单一真源

**Files:**
- Create: `backend/src/services/feature_credit_policy.py`
- Modify: `backend/src/services/credit_service.py`
- Modify: `backend/src/gateway/routers/tasks.py`
- Test: `backend/tests/services/test_feature_credit_policy.py`

- [ ] **Step 1: 写失败测试（policy cost 与 billable 判定）**

```python
def test_policy_resolves_thesis_writing_actions():
    assert get_feature_cost("thesis_writing", "generate_outline") == 20
    assert is_billable_task_type("thesis_generation") is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/services/test_feature_credit_policy.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 policy 并替换读取方**

```python
# feature_credit_policy.py
FEATURE_COSTS = {...}
BILLABLE_TASK_TYPES = {...}
```

- [ ] **Step 4: 运行 credit/tasks 相关测试**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/services/test_feature_credit_policy.py tests/gateway/routers/test_tasks.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /home/cjz/AcademiaGPT-V2 add \
  backend/src/services/feature_credit_policy.py \
  backend/src/services/credit_service.py \
  backend/src/gateway/routers/tasks.py \
  backend/tests/services/test_feature_credit_policy.py
git -C /home/cjz/AcademiaGPT-V2 commit -m "refactor(credit): centralize feature credit and billable task policy"
```

### Task 8: Feature execute 幂等保护

**Files:**
- Modify: `backend/src/gateway/routers/features.py`
- Modify: `backend/src/task/store.py`
- Test: `backend/tests/gateway/routers/test_features.py`

- [ ] **Step 1: 写失败测试（重复请求应返回同一 task_id）**

```python
async def test_execute_feature_idempotent_returns_existing_task(client, auth_headers):
    first = await client.post(...)
    second = await client.post(...)
    assert second.json()["task_id"] == first.json()["task_id"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/gateway/routers/test_features.py -v -k idempotent`
Expected: FAIL

- [ ] **Step 3: 最小实现幂等键与查询复用**

```python
idempotency_key = build_idempotency_key(user_id, workspace_id, feature_id, params)
existing = await store.find_recent_pending_or_running_task(user_id, idempotency_key, window_seconds=60)
if existing:
    return ExecuteResponse(task_id=existing.id, status=existing.status, ...)
```

- [ ] **Step 4: 运行 features 路由测试**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/gateway/routers/test_features.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /home/cjz/AcademiaGPT-V2 add \
  backend/src/gateway/routers/features.py \
  backend/src/task/store.py \
  backend/tests/gateway/routers/test_features.py
git -C /home/cjz/AcademiaGPT-V2 commit -m "feat(features): add idempotency guard for execute endpoint"
```

### Task 9: Task 提交一致性修复

**Files:**
- Modify: `backend/src/task/service.py`
- Test: `backend/tests/task/test_task_service_submission_failures.py`

- [ ] **Step 1: 写失败测试（send_task 异常后应 failed）**

```python
async def test_submit_task_marks_failed_when_send_task_raises(task_service, monkeypatch):
    monkeypatch.setattr("src.task.service.celery_app.send_task", broken_send)
    with pytest.raises(RuntimeError):
        await task_service.submit_task(...)
    record = await store.get_task_record(task_id)
    assert record.status == "failed"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/task/test_task_service_submission_failures.py -v`
Expected: FAIL

- [ ] **Step 3: 最小实现失败状态落库**

```python
try:
    celery_app.send_task(...)
except Exception as exc:
    await self._store.update_task_record(task_id, status="failed", error="queue_submit_failed")
    raise
```

- [ ] **Step 4: 运行 task service 测试**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/task/test_task_service_submission_failures.py tests/task/test_task_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /home/cjz/AcademiaGPT-V2 add \
  backend/src/task/service.py \
  backend/tests/task/test_task_service_submission_failures.py
git -C /home/cjz/AcademiaGPT-V2 commit -m "fix(task): mark records failed when queue submission fails"
```

### Task 10: Dashboard 增加 failed 状态语义

**Files:**
- Modify: `backend/src/services/dashboard_service.py`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/ModuleCard.tsx`
- Test: `backend/tests/services/test_dashboard_service.py`

- [ ] **Step 1: 写失败测试（compile failure -> failed）**

```python
async def test_compile_export_status_failed_on_latest_failed_artifact(...):
    status = await service._get_compile_export_status(workspace_id)
    assert status["status"] == "failed"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/services/test_dashboard_service.py -v -k compile_export`
Expected: FAIL

- [ ] **Step 3: 最小实现后端状态与前端文案**

```ts
if (status === "failed") {
  subtitle = "最近执行失败";
}
```

- [ ] **Step 4: 回归后端 + 前端类型检查**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/services/test_dashboard_service.py -v`
Expected: PASS

Run: `cd /home/cjz/AcademiaGPT-V2/frontend && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /home/cjz/AcademiaGPT-V2 add \
  backend/src/services/dashboard_service.py \
  backend/tests/services/test_dashboard_service.py \
  frontend/app/\(workbench\)/workspaces/\[id\]/components/ModuleCard.tsx
git -C /home/cjz/AcademiaGPT-V2 commit -m "feat(dashboard): introduce failed module status and frontend rendering"
```

### Task 11: 全量回归与文档同步

**Files:**
- Modify: `docs/2026-03-13-project-status-and-next-steps.md`（更新状态差异）
- Modify: `docs/2026-03-13-credit-closure-and-p0-remediation-summary.md`（补充治理完成项）

- [ ] **Step 1: 运行后端核心回归测试集**

Run:

```bash
cd /home/cjz/AcademiaGPT-V2/backend
PYTHONPATH=. uv run pytest \
  tests/task/test_workspace_feature_handler.py \
  tests/task/test_thesis_handlers.py \
  tests/gateway/routers/test_features.py \
  tests/services/test_dashboard_service.py \
  tests/gateway/routers/test_academic.py -v
```

Expected: PASS

- [ ] **Step 2: 运行 thesis/workflow 与 execution 回归**

Run:

```bash
cd /home/cjz/AcademiaGPT-V2/backend
PYTHONPATH=. uv run pytest tests/thesis/ tests/execution/ -v
```

Expected: PASS

- [ ] **Step 3: 运行前端类型检查**

Run: `cd /home/cjz/AcademiaGPT-V2/frontend && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 4: 更新状态文档并自检**

Run:

```bash
cd /home/cjz/AcademiaGPT-V2
git diff -- docs/2026-03-13-project-status-and-next-steps.md docs/2026-03-13-credit-closure-and-p0-remediation-summary.md
```

Expected: 仅包含本次恢复范围更新

- [ ] **Step 5: Commit**

```bash
git -C /home/cjz/AcademiaGPT-V2 add \
  docs/2026-03-13-project-status-and-next-steps.md \
  docs/2026-03-13-credit-closure-and-p0-remediation-summary.md
git -C /home/cjz/AcademiaGPT-V2 commit -m "docs: sync status docs after full recovery rollout"
```

---

## 执行约束与检查点

1. 每个 Task 结束后必须跑对应最小测试，不得积压到最后一次性验证。
2. 每个 Chunk 完成后执行一次 checkpoint：
   - `backend` 目标测试
   - `frontend` type-check
   - `git status` 确认仅包含预期文件
3. 严格遵循 DRY/YAGNI：不做未在设计中确认的横向扩展。

## Plan Review Notes

- 若具备子代理能力：每个 Chunk 完成后使用计划审阅子代理进行 review loop。
- 若不具备子代理能力：由当前会话执行同等严格人工审阅（逐任务核对“测试先失败->最小实现->测试通过->提交”链路）。

Plan complete and saved to `docs/superpowers/plans/2026-03-16-full-recovery-implementation-plan.md`. Ready to execute?
