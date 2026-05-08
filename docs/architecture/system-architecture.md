# 问津 (Wenjin) 系统架构文档

> 版本：2026-05-01  
> 范围：全栈架构（后端、前端、基础设施）  
> 读者：新加入的开发者、架构评审、运维人员

---

## 1. 项目概述

**问津 (Wenjin)** 是一个面向学术研究的 AI 工作台。它以 "工作区 (Workspace)" 为核心组织单元，支持学位论文、SCI 论文、项目申报书、软件著作权、专利等多种学术工作流。每个工作区包含：

- **Chat 控制面**：以对话方式驱动研究、写作和修改
- **Compute 工作面**：结构化展示 Agent 执行进度、产物、日志和审查门
- **文献库 (Reference Library)**：统一管理文献、引用和证据包
- **LaTeX 编辑器 (WenjinPrism)**：与 Compute 工作面联动的学术写作环境

### 1.1 核心原则

| 原则 | 含义 |
|------|------|
| **Chat = 控制面** | 用户通过聊天线程发起意图，不直接操作业务状态 |
| **Compute = 工作面** | Agent 执行的进度、产物、日志通过 Compute Stage 结构化展示 |
| **FeatureIngress = 唯一入口** | 所有工作区功能（调研、写作、绘图等）必须经过 `FeatureIngressService` 统一调度 |
| **ExecutionSession = 事实源 (SSOT)** | 功能执行业务状态的唯一事实源，ComputeSession 只做 UI 投影 |
| **ReferenceLibrary = 文献 SSOT** | 所有文献以 `WorkspaceReference` 为唯一事实源，BibTeX/引用键均从它派生 |
| **不保留旧链路 fallback** | 新主链路落地后，旧代码路径直接删除，不保留兼容层 |

---

## 2. 系统架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户浏览器                                       │
│  ┌──────────────────────────────┐  ┌─────────────────────────────────────┐  │
│  │  Next.js 前端 (Port 3000)    │  │  独立页面：/latex/:projectId         │  │
│  │  - Chat 线程界面              │  │  - WenjinPrism LaTeX 编辑器          │  │
│  │  - Compute Stage 工作面       │  │                                      │  │
│  │  - Workspace 仪表盘           │  │                                      │  │
│  └──────────────┬───────────────┘  └─────────────────────────────────────┘  │
│                 │                                                             │
│                 ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  Nginx 反向代理 (Port 2026)                                              ││
│  │  - /api/* → Gateway   - SSE 流无缓冲   - 静态资源缓存 365 天              ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                 │                                                             │
│                 ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  FastAPI Gateway (Port 8001)                                             ││
│  │  - 21 个路由模块   - JWT 认证   - 依赖注入   - SSE 事件网关              ││
│  └─────────────────────────────┬───────────────────────────────────────────┘│
│                                │                                              │
│           ┌────────────────────┼────────────────────┐                        │
│           ▼                    ▼                    ▼                        │
│  ┌──────────────┐   ┌──────────────────┐   ┌──────────────────┐             │
│  │  PostgreSQL  │   │  Redis (3 DB)    │   │  Celery Worker   │             │
│  │  pg16+vector │   │  /0 应用运行时    │   │  长任务执行       │             │
│  │  业务持久化   │   │  /1 Celery Broker │   │  - LangGraph     │             │
│  │              │   │  /2 Celery Backend│   │  - 子 Agent 并行 │             │
│  └──────────────┘   └──────────────────┘   └──────────────────┘             │
│                                │                                              │
│  ┌─────────────────────────────┴───────────────────────────────────────────┐│
│  │  可选：TeXLive 容器（LaTeX 编译沙箱）                                    ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 技术栈

| 层级 | 技术选型 |
|------|----------|
| **前端** | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS, Zustand, Framer Motion |
| **后端 Gateway** | FastAPI, Python 3.13+, SQLAlchemy 2 (async), Alembic |
| **后台 Worker** | Celery + asyncio.Runner, Redis 队列 |
| **Agent 运行时** | LangGraph (in-process), 自定义 Subagent 并行执行器 |
| **数据持久化** | PostgreSQL 16 + pgvector |
| **缓存/消息** | Redis 8 (AOF 持久化)，分 3 个逻辑库 |
| **编译环境** | Docker 化 TeXLive 2024 (xelatex/pdflatex/biber) |
| **监控** | Prometheus + Grafana |
| **部署** | Docker Compose, Nginx 反向代理 |

---

## 3. 后端架构

### 3.1 目录结构

```
backend/src/
├── gateway/              # HTTP 层：FastAPI App、路由、依赖注入、中间件、认证
│   ├── app.py            # 应用入口：lifespan 管理（启动/关闭 Sentry、DB、Redis、MCP、watchdog）
│   ├── routers/          # 21 个路由模块
│   ├── deps/             # 依赖注入（get_db、FeatureIngressService、TaskService 等）
│   ├── middleware/       # 关联 ID、错误处理、限流
│   └── validators/       # 请求体校验
├── database/             # SQLAlchemy 异步引擎、会话管理、ORM 模型
│   ├── session.py        # get_db_session() 上下文管理器、引擎工厂
│   ├── base.py           # DeclarativeBase + UUIDMixin + TimestampMixin
│   └── models/           # 23 张表的 ORM 定义
├── services/             # 领域服务层
│   ├── references/       # 文献库：WorkspaceReferenceService、ReferenceBibTeXService、ReferenceEvidenceService
│   ├── latex/            # LaTeX：LatexProjectService、LatexCompileService、反馈改写 Diff
│   ├── execution_session_service.py   # ExecutionSession SSOT 管理
│   └── ...               # 认证、计费、仪表盘、用户记忆等
├── compute/              # Compute Stage：UI 投影层
│   ├── session_service.py           # ComputeSession CRUD + touch_session
│   ├── projection_service.py        # ComputeProjectionService：按需构建投影
│   └── events.py                    # compute.updated 等事件发布
├── workspace_features/   # 工作区功能系统
│   ├── registry.py       # 功能注册表（按 WorkspaceType 定义所有功能）
│   ├── runtime_profiles.py          # 功能运行时画像（CHAT_ONLY / DETERMINISTIC / COMPUTE_WORKFLOW / COMPUTE_AGENTIC）
│   ├── contracts.py      # 功能执行结果标准化合约
│   ├── latex_sync.py     # LaTeX 桥接：sync_project / compile_thesis_payload
│   └── services/         # 各工作区类型的 payload builder 和 feature handler
├── agents/               # Agent 编排层
│   ├── feature_leader/   # 功能执行入口：FeatureLeaderRuntime、Workflow Plan、Graph Registry
│   ├── graphs/           # LangGraph 子图（按 workspace_type/feature_id 组织）
│   ├── harness/          # AgentHarness 合约（当前仅启用 Native Wenjin provider）
│   ├── middlewares/      # 20+ 中间件（沙箱、引用、知识、纠错、澄清等）
│   ├── memory/           # 记忆捕获与压缩
│   └── subagents/        # 子 Agent 并行执行器
├── task/                 # 任务系统
│   ├── celery_app.py     # Celery 应用配置（队列、路由、序列化）
│   ├── worker.py         # Worker 进程生命周期（fork 安全、MCP 启动、Prometheus）
│   ├── store.py          # TaskStore：Redis + PG 双写
│   ├── registry.py       # 任务类型注册（workspace_feature / document_preprocess / reference_preprocess）
│   ├── handlers/         # 任务处理器
│   └── runtime_blocks.py # 结构化运行时状态块（metrics / list / activity / prism 等）
├── execution/            # 执行运行时
│   ├── providers/        # Docker / Local 沙箱提供者
│   ├── security/         # LaTeX / Python 代码安全清洗
│   └── types.py          # ExecutionType 枚举（PYTHON_PLOT、MERMAID_DIAGRAM、AI_IMAGE 等）
├── academic/             # 学术领域服务
│   ├── literature/       # Semantic Scholar 集成、文献检索
│   ├── citation/         # BibTeX / APA / MLA / Chicago / IEEE 格式化
│   └── services/         # ArtifactService、GenerationService
├── tools/                # 工具层
│   ├── builtins/         # 内置工具（文件操作、bash、文献查询、澄清请求等）
│   └── execution/        # 工具执行器（LaTeX 编译等）
├── runtime/              # Run 运行时
│   ├── runs/manager.py   # RunManager：Redis 支持的运行恢复
│   └── stream_bridge/    # Redis Stream 桥接（SSE 多路复用）
├── application/          # 应用编排层
│   ├── handlers/         # ThreadTurnHandler
│   ├── services/         # FeatureIngressService、FeatureSubmissionService、FeatureLaunchService
│   └── presenters/       # AgentResultCard（结果卡片渲染）
├── mcp/                  # Model Context Protocol 运行时和工具注册
├── models/               # 模型路由（LLM  provider 选择和调用）
├── config/               # 应用配置加载
├── observability/        # Prometheus 指标、Sentry
├── quality/              # 发布门控（Release Gate）
├── sandbox/              # 沙箱抽象层
└── workspace_events.py   # 跨模块工作区事件发布
```

### 3.2 Gateway / API 层

**入口**：`src/gateway/app.py` 创建 FastAPI 应用， lifespan 管理所有外部连接的启动和关闭。

**路由列表**（`src/gateway/routers/`）：

| 路由文件 | 端点前缀 | 职责 |
|----------|----------|------|
| `auth.py` | `/api/auth` | JWT 登录/注册/刷新/登出 |
| `workspaces.py` | `/api/workspaces` | 工作区 CRUD |
| `threads.py` | `/api/threads` | 聊天线程管理 |
| `thread_runs.py` | `/api/threads/{id}/runs` | 线程运行（流式/非流式） |
| `runs.py` | `/api/runs` | 独立运行接口 |
| `features.py` | `/api/workspaces/{id}/features` | 功能发现和执行（唯一入口） |
| `compute.py` | `/api/compute` | Compute Session 查询和投影 |
| `tasks.py` | `/api/tasks` | 任务状态轮询 |
| `references.py` | `/api/workspaces/{id}/references` | 文献库 CRUD、导入、搜索、outline |
| `latex.py` | `/api/latex` | LaTeX 项目编译/回滚/反馈改写 |
| `artifacts.py` | `/api/artifacts` | 产物检索 |
| `templates.py` | `/api/templates` | 工作区模板管理 |
| `skills.py` | `/api/skills` | 技能注册和发现 |
| `models.py` | `/api/models` | 可用 LLM 模型列表 |
| `mcp.py` | `/api/mcp` | MCP 扩展管理 |
| `memory.py` | `/api/memory` | 用户记忆查询 |
| `dashboard.py` | `/api/dashboard` | 仪表盘数据 |
| `uploads.py` | `/api/uploads` | 文件上传签名 |

**依赖注入**：`src/gateway/deps/core.py` 提供 `get_db()`（异步会话上下文管理器）。更高层的依赖（如 `FeatureIngressService`）通过嵌套 `Depends()` 链组装。

### 3.3 SSOT 核心

#### 3.3.1 ExecutionSession — 业务状态事实源

**文件**：`src/database/models/execution_session.py`、`src/services/execution_session_service.py`

**职责**：一个功能执行（如"撰写第三章"）的完整生命周期状态机。所有业务状态变更（启动→运行→完成/失败/等待输入）都记录在此。

**核心字段**：
- `id` (UUID), `user_id`, `workspace_id`, `workspace_type`, `feature_id`
- `status`: `launching` → `running` → `completed` / `failed` / `advisory` / `awaiting_user_input`
- `params`: 用户传入参数
- `task_ids`, `primary_task_id`: 关联的 Celery 任务
- `runtime_snapshot`: 结构化运行时快照（`runtime_blocks`）
- `result_summary`, `artifact_ids`, `next_actions`: 执行结果
- `advisory_code`, `last_error`: 异常和咨询信息

**关键模式**：`update_session_record()` 在每次状态变更后，通过**延迟导入**调用 `ComputeSessionService.touch_session_by_execution()`，触发 Compute Stage 刷新。

#### 3.3.2 ComputeSession — UI 投影层

**文件**：`src/database/models/compute_session.py`、`src/compute/session_service.py`

**职责**：Compute Stage 的 UI 投影壳。它**不拥有业务状态**，只提供前端刷新所需的 `updated_at` 和 `ui_state`。

**核心字段**：
- `execution_session_id` (FK, CASCADE)
- `workspace_id`, `user_id`
- `sandbox_session_id`
- `active_view`: 当前活跃视图
- `ui_state` (JSONB): 前端 UI 状态增量

**关键方法**：
- `touch_session()`: 更新 `updated_at` 并发布 `compute.updated` 事件
- `touch_session_by_execution()`: 通过 `execution_session_id` 查找并 touch

#### 3.3.3 ReferenceLibrary — 文献事实源

**文件**：`src/database/models/reference.py`、`src/services/references/service.py`

**核心模型**：`WorkspaceReference`（表 `workspace_references`）

**字段**：标题、作者、年份、DOI、URL、`citation_key`、`bibtex_entry_type`、`bibtex_fields`、
`library_status`（candidate/included/core/excluded/used_in_draft）、
`evidence_level`（metadata_only → indexed_fulltext）、
`fulltext_status`（none/uploaded/preprocessing/indexed/failed）、
`read_status`、`tags`、`notes`

**支撑模型**：
- `ReferenceExternalId`: 来源原生 ID（Semantic Scholar 等）
- `ReferenceAsset`: 上传的 PDF、Markdown、Manifest，含预处理状态
- `ReferenceOutlineNode`: 目录/页码索引节点（`section_path`、`title`、`level`、`page_start`、`page_end`）
- `ReferenceTextUnit`: 全文索引文本块（GIN `to_tsvector` 全文搜索）
- `ReferenceUsageEvent`: 文献在写作中的使用审计
- `ReferenceBibtexSnapshot`: `refs.bib` 物化投影快照

**关键服务**：
- `WorkspaceReferenceService`: CRUD、去重（DOI 或规范化标题）、引用键唯一性、证据等级升级
- `ReferenceBibTeXService`: 从 `WorkspaceReference` 生成 BibTeX、校验、同步到 Prism (`sync_prism`)
- `ReferenceEvidenceService`: 基于全文索引构建证据包（`build_evidence_pack`）
- `ReferenceImportService`: 从 Semantic Scholar、BibTeX、深度搜索产物、手动录入导入

### 3.4 任务/执行系统

#### 3.4.1 Celery 配置

**文件**：`src/task/celery_app.py`

- **Broker**: `redis://redis:6379/1`
- **Backend**: `redis://redis:6379/2`
- **队列**: `default`（通用功能）、`long_running`（文档/文献预处理）、`priority`
- **Worker 设置**: `prefetch_multiplier=2`, `acks_late=True`, `reject_on_worker_lost=True`, soft=10min, hard=15min

#### 3.4.2 Worker 生命周期

**文件**：`src/task/worker.py`

- `worker_process_init`: 重置 DB 引擎（fork 安全）、连接 Redis、初始化 MCP 运行时
- `worker_process_shutdown`: 关闭 MCP、断开 Redis、关闭 DB、标记 Worker 死亡
- 使用 `asyncio.Runner` 桥接 Celery 同步模型与异步代码
- 推荐 Pool: `solo`（避免 asyncio + prefork 事件循环绑定问题）

#### 3.4.3 TaskStore — 双写层

**文件**：`src/task/store.py`

`TaskStore(redis_client, db_session)` 同时写入：
- **Redis**: 运行时状态（status、progress、message、current_step、worker_id、metadata），带 TTL
- **PostgreSQL**: 持久化 `TaskRecord`（含 workspace_id、feature_id、execution_session_id 等上下文）

**关键生命周期**：
- `mark_task_started()` → 更新 Redis + PG，同时更新 `ExecutionSession.status = running`
- `persist_runtime_state()` → 从 metadata 提取 `runtime_blocks` 写入 `ExecutionSession.runtime_snapshot`
- `mark_task_completed()` → 写入最终结果/错误到 PG，更新 `ExecutionSession` 产物、next_actions、result_summary

#### 3.4.4 任务类型

| 任务类型 | 队列 | 超时 | 处理器 |
|----------|------|------|--------|
| `workspace_feature` | `default` | 300s | `workspace_feature_handler.py` → `FeatureLeaderRuntime` |
| `document_preprocess` | `long_running` | 900s | `document_preprocess_handler.py` |
| `reference_preprocess` | `long_running` | 1200s | `reference_preprocess_handler.py` |

### 3.5 Agent / Graph 架构

#### 3.5.1 Feature Leader Runtime

**文件**：`src/agents/feature_leader/runtime.py`

**`FeatureLeaderRuntime.execute_feature()`** 是**所有工作区功能的规范执行路径**：

1. 若功能画像为 `COMPUTE_AGENTIC`，先运行动态子 Agent 工作流 (`_run_dynamic_workflow()`)
2. 将工作流结果注入 payload（`__leader_workflow` / `__leader_workflow_highlights`）
3. 调用 `execute_feature_graph()`（LangGraph 子图）
4. 返回结果 + 产物

#### 3.5.2 动态工作流规划

**文件**：`src/agents/feature_leader/workflow.py`

`build_dynamic_feature_workflow_plan()` 为 `COMPUTE_AGENTIC` 功能创建确定性多阶段计划：

- **调研类**（deep_research、literature_search）：2 阶段 — 发现（scout、trend_spotter、gap_miner）→ 综合（synthesizer）
- **写作类**（thesis_writing、writing）：2 阶段 — 证据（librarian、reviewer）→ 起草（thesis_writer/writer）
- **绘图类**（figure_generation）：1 阶段 — 设计（figure_planner、analyst）

计划受 `FeatureRuntimeProfile` 约束（最大子 Agent 数、允许类型）。

#### 3.5.3 LangGraph 子图注册表

**文件**：`src/agents/feature_leader/graph_registry.py`

- 懒加载：按 `workspace_type` 通过 `importlib` 动态导入 `src.agents.graphs.{type}.{feature}`
- 装饰器：`@register_feature_graph(feature_id, workspace_type)` 绑定子图函数
- 执行：构建系统提示（含工作区上下文 + 用户记忆注入）→ 调用 `(initial_state, payload) -> result`

**子图目录**：
```
src/agents/graphs/
├── thesis/              # deep_research, literature_management, opening_research, thesis_writing, figure_generation
├── sci/                 # literature_search, paper_analysis, writing, literature_review, framework_outline, figure_generation, peer_review, journal_recommend
├── proposal/            # background_research, experiment_design, proposal_outline
├── patent/              # patent_outline, prior_art_search
└── software_copyright/  # technical_description, copyright_materials
```

#### 3.5.4 Agent Harness

**文件**：`src/agents/harness/`

`AgentHarness` 是功能运行时调用 Agent 的合约层。当前启用的 provider 是：
- `NativeWenjinAgentHarness` → `src.subagents.parallel.ParallelExecutor`

非 native provider 不作为当前运行能力；若 runtime profile 配置为 `deerflow`、`claude` 或 `codex`，`FeatureLeaderRuntime` 会拒绝执行，避免未集成 provider 被误用。

协议：`AgentHarness` 接口含 `run_subtask()` 和 `run_session()`

#### 3.5.5 子 Agent 并行执行

**文件**：`src/subagents/parallel.py`

`ParallelExecutor` 执行 `PhasedPlan`（带依赖关系的多阶段计划），支持配置 `max_concurrent`。每个子 Agent 类型由 `src.subagents.academic.registry` 解析。

#### 3.5.6 中间件栈

**文件**：`src/agents/middlewares/`

20+ 中间件注入 Agent 线程：

| 类别 | 中间件 |
|------|--------|
| 执行安全 | `execution.py`, `sandbox.py`, `sandbox_audit.py` |
| 上下文注入 | `citation_context.py`, `literature_context.py`, `knowledge_context.py`, `discipline_context.py`, `workspace_context.py` |
| 状态管理 | `memory.py`, `todo_list.py`, `summarization.py`, `title.py`, `thread_data.py` |
| 鲁棒性 | `loop_detection.py`, `dangling_tool_call.py`, `llm_error_handling.py`, `tool_error_handling.py` |
| 用户交互 | `clarification.py`, `uploads.py`, `view_image.py` |

### 3.6 Feature 系统

#### 3.6.1 功能注册表

**文件**：`src/workspace_features/registry.py`

按 `WorkspaceType` 定义所有功能：

| 工作区类型 | 功能列表 |
|------------|----------|
| **THESIS** | deep_research, literature_management, opening_research, thesis_writing, figure_generation |
| **SCI** | literature_search, paper_analysis, writing, literature_review, framework_outline, figure_generation, peer_review, journal_recommend |
| **PROPOSAL** | background_research, experiment_design, proposal_outline |
| **SOFTWARE_COPYRIGHT** | technical_description, copyright_materials |
| **PATENT** | patent_outline, prior_art_search |

每个功能定义包含：`workspace_type`、`id`、`name`、`agent`、`handler_key`、`task_type`、`panel`、`stages`、`graph_module` 等。

#### 3.6.2 运行时画像

**文件**：`src/workspace_features/runtime_profiles.py`

`FeatureRuntimeProfile` 决定执行模式：

| 模式 | 说明 |
|------|------|
| `CHAT_ONLY` | 简单聊天响应，无计算工作流 |
| `DETERMINISTIC` | 确定性 handler，无 Agent |
| `COMPUTE_WORKFLOW` | 标准计算工作流（默认） |
| `COMPUTE_AGENTIC` | 进入 FeatureLeaderRuntime，子 Agent 扇出 |

关键覆盖：
- 调研类功能 → `COMPUTE_AGENTIC`，最多 4 个研究子 Agent
- `figure_generation`（所有类型）→ `COMPUTE_AGENTIC` + `requires_sandbox=True` + review gate `artifact_preview`

#### 3.6.3 功能执行数据流

```
用户请求 (HTTP / Thread)
    ↓
FeatureIngressService.launch()
    ↓
ExecutionSession 创建 (status=launching)          ← SSOT
    ↓
ComputeSession 确保存在 (UI 投影绑定)
    ↓
FeatureSubmissionService.execute() → Celery 入队
    ↓
Celery Worker: workspace_feature_handler.execute_workspace_feature()
    ↓
FeatureLeaderRuntime.execute_feature()
    ├── 动态工作流 (子 Agent 阶段) [若 COMPUTE_AGENTIC]
    └── LangGraph 子图 (graph_registry)
        ↓
结果 + 产物
    ↓
TaskStore.mark_task_completed()
    ↓
ExecutionSession 更新 (status=completed, artifact_ids, next_actions)
    ↓
ComputeSession touch (updated_at 更新 → 前端刷新)
    ↓
ComputeProjectionService.get_projection() (按需 API)
    ↓
前端 Compute Stage 渲染 runtime_blocks、files、logs、prism、review_gate
```

### 3.7 数据库模型

**引擎**：`create_async_engine()` + `async_sessionmaker(expire_on_commit=False, autocommit=False, autoflush=False)`

**会话管理**：`get_db_session()` 上下文管理器，成功自动 commit，异常自动 rollback。

#### 3.7.1 完整模型清单

| 模型类 | 表名 | 说明 | 关键关系 |
|--------|------|------|----------|
| `User` | `users` | 用户 | → workspaces, threads, user_knowledge, credit_transactions, admin_logs |
| `Workspace` | `workspaces` | 工作区 | → users (FK), workspace_references, artifacts, generation_records, threads |
| `WorkspaceTemplate` | `workspace_templates` | 工作区模板 | → workspaces (FK) |
| `Thread` | `threads` | 聊天线程 | → users (FK), workspaces (FK, SET NULL) |
| `ExecutionSessionRecord` | `execution_sessions` | 执行会话（业务 SSOT）| 无 ORM 关系 |
| `ComputeSessionRecord` | `compute_sessions` | 计算会话（UI 投影）| → execution_sessions (FK, CASCADE) |
| `TaskRecord` | `task_records` | 任务记录 | 无 ORM 关系 |
| `SubagentTaskRecord` | `subagent_task_records` | 子 Agent 任务 | → execution_sessions (FK, CASCADE) |
| `Artifact` | `artifacts` | 产物 | → workspaces (FK), self (parent_artifact_id, SET NULL) |
| `WorkspaceReference` | `workspace_references` | 文献（文献 SSOT）| → workspaces (FK), artifacts (source_artifact_id) |
| `ReferenceExternalId` | `reference_external_ids` | 来源原生 ID | → workspaces, workspace_references |
| `ReferenceAsset` | `reference_assets` | 文献资产 | → workspaces, workspace_references, self (source_asset_id) |
| `ReferenceOutlineNode` | `reference_outline_nodes` | 目录节点 | → workspaces, workspace_references, self (parent_id) |
| `ReferenceTextUnit` | `reference_text_units` | 文本单元 | → workspaces, workspace_references, reference_outline_nodes, reference_assets |
| `ReferenceUsageEvent` | `reference_usage_events` | 使用审计 | → workspaces, workspace_references, reference_outline_nodes, reference_text_units |
| `ReferenceBibtexSnapshot` | `reference_bibtex_snapshots` | BibTeX 快照 | → workspaces |
| `GenerationRecord` | `generation_records` | 生成记录 | → workspaces |
| `CreditTransaction` | `credit_transactions` | 积分交易 | → users, workspaces |
| `UserKnowledge` | `user_knowledge` | 用户知识 | → users |
| `AdminLog` | `admin_logs` | 管理日志 | → users |
| `LatexProject` | `latex_projects` | LaTeX 项目 | → users, latex_compile_history |
| `LatexTemplate` | `latex_templates` | LaTeX 模板 | 无关系 |
| `LatexCompileHistory` | `latex_compile_history` | 编译历史 | → latex_projects |

**约定**：所有模型使用 `String(36)` UUID 主键，`DateTime(timezone=True)` 时间戳，`JSONB` 带 `server_default`。枚举使用 `native_enum=False` 存储字符串值。

#### 3.7.2 Alembic 迁移

- 配置：`backend/alembic.ini`，`backend/alembic/env.py`
- 28 个迁移（`001_initial` → `028_reference_library_rebuild`）
- `init_db()` 仅创建 `vector` 扩展，表创建由迁移驱动
- `migration_bootstrap.py` 处理 pre-Alembic 数据库的 stamp 兼容

### 3.8 执行沙箱

**文件**：`src/execution/`、`src/sandbox/`

支持两种沙箱提供者：
- **Docker**: 容器化隔离执行（Python 绘图、Mermaid 图、AI 图像生成）
- **Local**: 本地进程执行（开发环境）

**执行类型**（`ExecutionType`）：
- `PYTHON_PLOT`: Python 数据可视化（matplotlib/seaborn）
- `MERMAID_DIAGRAM`: Mermaid 流程图
- `AI_IMAGE`: AI 图像生成
- `LATEX`: LaTeX 编译（通过 TeXLive Docker 容器）

**安全层**：`latex_sanitizer.py`、`python_sanitizer.py` 在执行前清洗用户代码。

---

## 4. 前端架构

### 4.1 技术栈

| 类别 | 技术 |
|------|------|
| 框架 | Next.js 16 (App Router), React 19, TypeScript |
| 状态管理 | Zustand 5 |
| 样式 | Tailwind CSS 3.4 + CSS Variables 设计系统 |
| 动画 | Framer Motion 12 |
| UI 基础 | Radix UI Primitives + 自定义组件 |
| 图标 | Lucide React |
| Markdown | react-markdown + remark-gfm |
| PDF | pdfjs-dist |
| I18n | next-intl |
| HTTP | axios |
| 测试 | Vitest 4 |

### 4.2 目录结构

```
frontend/
├── app/                          # Next.js 15 App Router
│   ├── layout.tsx                # 根布局：字体、I18nProvider
│   ├── page.tsx                  # 落地页（Hero、理念、工作区类型）
│   ├── globals.css               # 全局样式、CSS 变量、自定义动画
│   ├── (auth)/                   # 认证路由组
│   │   ├── login/page.tsx
│   │   └── register/page.tsx
│   ├── (workbench)/              # 主应用路由组
│   │   └── workspaces/[id]/
│   │       ├── layout.tsx        # WorkbenchLayout: 侧边栏 + 事件流 + Store 注水
│   │       ├── page.tsx          # Workspace 仪表盘（Hero、功能卡片、Inspector）
│   │       ├── chat/page.tsx     # 聊天界面（ThreadPanel + WorkspaceInspector）
│   │       └── components/       # 工作区专属组件
│   │           ├── ThreadPanel.tsx
│   │           ├── WorkspaceInspector.tsx
│   │           ├── WorkspaceThreadMessages.tsx
│   │           ├── WorkspaceThreadComposer.tsx
│   │           ├── thread-blocks/# 结构化消息块
│   │           └── ...
│   ├── latex/[projectId]/page.tsx # LaTeX 编辑器
│   ├── latex/page.tsx            # LaTeX 项目列表
│   └── workspaces/page.tsx       # 工作区列表
├── components/
│   ├── ui/                       # 原子 UI 组件
│   ├── glass/                    # 玻璃态效果组件
│   ├── layout/                   # 布局组件（Header 等）
│   ├── auth/                     # 认证相关
│   ├── workspace/                # 共享工作区组件
│   ├── compute/                  # Compute Stage 组件
│   └── latex/                    # LaTeX 编辑器子组件
├── stores/                       # Zustand 状态库
│   ├── workspace.ts
│   ├── thread.ts
│   ├── compute.ts
│   ├── execution.ts
│   ├── features.ts
│   ├── auth.ts
│   ├── latex.ts
│   ├── dashboard.ts
│   └── locale.ts
├── lib/                          # 工具库
│   ├── api/                      # API 层
│   │   ├── client.ts             # axios 实例 + authorizedFetch
│   │   ├── types.ts              # 所有 API TypeScript 类型（~1280 行）
│   │   ├── workspace.ts          # 工作区 API
│   │   ├── threads.ts            # 线程 API
│   │   ├── streams.ts            # 流式 API
│   │   ├── compute.ts            # Compute API
│   │   ├── latex.ts              # LaTeX API
│   │   ├── runs.ts               # Run API
│   │   └── ...
│   ├── workspace-feature-*.ts    # 功能路由、动作解析、阶段逻辑
│   └── thread-*.ts               # 线程工具（技能状态、Token 用量等）
├── hooks/                        # React Hooks
│   ├── useWorkspaceEventStream.ts # SSE 事件处理
│   └── ...
├── locales/                      # i18n JSON（cn.json, en.json）
└── tests/unit/                   # Vitest 单元测试
```

### 4.3 App Router 结构

| 路由 | 用途 |
|------|------|
| `/` | 营销落地页 |
| `/workspaces` | 工作区列表、搜索、创建 |
| `/workspaces/:id` | 工作区仪表盘（功能卡片 + Inspector）|
| `/workspaces/:id/chat` | 聊天线程界面（主要交互面）|
| `/latex` | LaTeX 项目列表 |
| `/latex/:projectId` | LaTeX 编辑器（Prism）|

**布局层次**：
```
app/layout.tsx (RootLayout: 字体 + I18nProvider)
  └── app/(workbench)/workspaces/[id]/layout.tsx (WorkbenchLayout)
        ├── 挂载 useWorkspaceEventStream(workspaceId) 实时更新
        ├── 注水所有相关 Store
        └── 卸载时清理（防止跨工作区数据残留）
```

### 4.4 状态管理（Zustand）

10 个独立 Store，每个管理一个领域：

| Store | 关键状态 | 用途 |
|-------|----------|------|
| `useWorkspaceStore` | `workspace`, `artifacts`, `references`, `activities` | 工作区数据、产物、文献库 |
| `useThreadStore` | `messages`, `isStreaming`, `threadId`, `currentSkill` | 聊天线程生命周期、流式输出 |
| `useExecutionStore` | `byWorkspace[workspaceId]`, `activeExecutionIdByWorkspace` | 执行会话、任务摄取、子 Agent 追踪 |
| `useComputeStore` | `byWorkspace[workspaceId]`, `projectionBySessionId` | Compute Session 及富投影 |
| `useFeaturesStore` | `features`, `skills`, `featuresByWorkspace` | 工作区功能/技能 |
| `useAuthStore` | `user`, `accessToken`, `isAuthenticated` | 认证（zustand/persist + cookie 同步）|
| `useLatexStore` | `project`, `tree`, `activeFilePath`, `fileChanges` | LaTeX 编辑器完整状态 |
| `useDashboardStore` | `summary` | 工作区摘要/进度 |
| `useLocaleStore` | `locale` | i18n 语言 |

**跨 Store 交互模式**：
- Store 之间**不直接依赖**；跨 Store 读取发生在组件/Hook 中
- `useWorkspaceEventStream` 作为**事件分发器**，根据 SSE 事件调用多个 Store
- Thread/Execution/Compute Store 使用**工作区作用域的键控状态**（`byWorkspace[workspaceId]`）支持快速切换不丢数据

### 4.5 组件架构

#### 4.5.1 聊天页面

```
ThreadPageInner
├── ThreadPanel
│   ├── WorkspaceThreadHeader
│   ├── WorkspaceProjectStatusStrip
│   ├── WorkspaceThreadMessages (可滚动)
│   │   └── MessageBubble (user | assistant)
│   │       ├── ReasoningPanel (可折叠)
│   │       ├── MarkdownRenderer
│   │       └── Structured Blocks (text, status_line, question_card, result_card, ...)
│   └── WorkspaceThreadComposer
│       ├── ModelSelector, ReasoningEffortSelector
│       ├── 附件上传（PDF/图片）
│       └── 自适应高度文本框
└── WorkspaceInspector
    ├── 标签栏: work | outputs | sources | activity
    ├── TaskRuntimePanel（活跃执行状态）
    └── 内容面板:
        ├── ComputeStage（work 标签）
        ├── ArtifactLibrary（outputs 标签）
        ├── LiteraturePanel（sources 标签）
        └── KnowledgePanel（activity 标签）
```

#### 4.5.2 Compute Stage

```
ComputeStage
├── ComputeHeader（状态、执行信息）
├── TaskRuntimePanel（运行时块和指标）
├── SubagentPanel + TaskArtifactPanel（双列网格）
└── PrismPanel + SandboxFilePanel + LogPanel + ReviewGatePanel（四列网格）
```

#### 4.5.3 Thread Block 系统

消息可包含类型化的 `blocks`，渲染为专用卡片。AgentBlock 协议定义 4 种核心类型：

| Block 类型 | 用途 |
|------------|------|
| `text` | 普通文本内容 |
| `status_line` | 实时状态/进度指示 |
| `question_card` | 请求用户输入的交互卡片 |
| `result_card` | 已完成任务的结果展示 |

其他辅助 block 类型：

| Block 类型 | 用途 |
|------------|------|
| `context_brief` | 工作区上下文摘要 |
| `warning` | 错误/警告横幅 |
| `artifacts` | 文件下载列表 |
| `reasoning` | 思考过程（可折叠）|

### 4.6 API 层

**双客户端模式**：
- `apiClient`（axios）：标准 REST，含拦截器（401 自动刷新、token 注入）
- `authorizedFetch()`：流式/SSE 专用，手动 token 刷新

**类型中心化**：所有 API TypeScript 类型集中在 `lib/api/types.ts`（~1280 行），作为前后端契约。

**错误处理**：401 自动刷新使用 `refreshPromise` 单例防止双刷；错误提取检查 `detail`、`message`、`error.message` 字段。

### 4.7 实时事件（SSE）

**双 SSE 通道**：

1. **线程流** (`streamThread`):
   - `POST /threads/:id/runs/stream` 或 `POST /runs/stream`
   - 事件：`content`, `reasoning`, `assistant_message`, `thread_id`, `error`, `done`
   - 支持**断线续传**：提取 `run_id`，使用 `Last-Event-ID` 重连（最多 3 次）

2. **工作区事件** (`subscribeWorkspaceEvents`):
   - `GET /workspaces/:id/events`
   - 处理事件：
     - `task.updated` → execution store + activity
     - `thread.status` → thread status
     - `thread.updated/deleted` → thread summary 同步
     - `execution.created/updated/completed/failed` → execution upsert
     - `compute.created/updated` → compute session upsert + projection fetch
     - `subagent.updated` → subagent state append
     - `workspace.refresh` → 定向 Store 重新获取
   - **自动重连**：指数退避（1.5s → 60s 上限），成功消息后重置

---

## 5. 基础设施与部署

### 5.1 Docker Compose 服务拓扑

```
┌─────────────────────────────────────────────────────────────┐
│                        Host (Port 2026)                      │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                      Nginx (80)                        │  │
│  │  • 反向代理、限流、SSE 无缓冲规则                        │  │
│  └────────────┬──────────────────────┬───────────────────┘  │
│               │                      │                       │
│      ┌────────▼──────┐    ┌─────────▼────────┐              │
│      │   Frontend    │    │     Gateway      │              │
│      │  Next.js 3000 │    │   FastAPI 8001   │              │
│      └───────────────┘    └─────────┬────────┘              │
│                                     │                        │
│                           ┌─────────▼────────┐              │
│                           │     Worker       │              │
│                           │  Celery Worker   │              │
│                           │  (metrics: 9153) │              │
│                           └─────────┬────────┘              │
│                                     │                        │
│  ┌──────────────────────────────────┼────────────────────┐  │
│  │         数据与消息层              │                    │  │
│  │  ┌─────────────┐  ┌─────────────┐│  ┌──────────────┐  │  │
│  │  │  PostgreSQL │  │    Redis    ││  │   Prometheus │  │  │
│  │  │  pg16+vector│  │  7 (AOF)    ││  │   (scrapes)  │  │  │
│  │  │   :5432     │  │   :6379     ││  └──────┬───────┘  │  │
│  │  └─────────────┘  │  /0 /1 /2   ││         │          │  │
│  │                   └─────────────┘│  ┌──────▼───────┐  │  │
│  │                                  │  │    Grafana   │  │  │
│  │  ┌─────────────┐                 │  │   :3001      │  │  │
│  │  │  TeXLive    │                 │  └──────────────┘  │  │
│  │  │  (LaTeX)    │                 │                    │  │
│  │  └─────────────┘                 └────────────────────┘  │
│  └──────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────┘
```

### 5.2 数据存储

#### PostgreSQL 16 + pgvector
- **镜像**: `pgvector/pgvector:pg16`
- **角色**: 业务数据持久化
- **连接**: SQLAlchemy async (`asyncpg`)，Gateway 和 Worker 共用

#### Redis 8
- **镜像**: `redis:8-alpine`，AOF 持久化（`appendonly yes`, `appendfsync everysec`）
- **逻辑库分区**：
  - **`/0`**: 应用运行时状态（任务、运行、pub/sub、锁、缓存、限流、SSE 缓冲）
  - **`/1`**: Celery Message Broker
  - **`/2`**: Celery Result Backend
- **连接模型**: `RedisClient` 维护两个连接池：
  - `client`: 通用 KV/Hash/Lock 操作（默认 max 50）
  - `stream_client`: SSE / PubSub 专用（默认 max 200）
- **关键键模式**：
  - `task:{task_id}` — 任务运行时 Hash
  - `runtime:runs:{run_id}` — 运行元数据
  - `runtime:runs:stream:{run_id}` — 运行事件 Redis Stream
  - `workspace:{workspace_id}:events` — 工作区事件 pub/sub
  - `lock:workspace:{workspace_id}:write` — 分布式写锁

### 5.3 Nginx 配置

- **限流**: `general` 区（100r/s）前端；`api` 区（30r/s）API
- **SSE/流式**: 专用 location，`proxy_buffering off`，`proxy_cache off`，24 小时超时
- **静态资源**: `/_next/static/` 缓存 365 天
- **健康检查**: `/livez`（Nginx 自身），`/readyz` 和 `/health` 代理到 Gateway

### 5.4 监控

#### Prometheus
- **配置**: `monitoring/prometheus.yml`
- **抓取目标**: Gateway (`gateway:8001/metrics`) + Worker (`worker:9153/metrics`)
- **自定义指标**: `run_dispatch_total`、`run_wait_seconds`、`task_duration_seconds`

#### Grafana
- **端口**: `3001`
- **自动配置**: 启动时从 `monitoring/grafana/provisioning/` 加载数据源和仪表盘

### 5.5 启动脚本

**`start.sh`**（本地开发编排器）：
- 模式：`--init`, `--backend`, `--worker`, `--frontend`, `--langgraph`, `--stop`, `--status`, `--logs`
- 自动回退容器：若宿主机 PostgreSQL/Redis 不可用，自动启动 `wenjin-local-postgres`（55432）和 `wenjin-local-redis`（56379）
- 迁移：启动时运行 `migration_bootstrap`
- 健康检查：HTTP 就绪前循环等待

**`scripts/doctor.py`**: 环境健康检查（Python ≥3.12、Node ≥20、Docker、配置有效性、网络连通性）

**`scripts/setup_wizard.py`**: 交互式终端向导，创建 `.env` 文件

### 5.6 CI/CD

- **`backend-quality.yml`**: Python 3.13 → `uv sync --extra dev` → `ruff check` → `pytest -q` → `mypy`
- **`frontend-unit-tests.yml`**: Node 22 → `npm ci` → `npm test`
- 并发组：同一 PR/分支有新提交时取消进行中的运行

---

## 6. 数据流详解

### 6.1 完整执行链路：用户发送消息 → 执行完成

```
[前端] WorkspaceThreadComposer.handleSubmit()
    │
    ▼
[前端] threadStore.sendMessage() → streamThread(payload, callbacks)
    │
    ▼
[HTTP] POST /threads/:id/runs/stream
    │
    ▼
[后端] Gateway → ThreadTurnHandler / RunLifecycle
    │
    ▼
[后端] lead_agent (create_react_agent) 处理所有 chat turns
    │     ├─ 纯聊天 → LLM 直接响应
    │     └─ 功能意图 → 调用 launch_feature tool → FeatureIngressService.launch()
    │
    ▼
[后端] FeatureIngressService
    │     1. 解析功能 ID 和参数
    │     2. 创建 ExecutionSession (status=launching)
    │     3. 确保 ComputeSession 存在
    │     4. 调用 FeatureSubmissionService.execute()
    │
    ▼
[后端] Celery 任务入队 (workspace_feature)
    │
    ▼
[Worker] workspace_feature_handler.execute_workspace_feature()
    │     1. 更新 ExecutionSession.status = running
    │     2. 调用 FeatureLeaderRuntime.execute_feature()
    │        ├─ [若 COMPUTE_AGENTIC] 动态子 Agent 工作流
    │        └─ LangGraph 子图执行
    │     3. 收集产物和结果
    │     4. TaskStore.mark_task_completed()
    │        ├─ 更新 ExecutionSession (status=completed, artifacts, next_actions)
    │        ├─ 发布 workspace events
    │        └─ 计费结算
    │
    ▼
[后端] ExecutionSessionService.update_session_record()
    │     → 延迟导入 ComputeSessionService
    │     → touch_session_by_execution()
    │     → 发布 compute.updated 事件
    │
    ▼
[前端] useWorkspaceEventStream 接收事件
    │     ├─ execution.updated → executionStore.upsertExecution()
    │     ├─ compute.updated → computeStore.upsertComputeSession() + 拉取投影
    │     └─ workspace.refresh → 定向 Store 重新获取
    │
    ▼
[前端] ComputeStage 重新渲染
    │     → 显示 runtime_blocks、产物、日志、Prism 状态、审查门
    │
    ▼
[前端] Thread 消息追加 LLM 回复（通过 SSE 流）
```

### 6.2 SSOT 刷新机制

```
ExecutionSession 状态变更
    │
    ▼
ExecutionSessionService.update_session_record()
    │
    ▼
延迟导入 ComputeSessionService(self.db)
    │     （避免 execution_session_service → compute → projection_service →
    │      runtime_profiles → registry → task → store → compute 循环依赖）
    ▼
ComputeSessionService.touch_session_by_execution(execution_session_id)
    │
    ▼
get_by_execution_session_id() → 找到对应 ComputeSession
    │
    ▼
touch_session(compute_session_id)
    │     1. updated_at = now()
    │     2. 可选合并 ui_state_delta
    │     3. commit + refresh
    │     4. 发布 compute.updated 事件
    │
    ▼
前端事件流接收 compute.updated
    │
    ▼
ComputeStore 更新 → 触发投影重新获取
    │
    ▼
ComputeProjectionService.get_projection() (按需 API)
    │     从 ExecutionSession.runtime_snapshot 构建投影
    │
    ▼
前端 Compute Stage 刷新
```

---

## 7. 关键设计决策

| 决策 | 理由 |
|------|------|
| **ExecutionSession / ComputeSession 分离** | 防止前端工作面污染后端业务状态；ComputeSession 只做 UI 投影 |
| **事件驱动刷新而非实时推送投影** | ComputeProjectionService 按需构建投影，不维护实时副本，降低复杂度 |
| **Redis + PG 双写任务状态** | Redis 支持前端快速轮询，PG 支持持久化和恢复 |
| **懒加载 LangGraph 子图** | 按 workspace_type 动态导入，一个领域的导入错误不影响其他领域 |
| **Agent Harness 合约** | 保留 Agent 执行边界，但当前只启用 Native Wenjin，避免未集成 provider 被误用 |
| **Runtime Blocks 作为 UI 契约** | 后端输出结构化 `runtime_blocks`，Compute Stage 通用渲染，无需前端为每个功能写定制代码 |
| **Reference Library 作为 grounded evidence** | 所有文献检索经 Semantic Scholar 验证；LLM 综合只能引用已验证文献，防止幻觉引用 |
| **延迟导入打破循环依赖** | `compute → projection_service → runtime_profiles → registry → task → store → compute` 链通过方法内延迟导入打破 |
| **Celery Worker fork 安全** | Worker 进程在 `worker_process_init` 重置 DB 引擎，避免 asyncio 事件循环泄漏 |
| **FeatureIngress 统一入口** | 所有功能执行必须经过 `FeatureIngressService`，禁止直接调用 handler，确保 SSOT 一致性 |

---

## 8. 开发规范

### 8.1 后端规范

- **Python 版本**: 3.13+
- **代码风格**: Ruff（lint + format）
- **类型检查**: mypy（增量检查）
- **测试**: pytest（以 release gate 与 targeted suites 为准）
- **模型**: 所有表使用 `String(36)` UUID 主键，`DateTime(timezone=True)`，`JSONB` 带 `server_default`
- **枚举**: `StrEnum` + `Enum(..., native_enum=False)` 存储字符串值
- **删除策略**: `WorkspaceReference` 使用 `is_deleted` 软删除；其他实体通常使用硬删除 + CASCADE
- **时间戳**: 统一使用 `datetime.now(UTC)`
- **命名**: handler key 格式为 `{workspace_type}.{feature_id}`（如 `thesis.deep_research`）
- **内部参数**: 以 `__` 为前缀的参数（`__thread_context_focus`、`__leader_workflow`）保留用于线程 → 功能 → Agent 的内部上下文传递

### 8.2 前端规范

- **Next.js**: App Router，`"use client"` 仅在需要 hooks/stores/router 时使用
- **状态**: Store selector 使用内联 lambda：`useThreadStore((s) => s.messages)`
- **类型**: 所有 API 类型集中在 `lib/api/types.ts`
- ** Barrel 导出**: 每个域使用 `index.ts` 简化导入
- **性能**: `useMemo` 用于派生选择，`useRef` 用于滚动目标和初始化守卫
- **错误**: API 客户端将错误规范化为 `error.message`；组件内联显示错误横幅

---

## 9. 文档索引

| 文档路径 | 内容 |
|----------|------|
| `docs/README.md` | 文档索引和导航 |
| `docs/architecture/` | 技术栈、API 面、功能域架构、工作区执行流水线、ADRs |
| `docs/infrastructure/` | 部署运行手册、环境变量、故障排查指南 |
| `docs/product/` | 工作区当前状态、Reference Library、功能插件合约、工作区功能目录、发布门控检查表 |
| `docs/strategy/` | 长期方向 |
| `backend/docs/` | 后端专属文档 |
| `frontend/README.md` | 前端专属文档 |
