# 问津 (Wenjin) 系统架构文档

> 版本：2026-05-11
> 范围：全栈架构（后端、前端、基础设施）
> 读者：新加入的开发者、架构评审、运维人员

---

## 1. 项目概述

**问津 (Wenjin)** 是一个面向学术研究的 AI 工作台。它以 "工作区 (Workspace)" 为核心组织单元，支持学位论文、SCI 论文、项目申报书、软件著作权、专利等多种学术工作流。每个工作区包含：

- **Chat 控制面**（左面板）：以对话方式驱动研究、写作和修改，Chat Agent 处理意图识别与对话
- **Lead Agent 工作面**（右面板）：结构化展示能力执行进度、产物和结果，支持 LangGraph 子图实时可视化
- **8 个工作区房间 (Rooms)**：Library、Documents、Decisions、Memory、Run History、Sandbox、Tasks、Settings

### 1.1 核心原则

| 原则 | 含义 |
|------|------|
| **Two-Agent 拓扑** | Chat Agent（左面板）处理对话意图 + Lead Agent（右面板）运行能力执行，1:1 映射，lead-busy 阻塞新调度 |
| **Capability 数据驱动** | 能力定义通过 YAML seed + DB 存储，`CapabilityResolver` 加载并缓存，Admin 可运行时编辑 |
| **Output Mapping 声明式** | 能力 YAML 中的 `outputs` 声明经 `OutputMappingResolver` 解析为 5 种类型化 `ResultOutput`（library_item、document、memory_fact、decision、task） |
| **Curated result_card 流** | 执行产物先暂存 → 用户通过复选框审阅 → commit 写入房间，默认全选 + 一键"全部接受" |
| **7 种 Block 协议** | `text`、`thinking`、`status_line`、`question_card`、`result_card`、`tool_invocation`、`tool_result` — 按到达顺序存储 |
| **不保留旧链路 fallback** | 新主链路落地后，旧代码路径直接删除，不保留兼容层 |

---

## 2. 系统架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户浏览器                                       │
│  ┌──────────────────────────────┐  ┌─────────────────────────────────────┐  │
│  │  Next.js 前端 (Port 3000)    │  │  独立页面：/latex/:projectId         │  │
│  │  - Chat 面板 (左)             │  │  - WenjinPrism LaTeX 编辑器          │  │
│  │  - LiveWorkflow 面板 (右)     │  │                                      │  │
│  │  - 8 个 Rooms 面板            │  │                                      │  │
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
│  │  业务持久化   │   │  /1 Celery Broker │   │  - ExecutionEngine│             │
│  │              │   │  /2 Celery Backend│   │  - LeadAgentRuntime│            │
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
| **Agent 运行时** | LangGraph (in-process), v2 subagent registry + graph compiler |
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
│   ├── routers/          # 路由模块（含 executions.py、execution_commit.py、capabilities.py、workspace_rooms.py）
│   ├── deps/             # 依赖注入（get_db、ExecutionService 等）
│   ├── middleware/       # 关联 ID、错误处理、限流
│   └── validators/       # 请求体校验
├── database/             # SQLAlchemy 异步引擎、会话管理、ORM 模型
│   ├── session.py        # get_db_session() 上下文管理器、引擎工厂
│   ├── base.py           # DeclarativeBase + UUIDMixin + TimestampMixin
│   └── models/           # ORM 定义（含 Capability、ExecutionRecord 等）
├── services/             # 领域服务层
│   ├── references/       # 文献库：WorkspaceReferenceService、ReferenceBibTeXService、ReferenceEvidenceService
│   ├── latex/            # LaTeX：LatexProjectService、LatexCompileService、反馈改写 Diff
│   ├── rooms/            # 工作区房间服务（LibraryService、DocumentsService、DecisionsService、MemoryService、RunHistoryService、WorkspaceTasksService、SandboxService、SettingsService）
│   ├── capability_resolver.py        # CapabilityResolver：DB + 缓存加载能力定义
│   ├── capability_loader.py          # YAML seed → DB 加载
│   ├── execution_service.py          # ExecutionRecord 生命周期管理
│   ├── execution_commit_service.py   # 产物 commit：按 kind 路由到房间服务
│   ├── execution_event_publisher.py  # 执行事件 → Redis Stream + workspace events
│   ├── event_bus.py                  # Redis EventBus（发布/订阅）
│   └── ...               # 认证、计费、仪表盘、用户记忆等
├── workspace_features/   # 工作区功能注册与运行时画像
│   ├── registry.py       # 功能注册表（按 WorkspaceType 定义所有功能）
│   ├── runtime_profiles.py          # 功能运行时画像（CHAT_ONLY / DETERMINISTIC / COMPUTE_WORKFLOW / COMPUTE_AGENTIC）
│   ├── contracts.py      # 功能执行结果标准化合约
│   ├── latex_sync.py     # LaTeX 桥接：sync_project / compile_thesis_payload
│   └── services/         # 各工作区类型的 payload builder 和 feature handler
├── agents/               # Agent 编排层
│   ├── lead_agent/       # Lead Agent v2
│   │   ├── agent.py      # Chat Agent 入口（create_react_agent）
│   │   ├── prompts/      # Chat Agent 系统提示词
│   │   ├── blocks.py     # 结构化 Block 输出（status_line、question_card 等）
│   │   ├── dynamic_tools.py          # 动态工具注册
│   │   ├── structured_output.py      # 结构化输出解析
│   │   └── v2/           # Lead Agent v2 核心运行时
│   │       ├── runtime.py           # LeadAgentRuntime：resolve → compile → execute → TaskReport
│   │       ├── compiler.py          # compile_graph()：graph_template → LangGraph StateGraph
│   │       └── output_mapping.py    # OutputMappingResolver：outputs 声明 → typed ResultOutput
│   ├── contracts/        # 任务合约
│   │   ├── task_brief.py            # TaskBrief：能力执行输入
│   │   └── task_report.py           # TaskReport + ResultOutput discriminated union（5 种 kind）
│   ├── middlewares/      # 20+ 中间件（沙箱、引用、知识、纠错、澄清等）
│   ├── memory/           # 记忆捕获与压缩
│   └── subagents/        # v2 子 Agent
│       └── v2/
│           ├── base.py              # SubagentBase 基类（SubagentContext + SubagentResult）
│           ├── registry.py          # 全局 REGISTRY：name → SubagentBase 子类
│           └── types/               # 5 个内置子 Agent
│               ├── scholar_searcher.py
│               ├── critical_writer.py
│               ├── outliner.py
│               ├── clusterer.py
│               └── web_searcher.py
├── task/                 # 任务系统
│   ├── celery_app.py     # Celery 应用配置（队列、路由、序列化）
│   ├── worker.py         # Worker 进程生命周期（fork 安全、MCP 启动、Prometheus）
│   ├── store.py          # TaskStore：Redis + PG 双写
│   ├── registry.py       # 任务类型注册
│   ├── tasks/            # Celery 任务定义
│   │   ├── execution.py  # execute_execution：v2 执行入口（ExecutionEngineV2 → LeadAgentRuntime）
│   │   ├── run.py        # run 任务
│   │   ├── memory.py     # memory 任务
│   │   └── base.py       # 基础任务
│   ├── handlers/         # 任务处理器（document_preprocess、reference_preprocess）
│   └── runtime_blocks.py # 结构化运行时状态块
├── execution/            # 执行运行时
│   ├── engine.py         # ExecutionEngineV2：统一执行引擎（替代旧 ChatExecutionEngine + FeatureExecutionEngine）
│   ├── service.py        # ExecutionService：DB 层 CRUD
│   ├── providers/        # Docker / Local 沙箱提供者
│   ├── security/         # LaTeX / Python 代码安全清洗
│   └── types.py          # ExecutionType 枚举
├── academic/             # 学术领域服务
│   ├── literature/       # Semantic Scholar 集成、文献检索
│   ├── citation/         # BibTeX / APA / MLA / Chicago / IEEE 格式化
│   └── services/         # ArtifactService、GenerationService
├── tools/                # 工具层
│   └── builtins/         # 内置工具（文件操作、bash、文献查询、launch_feature 等）
├── runtime/              # Run 运行时
│   ├── runs/manager.py   # RunManager：Redis 支持的运行恢复
│   └── stream_bridge/    # Redis Stream 桥接（SSE 多路复用）
├── application/          # 应用编排层
│   ├── handlers/         # ThreadTurnHandler
│   └── services/         # 服务编排
├── mcp/                  # Model Context Protocol 运行时和工具注册
├── models/               # 模型路由（LLM provider 选择和调用）
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
| `executions.py` | `/api/executions` | 执行记录 CRUD + 状态查询 |
| `execution_commit.py` | `/api/executions/{id}/commit` | 产物 commit（按 kind 路由到房间） |
| `capabilities.py` | `/api/capabilities` | 能力 CRUD + 校验 |
| `workspace_rooms.py` | `/api/workspace_rooms` | 工作区房间数据（Library、Documents 等） |
| `compute.py` | `/api/compute` | Compute Session 查询和投影 |
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

**依赖注入**：`src/gateway/deps/core.py` 提供 `get_db()`（异步会话上下文管理器）。更高层的依赖通过嵌套 `Depends()` 链组装。

### 3.3 SSOT 核心

#### 3.3.1 ExecutionSession — 业务状态事实源

**文件**：`src/database/models/execution_session.py`、`src/services/execution_session_service.py`

**职责**：一个功能执行（如"撰写第三章"）的完整生命周期状态机。所有业务状态变更（启动→运行→完成/失败/等待输入）都记录在此。

**核心字段**：
- `id` (UUID), `user_id`, `workspace_id`, `workspace_type`, `feature_id`
- `status`: `launching` → `running` → `completed` / `failed` / `advisory` / `awaiting_user_input`
- `params`: 用户传入参数（含 `brief` 子对象）
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
- **队列**: `default`（通用功能）、`long_running`（执行引擎、文档/文献预处理）、`priority`
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
| `execute_execution` | `long_running` | 600s | `execution.py` → `ExecutionEngineV2` → `LeadAgentRuntime` |
| `document_preprocess` | `long_running` | 900s | `document_preprocess_handler.py` |
| `reference_preprocess` | `long_running` | 1200s | `reference_preprocess_handler.py` |

### 3.5 Agent / Capability 架构

#### 3.5.1 Two-Agent 拓扑

系统采用双 Agent 架构，1:1 映射到前端双面板布局：

- **Chat Agent**（左面板）：基于 `create_react_agent` 构建，处理所有用户对话。识别到能力意图时调用 `launch_feature` 工具。
- **Lead Agent v2**（右面板）：`LeadAgentRuntime` 在 Celery Worker 中执行能力。通过 `CapabilityResolver` 加载能力定义 → `compile_graph()` 编译为 LangGraph → 执行子 Agent 图 → 收集结果为 `TaskReport`。

**Lead-busy 互斥**：`launch_feature` 工具在调度前检查工作区是否有 `pending/running` 状态的执行，若有则返回 `advisory: lead_busy`，前端展示状态提示。

#### 3.5.2 Capability 数据模型

**定义来源**：YAML seed 文件（`backend/seed/capabilities/{workspace_type}/`）+ DB 持久化（`capabilities` 表）

**加载与缓存**：`CapabilityResolver`（`src/services/capability_resolver.py`）
- 按 `(capability_id, workspace_type)` 查询 DB，带内存缓存
- 通过 `EventBus` 订阅 `capability.invalidated` 事件自动清缓存
- `validate_capability()` 校验 graph_template 结构、subagent_type 注册、outputs 声明完整性、模板变量合法性

**能力结构**（graph_template）：
```yaml
graph_template:
  phases:
    - name: discovery
      tasks:
        - name: scholar_search
          subagent_type: scholar_searcher
          prompt_template: "搜索关于 {{topic}} 的文献..."
          outputs:
            - kind: library_item
              iterate_on: output.papers
              mapping:
                title: "{{item.title}}"
                authors: "{{item.authors}}"
    - name: synthesis
      depends_on: [discovery]
      tasks:
        - name: write_draft
          subagent_type: critical_writer
          outputs:
            - kind: document
              mapping:
                name: "综述报告"
                mime_type: "text/markdown"
```

#### 3.5.3 Graph Compiler

**文件**：`src/agents/lead_agent/v2/compiler.py`

`compile_graph()` 将能力的 `graph_template` 编译为 LangGraph `CompiledStateGraph`：

1. 为每个 task 添加 LangGraph 节点，命名为 `{phase}__{task}`
2. 从 `REGISTRY` 查找 `subagent_type` 对应的 `SubagentBase` 子类
3. 连线 `START` → 根阶段（无 `depends_on`）→ 依赖阶段（fan-in/fan-out）→ 终端阶段 → `END`
4. 可选注入 `abort_check`（检查 Redis abort 信号）
5. 支持重试：`retry_on_failure` 指定额外的重试次数

#### 3.5.4 Lead Agent v2 Runtime

**文件**：`src/agents/lead_agent/v2/runtime.py`

`LeadAgentRuntime.run_session()` 是**所有能力执行的规范路径**：

1. 通过 `CapabilityResolver.resolve()` 加载能力定义
2. 发布 `execution.graph_structure` 事件（节点 + 边结构，前端可视化用）
3. 组装 `ExecutionState`（workspace_id、inputs_for_tasks、workspace_data、node_results）
4. 编译 graph_template → LangGraph，执行 `graph.ainvoke()`
5. 收集节点错误（`failed_partial` 状态）
6. 通过 `OutputMappingResolver` 解析 outputs 声明 → `ResultOutput` 列表
7. 构建 `TaskReport`（status、duration、token_usage、narrative、outputs、errors）
8. 发布 `execution.completed` 事件

**状态**：`ExecutionState`（TypedDict）— LangGraph 状态贯穿所有子 Agent 节点

#### 3.5.5 Output Mapping

**文件**：`src/agents/lead_agent/v2/output_mapping.py`

`OutputMappingResolver` 将 YAML 中的 `outputs` 声明解析为类型化的 `ResultOutput` 对象：

| Kind | 数据模型 | 目标房间 |
|------|----------|----------|
| `library_item` | `LibraryItemData`（title、authors、year、doi、url、abstract） | Library |
| `document` | `DocumentData`（name、mime_type、storage_path、size_bytes） | Documents |
| `memory_fact` | `MemoryFactData`（content、category、confidence） | Memory |
| `decision` | `DecisionData`（key、value、confidence） | Decisions |
| `task` | `TaskData`（title、description、priority） | Tasks |

**模板解析**：支持 `{{output.field}}` 和 `{{item.field}}` 表达式（纯模板保留类型，插值模板返回字符串）。`iterate_on` 支持数组展开。

#### 3.5.6 Task Contracts

**文件**：`src/agents/contracts/`

- **TaskBrief**（`task_brief.py`）：能力执行输入 — `capability_id`、`workspace_id`、`brief`（用户参数字典）
- **TaskReport**（`task_report.py`）：能力执行输出 — `execution_id`、`capability_id`、`status`（completed/failed_partial/cancelled）、`duration_seconds`、`token_usage`、`narrative`、`outputs`（`ResultOutput` discriminated union 列表）、`errors`

#### 3.5.7 Execution Engine

**文件**：`src/execution/engine.py`

`ExecutionEngineV2` 是统一执行引擎，替代旧的 ChatExecutionEngine + FeatureExecutionEngine：

1. 通过 `ExecutionService.get_by_id()` 获取 ExecutionRecord
2. 调用 `ExecutionService.start_execution()` 标记 running
3. 从 `execution.params["brief"]` 构造 `TaskBrief`
4. 调用 `LeadAgentRuntime.run_session()` 执行能力
5. 通过 `ExecutionService.complete_execution()` 持久化 `TaskReport`
6. 通过 `RunHistoryService.record()` 记录运行历史
7. 失败时标记 execution 为 failed 并 re-raise

#### 3.5.8 v2 Subagent Registry

**文件**：`src/subagents/v2/registry.py`、`src/subagents/v2/types/`

全局 `REGISTRY` 单例（`_Registry`），通过 `@subagent("name")` 装饰器注册 `SubagentBase` 子类：

| 注册名 | 文件 | 用途 |
|--------|------|------|
| `scholar_searcher` | `types/scholar_searcher.py` | 学术文献检索 |
| `critical_writer` | `types/critical_writer.py` | 批判性写作 |
| `outliner` | `types/outliner.py` | 大纲生成 |
| `clusterer` | `types/clusterer.py` | 文献聚类 |
| `web_searcher` | `types/web_searcher.py` | 网络搜索 |

每个子 Agent 接收 `SubagentContext`（workspace_id、execution_id、prompt、inputs、tools），返回 `SubagentResult`（output、thinking、tool_calls、token_usage）。

#### 3.5.9 中间件栈

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
| **PROPOSAL** | background_research, experiment_design, proposal_outline, figure_generation |
| **SOFTWARE_COPYRIGHT** | technical_description, copyright_materials, figure_generation |
| **PATENT** | patent_outline, prior_art_search, figure_generation |

每个功能定义包含：`workspace_type`、`id`、`name`、`agent`、`handler_key`、`task_type`、`panel`、`stages` 等。

#### 3.6.2 运行时画像

**文件**：`src/workspace_features/runtime_profiles.py`

`FeatureRuntimeProfile` 决定执行模式：

| 模式 | 说明 |
|------|------|
| `CHAT_ONLY` | 简单聊天响应，无计算工作流 |
| `DETERMINISTIC` | 确定性 handler，无 Agent |
| `COMPUTE_WORKFLOW` | 标准计算工作流（默认） |
| `COMPUTE_AGENTIC` | 进入 LeadAgentRuntime，子 Agent 扇出 |

关键覆盖：
- 调研类功能 → `COMPUTE_AGENTIC`，最多 4 个研究子 Agent
- `figure_generation`（所有类型）→ `COMPUTE_AGENTIC` + `requires_sandbox=True` + review gate `artifact_preview`

#### 3.6.3 能力执行数据流

```
用户请求 (Chat 消息)
    ↓
Chat Agent 处理 → 识别能力意图 → 调用 launch_feature 工具
    ↓
launch_feature:
    1. Lead-busy 检查（工作区 pending/running 执行）
    2. 创建 ExecutionRecord (status=pending)
    3. 发布 execution.updated 工作区事件
    4. 调度 execute_execution Celery 任务 (queue=long_running)
    ↓
Celery Worker: execute_execution
    ↓
ExecutionEngineV2.run(execution_id)
    1. ExecutionService.start_execution() → running
    2. 构造 TaskBrief
    ↓
LeadAgentRuntime.run_session()
    1. CapabilityResolver.resolve() → 加载 graph_template
    2. 发布 execution.graph_structure 事件
    3. compile_graph() → LangGraph StateGraph
    4. graph.ainvoke() → 子 Agent 并行/串行执行
    5. OutputMappingResolver.resolve() → ResultOutput 列表
    6. 构建 TaskReport
    7. 发布 execution.completed 事件
    ↓
ExecutionEngineV2:
    1. ExecutionService.complete_execution() → 持久化 TaskReport
    2. RunHistoryService.record() → 记录运行历史
    ↓
前端接收 execution.completed SSE 事件
    ↓
ChatPanel: useChatStream 桥接 → 渲染 ResultCard
    ↓
用户审阅 ResultCard → 复选框选择 → POST /api/executions/{id}/commit
    ↓
ExecutionCommitService.commit_outputs()
    → 按 kind 路由到对应房间服务（Library、Documents、Decisions、Memory、Tasks）
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
| `Capability` | `capabilities` | 能力定义（DB-backed）| 按 workspace_type 索引 |
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
| 样式 | Tailwind CSS 3.4 + `--v2-*` CSS Variables 设计系统（Glass/visionOS 风格） |
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
├── app/                          # Next.js 16 App Router
│   ├── layout.tsx                # 根布局：字体、I18nProvider
│   ├── page.tsx                  # 落地页（Hero、理念、工作区类型）
│   ├── globals.css               # 全局样式、--v2-* CSS 变量、自定义动画
│   ├── (auth)/                   # 认证路由组
│   │   ├── login/page.tsx
│   │   └── register/page.tsx
│   ├── (workbench)/              # 主应用路由组
│   │   └── workspaces/[id]/
│   │       ├── layout.tsx        # WorkbenchLayout: 侧边栏 + 事件流 + Store 注水
│   │       ├── page.tsx          # Workspace 仪表盘
│   │       ├── v2/               # v2 工作区页面（双面板布局）
│   │       │   ├── layout.tsx    # v2 布局：ChatPanel (左) + LiveWorkflowPanel (右)
│   │       │   ├── page.tsx      # v2 主页面
│   │       │   └── components/   # v2 专属组件
│   │       │       ├── ChatPanel.tsx          # 左面板：聊天交互
│   │       │       ├── LiveWorkflowPanel.tsx  # 右面板：执行可视化
│   │       │       ├── GraphCanvas.tsx        # LangGraph 节点图可视化
│   │       │       ├── PhaseNode.tsx          # 阶段节点组件
│   │       │       ├── NodeDetailDrawer.tsx   # 节点详情抽屉
│   │       │       ├── ResultCard.tsx         # 产物卡片（含 commit 复选框）
│   │       │       ├── MessageBlock.tsx       # 消息块渲染器
│   │       │       ├── ThinkingBlock.tsx      # 思考过程（可折叠）
│   │       │       ├── StatusLineBlock.tsx    # 状态行
│   │       │       ├── AutoCompactToast.tsx   # 自动压缩提示
│   │       │       ├── RoomsTopbar.tsx        # Rooms 顶部导航
│   │       │       └── rooms/                # 8 个房间组件
│   │       │           ├── LibraryDrawer.tsx
│   │       │           ├── DocumentsDrawer.tsx
│   │       │           ├── DecisionsViewer.tsx
│   │       │           ├── MemoryViewer.tsx
│   │       │           ├── RunsDrawer.tsx
│   │       │           ├── SandboxConsole.tsx
│   │       │           ├── TasksDrawer.tsx
│   │       │           └── SettingsForm.tsx / SettingsPage.tsx
│   │       └── components/       # 旧版组件（兼容过渡）
│   ├── latex/[projectId]/page.tsx # LaTeX 编辑器
│   ├── latex/page.tsx            # LaTeX 项目列表
│   └── workspaces/page.tsx       # 工作区列表
├── components/
│   ├── ui/                       # 原子 UI 组件
│   ├── glass/                    # 玻璃态效果组件
│   ├── layout/                   # 布局组件（Header 等）
│   ├── auth/                     # 认证相关
│   ├── workspace/                # 共享工作区组件
│   └── latex/                    # LaTeX 编辑器子组件
├── stores/                       # Zustand 状态库
│   ├── workspace.ts
│   ├── chat-store.ts             # v2 chat store（handleEvent + sendMessage + Block 协议）
│   ├── execution-store.ts        # v2 execution store（applyStreamEvent + node_states）
│   ├── compute.ts
│   ├── features.ts
│   ├── auth.ts
│   ├── latex.ts
│   ├── dashboard.ts
│   └── locale.ts
├── hooks/                        # React Hooks
│   ├── useChatStream.ts          # 桥接 execution.completed 事件到 chat store（ResultCard 渲染）
│   ├── useExecutionStream.ts     # 执行流事件处理
│   ├── useExecutionStreamV2.ts   # v2 执行流
│   ├── useWorkspaceEventStream.ts # SSE 事件处理
│   ├── useGlobalShortcuts.ts
│   └── useModelSelection.ts
├── lib/                          # 工具库
│   ├── api/                      # API 层
│   │   ├── client.ts             # axios 实例 + authorizedFetch
│   │   ├── types.ts              # 所有 API TypeScript 类型
│   │   └── ...
│   └── ...
├── locales/                      # i18n JSON（cn.json, en.json）
└── tests/unit/                   # Vitest 单元测试
```

### 4.3 App Router 结构

| 路由 | 用途 |
|------|------|
| `/` | 营销落地页 |
| `/workspaces` | 工作区列表、搜索、创建 |
| `/workspaces/:id` | 工作区仪表盘 |
| `/workspaces/:id/v2` | v2 双面板工作区（Chat + LiveWorkflow + Rooms） |
| `/latex` | LaTeX 项目列表 |
| `/latex/:projectId` | LaTeX 编辑器（Prism） |

**布局层次**：
```
app/layout.tsx (RootLayout: 字体 + I18nProvider)
  └── app/(workbench)/workspaces/[id]/layout.tsx (WorkbenchLayout)
        ├── 挂载 useWorkspaceEventStream(workspaceId) 实时更新
        ├── 注水所有相关 Store
        └── 卸载时清理（防止跨工作区数据残留）
```

**v2 双面板布局**：
```
v2/layout.tsx
  ├── ChatPanel (左) — 最小白底聊天，ChatGPT 风格
  └── LiveWorkflowPanel (右) — Glass/visionOS 风格面板
        ├── RoomsTopbar — 8 个房间标签导航
        ├── GraphCanvas — LangGraph 节点图可视化（@xyflow/react）
        └── 房间内容面板
```

### 4.4 状态管理（Zustand）

9 个独立 Store，每个管理一个领域：

| Store | 关键状态 | 用途 |
|-------|----------|------|
| `useChatStoreV2` | `messages`, `currentAssistantId`, `isSending` | v2 聊天生命周期：7 种 Block 类型，SSE 事件驱动 |
| `useExecutionStore` | `executions`, `currentExecutionId`, `node_states` | 执行记录、节点状态、graph_structure 可视化 |
| `useWorkspaceStore` | `workspace`, `artifacts`, `references`, `activities` | 工作区数据、产物、文献库 |
| `useComputeStore` | `byWorkspace[workspaceId]`, `projectionBySessionId` | Compute Session 及富投影 |
| `useFeaturesStore` | `features`, `skills`, `featuresByWorkspace` | 工作区功能/技能 |
| `useAuthStore` | `user`, `accessToken`, `isAuthenticated` | 认证（zustand/persist + cookie 同步）|
| `useLatexStore` | `project`, `tree`, `activeFilePath`, `fileChanges` | LaTeX 编辑器完整状态 |
| `useDashboardStore` | `summary` | 工作区摘要/进度 |
| `useLocaleStore` | `locale` | i18n 语言 |

**跨 Store 交互模式**：
- Store 之间**不直接依赖**；跨 Store 读取发生在组件/Hook 中
- `useWorkspaceEventStream` 作为**事件分发器**，根据 SSE 事件调用多个 Store
- `useChatStream` 桥接 `execution.completed` SSE 事件到 chat store，自动渲染 ResultCard

### 4.5 组件架构

#### 4.5.1 v2 双面板

```
v2/page.tsx
├── ChatPanel (左面板)
│   ├── 消息列表（可滚动）
│   │   └── MessageBlock → 根据 kind 渲染：
│   │       ├── text → MarkdownRenderer
│   │       ├── thinking → ThinkingBlock（可折叠）
│   │       ├── status_line → StatusLineBlock
│   │       ├── question_card → 交互卡片
│   │       ├── result_card → ResultCard（产物审阅 + commit）
│   │       ├── tool_invocation → 工具调用展示
│   │       └── tool_result → 工具结果展示
│   └── 输入框（自适应高度、附件上传）
└── LiveWorkflowPanel (右面板)
    ├── RoomsTopbar（8 个房间标签）
    ├── GraphCanvas（LangGraph 节点图）
    │   └── PhaseNode（阶段节点，含状态指示）
    ├── NodeDetailDrawer（节点详情、thinking、输出预览）
    └── 房间面板:
        ├── LibraryDrawer（文献库房间）
        ├── DocumentsDrawer（文档房间）
        ├── DecisionsViewer（决策房间）
        ├── MemoryViewer（记忆房间）
        ├── RunsDrawer（运行历史房间）
        ├── SandboxConsole（沙箱房间）
        ├── TasksDrawer（任务房间）
        └── SettingsForm（设置房间）
```

#### 4.5.2 Block 协议

消息可包含类型化的 `blocks`，渲染为专用卡片。7 种核心 block 类型：

| Block 类型 | 用途 |
|------------|------|
| `text` | 普通文本内容 |
| `thinking` | 思考过程（可折叠） |
| `status_line` | 实时状态/进度指示 |
| `question_card` | 请求用户输入的交互卡片 |
| `result_card` | 执行结果展示（含 commit 复选框） |
| `tool_invocation` | 工具调用展示（launch_feature 等） |
| `tool_result` | 工具返回结果 |

**存储约定**：blocks 严格按到达顺序存储，thinking 不做前置插入。

### 4.6 API 层

**双客户端模式**：
- `apiClient`（axios）：标准 REST，含拦截器（401 自动刷新、token 注入）
- `authorizedFetch()`：流式/SSE 专用，手动 token 刷新

**类型中心化**：所有 API TypeScript 类型集中在 `lib/api/types.ts`，作为前后端契约。

**错误处理**：401 自动刷新使用 `refreshPromise` 单例防止双刷；错误提取检查 `detail`、`message`、`error.message` 字段。

### 4.7 实时事件（SSE）

**双 SSE 通道**：

1. **线程流** (`streamThread`):
   - `POST /threads/:id/runs/stream` 或 `POST /runs/stream`
   - 事件：`content`, `reasoning`, `block`, `done`, `error`
   - 支持**断线续传**：提取 `run_id`，使用 `Last-Event-ID` 重连（最多 3 次）

2. **工作区事件** (`subscribeWorkspaceEvents`):
   - `GET /workspaces/:id/events`
   - 处理事件：
     - `execution.updated/created/completed/failed` → execution store upsert + applyStreamEvent
     - `execution.graph_structure` → graph_structure 更新（前端节点图渲染）
     - `execution.node.started/delta/completed/failed` → node_states 更新
     - `execution.status` → status + progress + message 更新
     - `compute.updated` → compute session upsert + projection fetch
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
  - `abort:exec:{execution_id}` — 执行取消信号

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

### 6.1 完整执行链路：用户发送消息 → 执行完成 → 产物 commit

```
[前端] ChatPanel 输入 → chatStore.sendMessage()
    │
    ▼
[HTTP] POST /api/threads → 确保线程存在
    │
    ▼
[HTTP] POST /api/threads/:id/runs/stream
    │
    ▼
[后端] Chat Agent (create_react_agent) 处理 SSE 流
    │     ├─ 纯聊天 → LLM 直接响应（content / reasoning / block 事件）
    │     └─ 能力意图 → 调用 launch_feature 工具
    │
    ▼
[后端] launch_feature 工具
    │     1. Lead-busy 检查（查询工作区 active executions）
    │     2. ExecutionService.create_execution() → ExecutionRecord (pending)
    │     3. 发布 execution.updated 工作区事件
    │     4. execute_execution.apply_async(queue=long_running)
    │     5. 返回 { status: "launched", execution_id }
    │
    ▼
[前端] SSE 流返回 → tool_invocation + tool_result blocks → 聊天界面展示
    │
    ▼
[Worker] execute_execution Celery 任务
    │     1. Fork 安全：重置 DB 引擎、连接 Redis
    │     2. 发布 execution.status(running) 事件
    │     3. 构造 CapabilityResolver + EventBus + LeadAgentRuntime
    │     4. ExecutionEngineV2.run(execution_id)
    │
    ▼
[Worker] ExecutionEngineV2.run()
    │     1. ExecutionService.start_execution() → status=running
    │     2. 从 execution.params["brief"] 构造 TaskBrief
    │     3. LeadAgentRuntime.run_session()
    │        ├─ CapabilityResolver.resolve(capability_id, workspace_type)
    │        ├─ 发布 execution.graph_structure 事件（节点 + 边）
    │        ├─ compile_graph(graph_template) → LangGraph StateGraph
    │        ├─ graph.ainvoke(initial_state)
    │        │   └─ 子 Agent 节点并行/串行执行
    │        │       ├─ SubagentBase.run(context) → SubagentResult
    │        │       └─ node_results[task_name] = { output, thinking, token_usage }
    │        ├─ OutputMappingResolver.resolve() → ResultOutput 列表
    │        └─ 构建 TaskReport
    │     4. ExecutionService.complete_execution() → 持久化 TaskReport
    │     5. RunHistoryService.record() → 运行历史记录
    │     6. 发布 execution.completed 事件
    │
    ▼
[前端] useWorkspaceEventStream 接收事件
    │     ├─ execution.graph_structure → executionStore (GraphCanvas 渲染)
    │     ├─ execution.node.started/completed/failed → node_states 更新
    │     └─ execution.completed → executionStore + useChatStream → ResultCard
    │
    ▼
[前端] ChatPanel 渲染 ResultCard
    │     → 展示 outputs 列表（preview + checkbox）
    │     → 用户选择要 commit 的产物
    │
    ▼
[HTTP] POST /api/executions/{id}/commit
    │     { accept_all: true } 或 { accepted_ids: [...] }
    │
    ▼
[后端] ExecutionCommitService.commit_outputs()
    │     → 按 kind 路由到房间服务：
    │        library_item → LibraryService
    │        document → DocumentsService
    │        memory_fact → MemoryService
    │        decision → DecisionsService
    │        task → WorkspaceTasksService
    │     → RunHistoryService 始终记录
    │     → 发布 workspace.refresh 事件
    │
    ▼
[前端] 对应房间面板刷新
```

### 6.2 SSOT 刷新机制

```
ExecutionRecord 状态变更（ExecutionService）
    │
    ▼
publish_execution_event()
    │     → Redis Stream (execution_id)
    │     → workspace events (workspace_id)
    │
    ▼
前端 SSE 事件流接收
    │
    ▼
executionStore.applyStreamEvent(event)
    │     → 根据 event.type 更新对应字段
    │        metadata → status/feature_id/progress
    │        graph_structure → nodes + edges
    │        node.started/completed/failed → node_states
    │        completed → result + completed_at
    │
    ▼
ChatPanel / LiveWorkflowPanel 重新渲染
```

---

## 7. 关键设计决策

| 决策 | 理由 |
|------|------|
| **Two-Agent 拓扑（Chat + Lead）** | Chat Agent 处理对话与意图，Lead Agent 执行结构化能力。1:1 映射确保职责清晰，lead-busy 互斥防止资源竞争 |
| **Capability 数据驱动（YAML + DB）** | 能力定义不硬编码在 Python 中，YAML seed 可版本控制，DB 支持运行时编辑，EventBus 驱动缓存失效 |
| **OutputMappingResolver 声明式映射** | YAML 中的 outputs 声明自动解析为 5 种类型化 ResultOutput，无需为每种能力写定制映射代码 |
| **Curated result_card + commit** | 执行产物先暂存不直接写入，用户审阅后选择性 commit，防止自动写入低质量产物 |
| **Graph Compiler 动态构建 LangGraph** | graph_template 编译为 LangGraph StateGraph，支持声明式 phase 依赖（fan-in/fan-out），subagent_type 到类的动态解析 |
| **ExecutionSession / ComputeSession 分离** | 防止前端工作面污染后端业务状态；ComputeSession 只做 UI 投影 |
| **事件驱动刷新而非实时推送投影** | ComputeProjectionService 按需构建投影，不维护实时副本，降低复杂度 |
| **Redis + PG 双写任务状态** | Redis 支持前端快速轮询，PG 支持持久化和恢复 |
| **v2 Subagent Registry 装饰器注册** | `@subagent("name")` 装饰器 + 全局 REGISTRY 单例，简单清晰，compile_graph 通过 name 查找 |
| **Redis abort signal 支持取消** | `abort:exec:{id}` 键在 graph 节点执行前检查，支持用户取消正在运行的能力 |
| **Reference Library 作为 grounded evidence** | 所有文献检索经 Semantic Scholar 验证；LLM 综合只能引用已验证文献，防止幻觉引用 |
| **延迟导入打破循环依赖** | 长依赖链通过方法内延迟导入打破 |
| **Celery Worker fork 安全** | Worker 进程在 `worker_process_init` 重置 DB 引擎，避免 asyncio 事件循环泄漏 |

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
- **内部参数**: 以 `__` 为前缀的参数保留用于内部上下文传递

### 8.2 前端规范

- **Next.js**: App Router，`"use client"` 仅在需要 hooks/stores/router 时使用
- **状态**: Store selector 使用内联 lambda：`useChatStoreV2((s) => s.messages)`
- **类型**: 所有 API 类型集中在 `lib/api/types.ts`
- **Barrel 导出**: 每个域使用 `index.ts` 简化导入
- **性能**: `useMemo` 用于派生选择，`useRef` 用于滚动目标和初始化守卫
- **错误**: API 客户端将错误规范化为 `error.message`；组件内联显示错误横幅
- **v2 设计**: `--v2-*` CSS tokens only in new components。No 古风 tokens

---

## 9. 文档索引

| 文档路径 | 内容 |
|----------|------|
| `docs/README.md` | 文档索引和导航 |
| `docs/architecture/` | 技术栈、API 面、功能域架构、工作区执行流水线、ADRs |
| `docs/infrastructure/` | 部署运行手册、环境变量、故障排查指南 |
| `docs/product/` | 工作区当前状态、Reference Library、功能插件合约、工作区功能目录、发布门控检查表 |
| `docs/strategy/` | 长期方向 |
| `docs/superpowers/specs/2026-05-09-wenjin-workspace-rebuild-design.md` | v2 rebuild spec（source of truth） |
| `docs/superpowers/specs/2026-05-09-v2-design-language.md` | Glass/visionOS 设计语言 |
| `backend/docs/` | 后端专属文档 |
| `frontend/README.md` | 前端专属文档 |
