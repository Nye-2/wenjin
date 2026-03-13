# Thesis Workspace Review 与架构基线（2026-03-13）

## 1. 评审范围

本次 review 覆盖 thesis workspace 的 6 个模块链路以及当前“统一 feature 执行架构”。

评审目标：

1. 确认 thesis workspace 可跑通（任务可提交、可轮询、可落库、可在工作台回显）。
2. 清除 `thesis` handler 中剩余 placeholder/TODO，实现可执行逻辑。
3. 在不做大重构的前提下完成一轮可复用的架构优化，为其他 workspace 批量开发做模板。

---

## 2. 结论摘要

### 2.1 当前状态

thesis workspace 已达到“可跑通 + 可降级 + 可扩展”状态：

1. `figure_generation`：
   - 支持策略路由（mermaid/python/kling）。
   - provider 可用时真实执行；不可用时自动降级保存 `source_code/prompt` 与升级元数据。
2. `compile_export`：
   - 真实聚合 `framework_outline/thesis_chapter/figure/literature` 组装 LaTeX。
   - 尝试编译 PDF，成功/失败都持久化 `paper_draft`（含 logs/error）。
3. `opening_research`：
   - 模板骨架稳定生成。
   - 在模型可用时尝试 LLM 填充；失败则模板回退（`template_fallback`）。

### 2.2 架构优化完成点

1. 新增 thesis service 层，handler 薄化（编排/进度/持久化分离）。
2. 前端抽出统一任务轮询工具，减少页面重复逻辑。
3. 执行层补齐 `PYTHON_PLOT` provider 映射，图表能力可真实执行（环境具备时）。

---

## 3. 关键改动清单

### 3.1 后端

1. 新增：`backend/src/workspace_features/services/thesis_feature_service.py`
2. 修改：`backend/src/workspace_features/handlers/thesis.py`
3. 修改：`backend/src/execution/service.py`

### 3.2 前端

1. 新增：`frontend/lib/taskPolling.ts`
2. 修改：`frontend/app/(workbench)/workspaces/[id]/thesis-writing/page.tsx`
3. 修改：`frontend/app/(workbench)/workspaces/[id]/figure-generation/page.tsx`
4. 修改：`frontend/app/(workbench)/workspaces/[id]/opening-research/page.tsx`
5. 修改：`frontend/app/(workbench)/workspaces/[id]/compile-export/page.tsx`

### 3.3 测试

1. 修改：`backend/tests/task/test_thesis_handlers.py`
   - 从“仅断言成功”升级为“断言真实 payload 字段（generation/compile/report 模式）”。

---

## 4. 跑通验证结果

## 4.1 后端测试

已执行：

```bash
cd backend
pytest tests/gateway/routers/test_features.py \
       tests/task/test_workspace_feature_handler.py \
       tests/task/test_thesis_handlers.py
```

结果：`21 passed`。

## 4.2 前端类型检查

已执行：

```bash
cd frontend
npx tsc --noEmit
```

结果：通过。

## 4.3 Python 语法检查

已执行：

```bash
python -m py_compile \
  backend/src/workspace_features/services/thesis_feature_service.py \
  backend/src/workspace_features/handlers/thesis.py
```

结果：通过。

---

## 5. 现存风险与边界

1. Mermaid/Kling provider 当前未接入 execution provider map。
   - 已通过降级策略保证业务不中断。
   - 后续接 provider 后可按 artifact 中 upgrade metadata 自动升级渲染。
2. compile 目前以“可编译优先”实现 markdown->latex 转换。
   - 能跑通，但不是排版最优质量；后续可升级为模板驱动的结构化渲染器。
3. opening report 的高质量内容依赖 LLM provider 可用性与 prompt 质量。
   - 当前模板 fallback 可保底交付。

---

## 6. 对后续批量开发的意义

本次 thesis workspace 已可作为其他 workspace 的“标准样板”：

1. 统一入口：`registry -> task -> handler -> artifact -> dashboard refresh`。
2. 可复用抽象：`workspace_features/services/*`。
3. 可复制前端模式：`execute -> pollTaskUntilTerminal -> fetchArtifacts`。
4. 可验证标准：后端 handler 测试 + 路由测试 + 前端类型检查。
