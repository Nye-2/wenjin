# SCI Workspace 开发路线（2026-03-13）

## 1. 当前状态

registry 中已定义 `sci` 的 3 个 feature：

1. `literature_search`
2. `paper_analysis`
3. `writing`

当前主要问题：

1. 后端尚无 `sci.*` 具体 handler（会走 runtime placeholder）。
2. 前端无专属工作页，主要依赖通用工作台 UI。
3. dashboard 缺少对 `sci` 模块的细粒度状态聚合。

---

## 2. 第一阶段目标（先拿真实闭环）

先做 2 个闭环，按以下顺序：

1. `literature_search`（P0）
2. `paper_analysis`（P1）

`writing` 放在第二阶段（P2）。

---

## 3. 详细开发路线

## 3.1 P0: literature_search

### 后端

1. 新增 `backend/src/workspace_features/services/sci_feature_service.py`。
2. 实现 `build_literature_search_payload(...)`：
   - 输入：query、workspace discipline。
   - 先走本地 `PaperService` 搜索或现有 paper 数据源。
   - 返回结构化结果（papers、top_hits、filters、summary）。
3. 在 `backend/src/workspace_features/handlers/` 新增 `sci.py`：
   - 注册 `sci.literature_search`。
   - 持久化 `ArtifactType.LITERATURE_SEARCH_RESULTS`。
4. dashboard：
   - 增加 `sci.literature_search` 状态聚合（最近一次任务 + 结果数量）。

### 前端

1. 新增页面：`frontend/app/(workbench)/workspaces/[id]/literature-search/page.tsx`。
2. 采用统一模式：
   - `executeWorkspaceFeature -> pollTaskUntilTerminal -> fetchArtifacts`。
3. 在工作台 feature route map 中挂 `literature_search` 路由。

### 验收

1. 用户输入 query 后可获得落库 artifact。
2. 工作台 KnowledgePanel 能看到新结果。
3. dashboard 显示文献检索状态与数量。

## 3.2 P1: paper_analysis

### 后端

1. 实现 `build_paper_analysis_payload(...)`：
   - 输入：paper_id 或标题。
   - 输出：方法/实验/结论结构化分析。
2. handler 注册 `sci.paper_analysis`。
3. artifact 类型建议：
   - `paper_analysis`（优先）
   - 失败降级可落 `note`。

### 前端

1. 新增页面：`.../paper-analysis/page.tsx`。
2. 支持从 literature 列表一键带参跳转分析。

### 验收

1. 选中文献后可产出结构化分析 artifact。
2. dashboard 状态可反映是否完成至少一次分析。

## 3.3 P2: writing

### 后端

1. 实现 `build_sci_writing_payload(...)`：
   - 输入：section_type、target_words、context_artifact_ids。
   - 输出：章节草稿（可落 `introduction`/`literature_review`/`discussion_section` 等）。
2. 增加降级策略：
   - LLM 不可用时输出章节骨架模板。

### 前端

1. 新增写作页，支持章节选择与逐段生成。
2. 结果写回 artifacts，并支持二次编辑。

---

## 4. 建议测试清单

1. `tests/task/test_sci_handlers.py`
2. `tests/gateway/routers/test_features.py` 增加 sci execute payload 断言
3. `tests/services/test_dashboard_service.py` 增加 sci 模块状态断言

---

## 5. 估算与里程碑

1. P0：1-2 天
2. P1：1-2 天
3. P2：2-3 天

第一阶段可交付时间：约 3-4 天（P0+P1）。
