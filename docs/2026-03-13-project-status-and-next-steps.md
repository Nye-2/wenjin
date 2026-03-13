# AcademiaGPT-V2 项目进展与后续计划（截至 2026-03-13）

## 1. 文档目的

这份文档用于在 2026-03-13 这一节点上，对当前 `AcademiaGPT-V2` 项目的整体进展做一个“状态快照”，并给出后续迭代的优先级建议。

它主要回答三个问题：

1. 当前项目主干和关键子系统已经走到了什么程度？
2. 本科毕业论文（thesis）workspace 的新工作台体验已经完成到什么程度，还缺哪些环节？
3. 下一阶段应该优先做哪些具体工作，避免再开一轮大规模重构。

和 2026-03-12 的几份文档（架构评估、功能扩展指南、性能计划等）相比，本文件更偏“项目管理视角”，聚焦已完成与待办。

---

## 2. 当前整体架构状态（简要）

这一部分只总结关键结论，详细设计仍以 2026-03-12 的几份文档为准。

### 2.1 三层结构已稳定

当前整体仍采用三层结构，且已经可承载后续扩展：

1. 前端工作台层
   - 主要路径：`frontend/app/(workbench)/workspaces/[id]/...`
   - 职责：工作台 UI、模块卡片、聊天、artifact/paper 展示、任务轮询

2. 网关编排层
   - 主要路径：`backend/src/gateway/routers/*`
   - 职责：认证、workspace 鉴权、API 合同、任务提交与状态查询

3. 能力执行层
   - 主要路径：
     - `backend/src/workspace_features/*`
     - `backend/src/task/*`
     - `backend/src/thesis/*`
     - `backend/src/skills/*`
   - 职责：feature handler、异步任务执行、thesis workflow、artifact 持久化

关键边界已经基本固定：

- Router 不写复杂业务，只做鉴权 + 编排 + payload 组装。
- Feature 元数据统一通过 `workspace_features/registry.py` 暴露给前端。
- 非 thesis feature 统一走 `workspace_feature` runtime + handler。
- thesis 写作走独立的 LangGraph workflow（`thesis_generation` 任务类型）。

### 2.2 核心共享契约

几个重要的前后端契约已形成“事实标准”：

- Workspace type：`sci | thesis | proposal | software_copyright | patent`
- Feature 元数据：统一来自 `backend/src/workspace_features/registry.py`
- 异步任务协议：
  - 提交：`TaskService.submit_task(...)`
  - 轮询：`GET /api/tasks/{task_id}`（目前仍主要使用轮询，后续可切 SSE）
- Artifact taxonomy：统一在 `backend/src/artifacts/types.py`
- Chat thread：已从内存迁移到数据库模型 + service（见 3 月 12 日文档）

在这个基础上，本轮主要集中在：

1. thesis workspace 的新工作台体验落地。
2. Deep Research / 开题调研 / 编译导出等模块与 artifact / dashboard 的打通。
3. 其他 workspace 的前端模板统一到同一工作台框架。

---

## 3. Thesis Workspace 当前进展

### 3.1 六大模块定义与前端工作台

Thesis workspace 当前采用“模块卡片式工作台”：

- Registry 中定义的 6 个模块（`backend/src/workspace_features/registry.py`）：
  - `deep_research`
  - `literature_management`
  - `opening_research`
  - `thesis_writing`
  - `figure_generation`
  - `compile_export`
- 前端入口页：`frontend/app/(workbench)/workspaces/[id]/page.tsx`
  - type 为 `thesis` 时，采用卡片工作台布局：
    - 顶部：workspace 信息（名称 / 描述 / type badge / discipline）。
    - 中部：六个模块卡片（`ModuleCard`）。
    - 底部：最近产出（`RecentArtifacts`）。

Dashboard 数据来源：

- API：`GET /api/workspaces/{workspace_id}/dashboard`
- 服务：`backend/src/services/dashboard_service.py`

### 3.2 已经打通的模块链路

#### 3.2.1 Deep Research（深度调研）

**后端：**

- Skill：`backend/src/skills/implementations/deep_research.py`
  - 使用多 subagent 并行执行：文献侦察、趋势识别、gap 挖掘、创意生成。
  - 输出包含多种结构化 artifact（文献综述、研究创意、gap 分析）：
    - `literature_review`
    - `research_ideas`
    - `gap_analysis`
- Task 类型：`deep_research`（见 `backend/src/task/registry.py`）
- 任务桥接：
  - 在统一任务执行函数中（`backend/src/task/tasks/base.py`）对 `task_type == "deep_research"` 做了专门处理：
    - 将 Skill 输出的 `AcademicArtifact` 转存为数据库 `Artifact` 记录。
    - 将 `result["artifacts"]` 替换为 `{id, type, title}` 引用，并确保 `refresh_targets` 包含 `"artifacts"`。
- Dashboard 聚合：
  - `DashboardService._get_deep_research_status` 会：
    - 查看 `TaskRecord.task_type == "deep_research"` 的运行 / 完成情况决定模块状态。
    - 统计当前 workspace 下 `type="research_ideas"` 的数量，并写入 `summary.ideas_count`。

**前端：**

- 专属工作区页面：`frontend/app/(workbench)/workspaces/[id]/deep-research/page.tsx`
  - 输入：研究主题（默认用 workspace 描述/名称预填）。
  - 行为：点击“开始 Deep Research”时调用：
    - `executeWorkspaceFeature(workspaceId, "deep_research", { query })`
  - 对结果不做本页内轮询，只做成功/失败提示，artifact 展示由主工作台的知识区/最近产出统一处理。
- Chat 快捷指令：
  - ChatPanel 侧的 QuickAction 也会透传一个可用的 query（基于 workspace 信息），目前可作为备用入口。

整体上，Deep Research 已经形成完整闭环：

> 前端触发 → skill 执行 → artifact 落库 → dashboard & 知识区可见。

#### 3.2.2 文献管理（literature_management）

**后端：**

- 文献存储模型与 service 已存在（`WorkspaceLiterature`、`LiteratureService`），不再赘述。
- Dashboard 中，将模块 id 改为 `literature_management`，并补充 summary：
  - `summary.total`：总文献数。
  - `summary.core`：核心文献数。

**前端：**

- 专属页面：`frontend/app/(workbench)/workspaces/[id]/literature/page.tsx`
  - 使用 `useLiteratureStore` 调用 `/workspaces/{id}/literature` API。
  - 展示总数/核心数、列表、搜索/筛选 UI（部分操作仍为占位，可后续补齐）。

Dashboard 卡片可正确显示“X 篇文献”，与模块状态一致。

#### 3.2.3 开题调研（opening_research）

**后端：**

- Handler：`backend/src/workspace_features/handlers/thesis.py` 中 `opening_research`：
  - 输入：
    - `topic`：研究主题（默认可用 workspace name）。
    - `report_type`：`opening_report` / `literature_review` / `feasibility_analysis`。
  - 输出：
    - 创建对应类型的 artifact（`type = report_type`），内容为占位结构。
    - `refresh_targets = ["artifacts"]`。
- Dashboard：
  - `_get_opening_research_status` 现在以以下类型的 artifact 为依据：
    - `opening_report`
    - `literature_review`
    - `feasibility_analysis`
  - 将数量写入 `summary.reports_count`。

**前端：**

- 专属页面：`frontend/app/(workbench)/workspaces/[id]/opening-research/page.tsx`
  - 左侧配置：
    - 研究主题：默认用 workspace 描述/名称。
    - 报告类型单选：开题报告 / 文献综述 / 可行性分析。
  - 行为：点击“生成报告”时：
    - `executeWorkspaceFeature(workspaceId, "opening_research", { topic, report_type })`
  - 成功后提示“报告生成任务已提交，将作为产出物保存”，错误时提示具体信息。

闭环与 Deep Research 类似，artifact 会出现在 KnowledgePanel 和最近产出中。

#### 3.2.4 编译导出（compile_export）

**后端：**

- Handler：`backend/src/workspace_features/handlers/thesis.py` 中 `compile_and_export`
  - 当前仍是“骨架占位实现”：
    - 读取 `template` / `compiler` 等参数。
    - 模拟收集章节与 LaTeX 组装。
    - 创建一个 `type="paper_draft"` 的 artifact（编译稿占位），内容中保留模板/编译器信息。
    - `refresh_targets = ["artifacts"]`。
- Dashboard：
  - `_get_compile_export_status` 会：
    - 查找 `type="paper_draft"` 且 `created_by_skill="thesis.compile_export"` 的记录。
    - 有记录则标记为 `status="completed"`，并从最新记录的 `created_at` 填入 `summary.last_compile`。

**前端：**

- 专属页面：`frontend/app/(workbench)/workspaces/[id]/compile-export/page.tsx`
  - 左侧配置：
    - LaTeX 模板：默认/IEEE/ACM。
    - 编译器：XeLaTeX / PDFLaTeX / LuaLaTeX。
    - 参考文献格式：GB/T 7714 / APA / MLA（当前 handler 暂未真正使用）。
  - 行为：点击“编译 PDF”时：
    - `executeWorkspaceFeature(workspaceId, "compile_export", { template, compiler, bibliography_style })`
  - 页面给出“编译任务已提交”的提示，真正的 PDF 预览仍是后续待做。

整体上，编译模块已经具备“编译任务 + 编译稿 artifact + dashboard 标记”的闭环，只是实际 LaTeX 组装与 PDF 生成还没接工具链。

### 3.3 部分接通 / 仍为占位的模块

#### 3.3.1 图表生成（figure_generation）

当前状态：

- Handler 已存在（`thesis.figure_generation`），会创建 `type="figure"` 的 artifact，并触发 `refresh_targets=["artifacts"]`。
- Dashboard 已根据 `type="figure"` 的数量填充 `summary.figures_count`。
- 专属页面 `figure-generation/page.tsx` 目前只有 UI，还没挂到 execute API 上。

要补全闭环，只需：

- 将页面中的“图表类型 / 描述 / 关联章节”绑定到本地状态。
- 在“生成图表”按钮上调用：
  - `executeWorkspaceFeature(workspaceId, "figure_generation", { type, description, chapter_index })`。

#### 3.3.2 论文写作（thesis_writing）

当前状态：

- 后端：
  - Feature 使用 `task_type="thesis_generation"`，统一走 LangGraph workflow。
  - `execute_thesis_generation` 支持不同 `action`：
    - `"generate_outline"`：调用 `generate_outline_only`（目前是占位，尚未真正生成 outline artifact）。
    - `"write_chapter"`：`write_single_chapter` 占位逻辑。
    - 其他（默认 `write_all`）：走完整的 workflow。
- 前端：
  - 专属页面有两步 UI（大纲规划 / 全文写作）。
  - “生成大纲”按钮现在已经调用：
    - `executeWorkspaceFeature(workspaceId, "thesis_writing", { action: "generate_outline", paper_title, target_words })`
  - 目前仍不从任务结果中解析 outline 数据，`thesis-writing` store 内的 `OutlineData`/`ChapterStatus` 还没有被真实填充。
- Dashboard：
  - 使用 `framework_outline` 是否存在 + `thesis_chapter` 数量来判断 status 和 `outline_done`。

要让论文写作模块真正“完整可用”，需要一轮专门的设计与实现（见后续计划部分）。

---

## 4. 其他 workspace 的前端模板迁移

为了降低心智负担，当前已经将 thesis 的卡片工作台模板迁移到所有 workspace 类型：

- `frontend/app/(workbench)/workspaces/[id]/page.tsx` 逻辑：
  - `workspace.type === "thesis"`：
    - 使用原有 thesis 专用卡片布局。
  - 其他类型：
    - 顶部：与 thesis 一致的 header。
    - 主体：
      1. 模块卡片网格（根据 `features` 列表渲染）。
      2. 最近产出（ artifacts 列表）。
      3. 嵌入的三列工作区：
         - 左：KnowledgePanel（artifacts 时间线）。
         - 中：ChatPanel（chat + QuickActions）。
         - 右：LiteraturePanel（文献列表）。

模块卡片点击行为：

- 对 thesis 六个模块：通过 `featureRouteMap` 跳转到对应的专属页面。
- 对其他 workspace feature：暂时没有专属页面时，点击退回 workspace 主视图（避免 404）。
  - 后续逐个 workspace 做深度定制时，只需增加 route + 页面即可。

---

## 5. 后续工作建议（按优先级）

本节按“影响力 × 成熟度”排序，建议从上往下推进。

### 5.1 完成 Thesis Workspace 的真实论文写作闭环（高优先级）

目标：让 `thesis_writing` 模块不仅能提交任务，而且能真实生成大纲和章节，并与前端写作工作区联动。

建议拆分：

1. **大纲生成**
   - 设计一种可持久化的大纲结构（可以沿用 `framework_outline` 结构，或新增 `THESIS_OUTLINE` 类型）。
   - 在 `generate_outline_only` 中真正调用一个 outline 生成能力（可以是 skill 或 workflow 的子流程），生成的结果落为 artifact。
   - Dashboard 继续以该 artifact 存在与否判断 `outline_done`。
   - 前端在 `thesis-writing` 页面中，从该 artifact 解析出 `OutlineData`，填充 `useThesisWritingStore`。

2. **章节写作**
   - 定义章节 artifact 结构：`type="thesis_chapter"`，content 中至少包含章节 index/title/content。
   - 将 `write_single_chapter` 从占位改为真实调用 workflow 或专用 writer 能力。
   - 前端章节导航与编辑器从 `chapters` 列表驱动，支持查看/刷新单个章节。

3. **与 LangGraph workflow 对齐**
   - 评估现有 thesis workflow（`thesis/workflow/*`）生成的 state 与 artifact 的关系：
     - 是否可以在 workflow 节点中直接落 `framework_outline` / `thesis_chapter` artifact。
     - 或者将 workflow 的中间 state 转成 artifact。

### 5.2 完成 Figure Generation 模块闭环（中高优先级）

目标：图表模块能够从前端配置到生成 artifact，并在 KnowledgePanel/RecentArtifacts 中可见。

步骤：

1. 前端：
   - 在 `figure-generation/page.tsx` 上实现与 handler 的对接（类似 OpeningResearch）：
     - 收集 `type` / `description` / `chapter_index`。
     - 调用 `executeWorkspaceFeature(workspaceId, "figure_generation", params)`。
2. 后端：
   - 根据实际可用的图表生成工具（如现有 `thesis.execution.figure_tool`）替换 handler 中的 TODO。
   - 实现实际的 SVG/PNG 生成和路径写入（目前 content 中还只是占位 `render_data`）。

这样一来，Dashboard 与前端卡片的“图表数量”会变成有意义的指标。

### 5.3 让 Deep Research 产物更好地喂给后续模块（中优先级）

当前 Deep Research 的产物会作为 artifact 持久化，但其他模块尚未直接消费这些产物。建议：

1. 在文献管理模块中增加“从 Deep Research 导入”入口（部分逻辑已在 `useLiteratureStore.importFromDeepResearch` 中存在，可接上 UI）。
2. 在开题调研与论文写作中，适度使用 Deep Research 的结果作为上下文（例如自动推荐开题报告结构、章节分布、图表建议等）。

### 5.4 为其他 workspace 定义最小可用模块集（中优先级）

目前其他 workspace 已共享工作台模板，但模块定义和 handler 实现仍较薄。建议按 workspace type 逐个推进：

- `sci`：
  - 基本模块：文献检索、论文分析、写作、投稿建议。
  - 优先将已有的 literature_review / framework_designer / fullpaper_writer skill 挂载成 feature。
- `proposal`：
  - 从“申报书大纲 + 背景调研 + 预算/风险”三个模块开始。
- `software_copyright` / `patent`：
  - 已有部分 handler（如 soft copyright 材料），可扩展到完整申请流程。

目标不是一次性做完，而是保证每个 workspace 至少有 2–3 个“能产生真实 artifact 的模块”，避免空壳。

### 5.5 性能与基础设施（跟进 3 月 12 日性能计划）

这部分在 2026-03-12 的性能与基础设施改进文档中已有详细规划，这里只强调几个与当前工作直接相关的点：

1. **任务状态轮询 → SSE**：ChatPanel 仍使用轮询 `/tasks/{task_id}`，后续可切到 `/tasks/{task_id}/stream`。
2. **Progress 写库频率控制**：ProgressTracker 仍会频繁写 DB，可考虑引入节流策略或仅在关键阶段落库。
3. **观察性（Observability）**：Sentry/Prometheus 配置存在但未全面接入，可以结合 thesis workflow 和 deep_research 等热点路径先做一波试点。

---

## 6. 总结

截至 2026-03-13，`AcademiaGPT-V2` 的整体状态可以总结为：

- 架构主干已经稳定，并支持通过 registry + handler 方式“挂能力而不是改核心”。
- Thesis workspace 的新工作台体验已基本落地，Deep Research / 开题调研 / 编译导出等模块实现了从 UI 到 artifact 的闭环，Dashboard 状态也与之对齐。
- Deep Research 的能力已经以 skill 形式成熟，但在“产物复用”和“与其他模块联动”上还有提升空间。
- 论文写作模块已经接通任务链路，但大纲生成和章节写作仍主要是占位实现，需要单独一轮设计与实现。
- 其他 workspace 已完成前端模板迁移，可以在现有工作台框架上按需逐个填充能力。

后续的重点工作应从“再造架构”彻底转向“补能力模块 + 打通具体闭环”，尤其是：

1. 让 thesis 写作模块真正产出可编辑的大纲和章节。
2. 让图表生成模块跑通完整闭环。
3. 让 Deep Research 的产物在文献管理、开题调研、写作中被系统性复用。
4. 为其他 workspace 设计并实现一套最小可用模块集，在统一工作台框架下逐步扩张能力。

