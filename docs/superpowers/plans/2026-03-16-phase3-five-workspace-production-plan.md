# Phase 3 Five-Workspace Production Launch Implementation Plan (Baseline: ccda822)

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 2026-04-01 同日全量上线 thesis/sci/proposal/software_copyright/patent 五个 workspace，达到真实用户可用质量，并完成跨 workspace 的一致性 UI/UX 升级。

**Architecture:** 基于当前主干已落地的 `FeatureExecutionHandler`（Phase 2/3）和前端 `useFeatureTaskRunner`（commit `ccda822`）继续增量实现。`thesis` 与 `sci` 继续保持分离的 handler/service 业务实现，不新增统一 paper pipeline 业务层。执行遵循 `@superpowers/test-driven-development`：每个任务先失败测试，再最小实现，再回归验证。

**Tech Stack:** FastAPI, SQLAlchemy Async, Celery, Redis, Next.js 15, TypeScript, Zustand, Pytest.

---

## Baseline Impact Assessment (2026-03-16)

1. 已合入 `d346181`：任务系统一致性与可靠性增强（feature execution handler + task progress/store）。
2. 已合入 `ccda822`：前端 feature 页统一到 `useFeatureTaskRunner`，大量页面从“手写 execute+poll”收敛到共用 hook。
3. 因此原计划中的“新增 profile service 文件”与“重写 router 编排”已过时，需要改为在现有 workspace service/handler 上增量约束。
4. 当前工作区仍有并行改动流（literature external/mcp/http client 等）未归档为本计划范围，执行时必须隔离。
5. 质量门禁需要拆为两层：
   - Core Gate（Phase 3 必过）
   - Extended Gate（并行流稳定后补过）

## Execution Guardrails

1. 只做 Phase 3 相关文件，禁止无关重构。
2. `thesis` 与 `sci` 分离实现，不抽象统一论文业务 pipeline。
3. 输出语言硬约束：`thesis=zh`，`sci=en`。
4. UI 中英切换仅影响界面文案，不影响生成语言。
5. 本轮执行不做 `git commit`，仅产出可验证改动与测试结果。
6. 下列并行改动路径视为只读边界，除非任务明确要求，不得触碰：
   - `backend/src/academic/literature/external/*`
   - `backend/src/mcp/tools/*`
   - `backend/src/integration/*`
   - `backend/tests/integration/*`
   - `backend/tests/mcp/*`
   - `backend/.env`
   - `backend/Dockerfile`
   - `start.sh`

---

## File Structure

### Backend (Expected Create)

- `backend/tests/workspace_features/test_workspace_e2e_matrix.py`
- `backend/src/quality/release_gate.py`
- `backend/tests/services/test_release_gate.py`

### Backend (Expected Modify)

- `backend/src/workspace_features/services/thesis_feature_service.py`
- `backend/src/workspace_features/services/sci_feature_service.py`
- `backend/src/workspace_features/services/proposal_feature_service.py`
- `backend/src/workspace_features/services/software_copyright_feature_service.py`
- `backend/src/workspace_features/services/patent_feature_service.py`
- `backend/src/workspace_features/handlers/thesis.py`
- `backend/src/workspace_features/handlers/sci.py`
- `backend/src/workspace_features/handlers/proposal.py`
- `backend/src/workspace_features/handlers/software_copyright.py`
- `backend/src/workspace_features/handlers/patent.py`
- `backend/src/services/dashboard_service.py`

### Frontend (Expected Create)

- `frontend/components/workspace/TaskFeedbackBanner.tsx`
- `frontend/components/workspace/WorkspaceResultPanel.tsx`

### Frontend (Expected Modify)

- `frontend/hooks/useFeatureTaskRunner.ts`
- `frontend/app/(workbench)/workspaces/[id]/components/ModuleCard.tsx`
- `frontend/app/(workbench)/workspaces/[id]/page.tsx`
- `frontend/app/(workbench)/workspaces/[id]/literature/page.tsx`
- `frontend/app/(workbench)/workspaces/[id]/thesis-writing/page.tsx`
- `frontend/app/(workbench)/workspaces/[id]/writing/page.tsx`
- `frontend/app/(workbench)/workspaces/[id]/proposal-outline/page.tsx`
- `frontend/app/(workbench)/workspaces/[id]/technical-description/page.tsx`
- `frontend/app/(workbench)/workspaces/[id]/patent-outline/page.tsx`
- `frontend/app/(workbench)/workspaces/[id]/figure-generation/page.tsx`
- `frontend/app/(workbench)/workspaces/[id]/compile-export/page.tsx`
- `frontend/app/(workbench)/workspaces/[id]/literature-search/page.tsx`
- `frontend/app/(workbench)/workspaces/[id]/paper-analysis/page.tsx`
- `frontend/app/(workbench)/workspaces/[id]/background-research/page.tsx`
- `frontend/app/(workbench)/workspaces/[id]/copyright-materials/page.tsx`
- `frontend/app/(workbench)/workspaces/[id]/prior-art-search/page.tsx`

### Docs (Expected Modify/Create)

- Modify: `docs/2026-03-13-project-status-and-next-steps.md`
- Create: `docs/phase3-2026-04-01-launch-checklist.md`

---

## Chunk 0: Baseline Reconciliation

### Task 0: 锁定执行基线与改动边界

**Files:**
- Modify: `docs/superpowers/plans/2026-03-16-phase3-five-workspace-production-plan.md`（本文件，仅在需要时更新）

- [ ] **Step 1: 记录当前工作区状态**

Run: `cd /home/cjz/AcademiaGPT-V2 && git status --short`
Expected: 输出包含并行改动流文件；Phase 3 目标文件应可识别。

- [ ] **Step 2: 建立 no-touch 边界校验**

Run: `cd /home/cjz/AcademiaGPT-V2 && git diff --name-only | rg "^(backend/src/academic/literature/external|backend/src/mcp/tools|backend/src/integration|backend/tests/integration|backend/tests/mcp|backend/.env|backend/Dockerfile|start.sh)"`
Expected: 命中并行流文件（只读）；后续任务不修改这些路径。

- [ ] **Step 3: 运行基线核心测试（当前主干能力）**

Run:

```bash
cd /home/cjz/AcademiaGPT-V2/backend
PYTHONPATH=. uv run pytest \
  tests/gateway/routers/test_features.py \
  tests/application/handlers/test_feature_execution_handler.py -v
```

Expected: PASS

- [ ] **Step 4: 运行前端类型检查基线**

Run: `cd /home/cjz/AcademiaGPT-V2/frontend && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 5: 输出基线结论（不提交）**

结果格式：`基线 commit + 已通过测试 + no-touch 边界 + 风险清单`。

---

## Chunk 1: 子项目 A（业务闭环与语言硬约束）

### Task 1: thesis/sci 语言硬约束落地（在现有 service/handler 上增量实现）

**Files:**
- Modify: `backend/src/workspace_features/services/thesis_feature_service.py`
- Modify: `backend/src/workspace_features/services/sci_feature_service.py`
- Modify: `backend/src/workspace_features/handlers/thesis.py`
- Modify: `backend/src/workspace_features/handlers/sci.py`
- Create/Modify: `backend/tests/workspace_features/test_workspace_e2e_matrix.py`

- [ ] **Step 1: 写失败测试（语言约束）**

```python
def test_thesis_output_language_is_forced_to_zh():
    assert resolve_thesis_output_language(template="default") == "zh"
    assert resolve_thesis_output_language(template="english") == "zh"


def test_sci_writing_payload_must_mark_en_output_language():
    payload = build_sci_writing_payload(...)
    assert payload["output_language"] == "en"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/workspace_features/test_workspace_e2e_matrix.py -v -k "language or thesis or sci"`
Expected: FAIL

- [ ] **Step 3: 最小实现语言约束**

```python
# thesis_feature_service.py
THESIS_OUTPUT_LANGUAGE = "zh"

# sci_feature_service.py
SCI_OUTPUT_LANGUAGE = "en"
```

实现要求：
- thesis 编译语言不再跟随 template 漂移，固定 `zh`。
- sci 写作 fallback 模板与 LLM prompt 统一英文输出导向。
- sci/thesis 相关 artifact payload 增加 `output_language` 字段。
- handler 返回 `data` 补充 `output_language`，便于前端/监控识别。

- [ ] **Step 4: 运行定向 + 现有关键回归**

Run:

```bash
cd /home/cjz/AcademiaGPT-V2/backend
PYTHONPATH=. uv run pytest tests/workspace_features/test_workspace_e2e_matrix.py -v -k "thesis or sci"
PYTHONPATH=. uv run pytest tests/gateway/routers/test_features.py -v
```

Expected: PASS

- [ ] **Step 5: 任务检查点（不提交）**

记录：改动文件、测试结果、残余风险。

### Task 2: proposal/software_copyright/patent 三线闭环一致化

**Files:**
- Modify: `backend/src/workspace_features/services/proposal_feature_service.py`
- Modify: `backend/src/workspace_features/services/software_copyright_feature_service.py`
- Modify: `backend/src/workspace_features/services/patent_feature_service.py`
- Modify: `backend/src/workspace_features/handlers/proposal.py`
- Modify: `backend/src/workspace_features/handlers/software_copyright.py`
- Modify: `backend/src/workspace_features/handlers/patent.py`
- Modify: `backend/tests/workspace_features/test_workspace_e2e_matrix.py`

- [ ] **Step 1: 写失败测试（三 workspace 闭环元数据一致性）**

```python
def test_proposal_workspace_payload_has_required_audit_fields():
    assert payload["generation_mode"] in {"llm", "template_fallback"}
    assert payload["schema_version"] == "v1"
    assert payload["generated_at"]


def test_copyright_workspace_payload_has_required_audit_fields(): ...

def test_patent_workspace_payload_has_required_audit_fields(): ...
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/workspace_features/test_workspace_e2e_matrix.py -v -k "proposal or copyright or patent"`
Expected: FAIL

- [ ] **Step 3: 最小实现统一元数据**

```python
payload.update({
  "schema_version": "v1",
  "generated_at": now_iso,
  "output_language": "zh",
})
```

实现要求：
- 三个 workspace 的核心 feature payload 都具备可审计字段。
- handler `data` 返回包含 `generation_mode` 与关键计数信息。

- [ ] **Step 4: 运行矩阵回归**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/workspace_features/test_workspace_e2e_matrix.py -v`
Expected: PASS

- [ ] **Step 5: 任务检查点（不提交）**

记录：每个 workspace 覆盖的 feature 与通过证据。

---

## Chunk 2: 子项目 B（UI/UX 统一基线，基于 useFeatureTaskRunner）

### Task 3: 统一任务反馈组件（空/加载/失败/重试/进度）

**Files:**
- Create: `frontend/components/workspace/TaskFeedbackBanner.tsx`
- Modify: `frontend/hooks/useFeatureTaskRunner.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/literature/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/figure-generation/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/compile-export/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/literature-search/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/paper-analysis/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/writing/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/proposal-outline/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/background-research/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/copyright-materials/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/technical-description/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/patent-outline/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/prior-art-search/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/thesis-writing/page.tsx`

- [ ] **Step 1: 先制造失败（引用新组件）**

在一个页面先引入 `<TaskFeedbackBanner />`（组件尚不存在）。

- [ ] **Step 2: 运行类型检查确认失败**

Run: `cd /home/cjz/AcademiaGPT-V2/frontend && npx tsc --noEmit`
Expected: FAIL（module not found / type missing）

- [ ] **Step 3: 最小实现共用反馈组件 + hook 状态收敛**

```tsx
<TaskFeedbackBanner
  isRunning={isRunning}
  status={status}
  error={error}
  onRetry={retryFn}
/>
```

实现要求：
- 所有核心 feature 页不再手写 `error/status` 文案块。
- `literature/page.tsx` 迁移到 `useFeatureTaskRunner`，去除手写 poll 逻辑。
- hook 暴露统一可读状态，页面只负责参数与渲染。

- [ ] **Step 4: 运行类型检查**

Run: `cd /home/cjz/AcademiaGPT-V2/frontend && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 5: 任务检查点（不提交）**

记录：已迁移页面列表与未迁移例外（若有）。

### Task 4: 五类 workspace 结果页统一信息层

**Files:**
- Create: `frontend/components/workspace/WorkspaceResultPanel.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/thesis-writing/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/writing/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/proposal-outline/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/technical-description/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/patent-outline/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/ModuleCard.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/page.tsx`

- [ ] **Step 1: 先写统一 view model（并触发编译失败）**

```ts
interface WorkspaceResultViewModel {
  summary: string;
  sections: { title: string; content: string }[];
  nextActions: string[];
  outputLanguage?: "zh" | "en";
}
```

先在页面引用该模型但不实现转换函数，制造类型错误。

- [ ] **Step 2: 运行类型检查确认失败**

Run: `cd /home/cjz/AcademiaGPT-V2/frontend && npx tsc --noEmit`
Expected: FAIL

- [ ] **Step 3: 最小实现统一结果展示层**

```tsx
<WorkspaceResultPanel
  summary={vm.summary}
  sections={vm.sections}
  nextActions={vm.nextActions}
  outputLanguage={vm.outputLanguage}
/>
```

实现要求：
- 五类页面统一为“摘要 + 结构 + 下一步动作”。
- 页面保留自身业务参数区，但结果层结构统一。
- `ModuleCard` 结合 dashboard summary 显示最近成功/失败语义。

- [ ] **Step 4: 再跑类型检查**

Run: `cd /home/cjz/AcademiaGPT-V2/frontend && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 5: 任务检查点（不提交）**

记录：五个目标页面是否都接入统一结果层。

---

## Chunk 3: 子项目 C（发布质量门禁与上线演练）

### Task 5: 发布门禁实现（Go/No-Go 自动评估）

**Files:**
- Create: `backend/src/quality/release_gate.py`
- Create: `backend/tests/services/test_release_gate.py`
- Modify: `backend/src/services/dashboard_service.py`

- [ ] **Step 1: 写失败测试（门禁项缺失应 fail）**

```python
def test_release_gate_fails_when_language_constraints_missing():
    report = run_release_gate(...)
    assert report["status"] == "failed"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/services/test_release_gate.py -v`
Expected: FAIL

- [ ] **Step 3: 最小实现 Core Gate + Extended Gate**

```python
return {
  "status": "passed|failed",
  "core_gate": {...},
  "extended_gate": {...},
  "generated_at": now_iso,
}
```

Core Gate（必须通过）：
- thesis/sci 语言硬约束测试
- workspace e2e matrix
- features router/handler 回归
- frontend `tsc --noEmit`

Extended Gate（并行流稳定后通过）：
- literature external/mcp/integration 相关测试

- [ ] **Step 4: 运行定向测试**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && PYTHONPATH=. uv run pytest tests/services/test_release_gate.py -v`
Expected: PASS

- [ ] **Step 5: 任务检查点（不提交）**

记录：失败时输出可执行修复建议。

### Task 6: 全量回归与 2026-04-01 上线清单

**Files:**
- Modify: `docs/2026-03-13-project-status-and-next-steps.md`
- Create: `docs/phase3-2026-04-01-launch-checklist.md`

- [ ] **Step 1: 跑 Core Gate 回归**

Run:

```bash
cd /home/cjz/AcademiaGPT-V2/backend
PYTHONPATH=. uv run pytest \
  tests/workspace_features/test_workspace_e2e_matrix.py \
  tests/services/test_release_gate.py \
  tests/gateway/routers/test_features.py \
  tests/application/handlers/test_feature_execution_handler.py -v
```

Expected: PASS

- [ ] **Step 2: 跑前端类型检查**

Run: `cd /home/cjz/AcademiaGPT-V2/frontend && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 3: 跑 Extended Gate（条件执行）**

Run:

```bash
cd /home/cjz/AcademiaGPT-V2/backend
PYTHONPATH=. uv run pytest \
  tests/integration/test_tool_chain.py \
  tests/mcp/test_academic_tools.py \
  tests/integration/test_http_client.py -v
```

Expected: PASS（若并行流未稳定，记录为 blocker，不阻塞 Core Go/No-Go）

- [ ] **Step 4: 更新上线清单与项目状态文档**

Run:

```bash
cd /home/cjz/AcademiaGPT-V2
git diff -- docs/2026-03-13-project-status-and-next-steps.md docs/phase3-2026-04-01-launch-checklist.md
```

Expected: 仅包含 Phase 3 上线与门禁信息。

- [ ] **Step 5: 发布前检查点（不提交）**

输出：
- Core Gate 是否全绿
- Extended Gate 状态
- 2026-03-31 Go/No-Go 结论草案

---

## Execution Calendar (Absolute Dates)

1. `2026-03-16 ~ 2026-03-19`: Chunk 0 + Chunk 1 Task 1
2. `2026-03-20 ~ 2026-03-23`: Chunk 1 Task 2
3. `2026-03-24 ~ 2026-03-27`: Chunk 2（UI/UX 统一基线）
4. `2026-03-28 ~ 2026-03-30`: Chunk 3 Task 5（门禁实现）
5. `2026-03-31`: Chunk 3 Task 6（回归 + Go/No-Go）
6. `2026-04-01`: 五 workspace 同日全量上线

## Mandatory Daily Checkpoint

- [ ] thesis/sci 语言硬约束测试保持通过。
- [ ] workspace e2e matrix 保持通过。
- [ ] `test_features.py` 与 `test_feature_execution_handler.py` 保持通过。
- [ ] Frontend `npx tsc --noEmit` 保持通过。
- [ ] no-touch 边界无误改。
- [ ] 风险日志更新（Top 3 blocker + owner + 解除条件）。

Plan complete and saved to `docs/superpowers/plans/2026-03-16-phase3-five-workspace-production-plan.md`. Ready to execute.
