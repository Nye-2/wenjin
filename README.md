# 问津 Wenjin

> **向研究深处问津。**

问津，取自《论语》"长沮桀溺耦而耕，孔子过之，使子路问津焉"。津，渡口也。问津，是在前路未明时主动探询方向的姿态。

学术研究也是如此——论文、申报、专利，每一项都是一段需要找到渡口的旅程。问津希望成为那个帮你探路的同行者，而不是替你走路的工具。

---

## 理念

### 为什么要做问津？

AI 写作工具正在泛滥，但大多数都在做同一件事：给你一个输入框，让你描述需求，然后一次性生成一段文字。这种模式有它的价值，但对于学术写作来说远远不够。

学术写作是一个**阶段性的、迭代的、高度个人化**的过程：

- 你需要系统地检索文献，而不只是让 AI 背诵它知道的知识
- 你的大纲需要经过多轮讨论和修改，而不是一次生成就完成
- 你的导师有特定的写作规范，你的目标期刊有投稿要求，这些约束是真实存在的
- 你在写第三章时，AI 需要记得你在第一章确定的研究问题

问津的回答是：**不是一个更好的文字生成器，而是一个真正懂得如何做学术研究的工作伙伴。**

### 核心设计原则

**对话即工作流。** 不是填表单，不是点按钮执行任务，而是通过自然对话完成所有工作。AI 会主动询问它需要知道的信息，引导你逐步推进，而不是把参数收集的负担抛给你。

**阶段感知，而非功能堆砌。** 每个工作区都有清晰的研究阶段（调研 → 收集 → 结构 → 写作 → 评审），系统知道你现在在哪个阶段，推荐下一步该做什么，而不是把所有功能平铺展示让你自己选择。

**一个工作区，一段对话。** 每个工作区只有一个持续的对话线程。你不需要管理多个对话分支——所有的上下文、记忆、成果都在同一个连续的工作流中积累。AI 通过摘要压缩和长期记忆提取来保持上下文的连贯性。

**成果驱动，而非过程驱动。** 每次对话产生的论文章节、文献综述、大纲、图表都作为"成果"持久保存，可以追溯来源，可以在后续工作中复用。工作区不只是聊天记录，而是研究进展的完整档案。

**模板优先，自由生成兜底。** 有学校/期刊模板就按模板写，没有就让 AI 自由发挥。这个顺序很重要——学术写作最终要符合规范，AI 的自由创作只是起点。

---

## 支持的工作区类型

### 学位论文
从选题到答辩的全程支持。AI 会帮你梳理研究方向、检索相关文献、设计论文结构、逐章推进写作、生成图表、最终编译排版。特别针对导师要求和学校规范做了适配。

**工作模块：** 深度调研 · 文献管理 · 开题综述 · 大纲设计 · 论文撰写 · 图表生成 · 编译导出

### 学术论文（SCI/EI）
面向期刊投稿的全流程辅助。从 research gap 识别到 revision response letter，覆盖 SCI/EI 论文写作的所有关键节点。支持按期刊要求调整写作规范。

**工作模块：** 文献检索 · 论文分析 · 章节写作 · 文献综述 · 框架设计 · 同行评审 · 期刊推荐

### 研究计划书
基金申请和研究计划撰写。重点突出创新性、可行性和科学意义，针对国自然、省基金等不同类型提供针对性指导。

**工作模块：** 背景调研 · 实验设计 · 计划书撰写

### 软件著作权
整理软件材料，生成符合版权局要求的说明书和技术文档。

**工作模块：** 著作权材料 · 技术文档

### 专利申请
从现有技术检索到权利要求书撰写，覆盖发明专利和实用新型专利的核心文件。

**工作模块：** 专利撰写 · 现有技术检索

---

## 系统架构

### 整体设计思路

问津的核心是**一个对话入口，多层能力支撑**的架构：

```
用户对话
    ↓
Lead Agent（对话引导 + 意图理解 + Skill 调度）
    ↓
17 层 Middleware Pipeline（上下文增强 + 记忆注入 + 权限控制）
    ↓
Workspace Feature 执行图（确定性工作流 + Subagent 子任务）
    ↓
工具层（文献检索 · LaTeX 编译 · 代码执行 · 知识库）
```

### Lead Agent 与 Skill 系统

Lead Agent 是用户的主要对话界面。它不是一个通用聊天机器人，而是针对每种工作区类型有专属的系统提示——理解对应领域的写作规范、阶段流程和学术惯例。

**Skill** 是 Lead Agent 的能力单元，共 21 个，分布在 5 种工作区类型中。每个 Skill 都有：
- 对话式参数收集提示（引导用户说清楚需求，而不是弹出表单）
- 对应的 Feature 执行图（确定性的、可追溯的工作流）
- 后续推荐 Skill（帮助用户知道下一步该做什么）

```
Skill（交互层）  →  Feature（执行层）  →  成果
deep-research    →  deep_research      →  文献报告 Artifact
framework-designer → framework_outline → 论文大纲 Artifact
fullpaper-writer   → thesis_writing    → 章节草稿 Artifact
```

### Middleware Pipeline（17 层）

每次对话都经过严格有序的 17 层中间件处理，在 LLM 被调用之前完成所有上下文增强：

| 层级 | 中间件 | 作用 |
|------|--------|------|
| 1 | ThreadData | 加载历史消息和线程状态 |
| 2 | Uploads | 处理附件和文件上传 |
| 3 | Sandbox | 代码执行环境初始化 |
| 4 | FeatureBridge | Feature 意图识别与路由 |
| 5 | UserMemory | 注入用户长期记忆 |
| 6 | KnowledgeContext | 注入知识库检索结果 |
| 7 | LiteratureContext | 注入文献库上下文 |
| 8 | DisciplineNorms | 注入学科写作规范 |
| 9 | WorkspaceContext | 注入工作区状态和活跃模板 |
| 10 | ArtifactContext | 注入已有成果摘要 |
| 11 | TaskContext | 注入后台任务状态 |
| 12 | Clarification | 检测是否需要澄清 |
| 13-17 | 工具执行层 | 文献检索、代码执行、LaTeX 编译等 |

### 单线程模型

每个工作区只维护一个持续的对话线程，而不是多个分支。这个设计背后有几层考量：

- **每个工作区对应一个项目**，不需要并行管理多个思路分支
- **摘要压缩**（SummarizationMiddleware）在上下文达到 80k tokens 时自动压缩历史，保持响应速度
- **长期记忆提取**（MemoryMiddleware）将对话中的关键事实（引用格式偏好、研究方向、导师要求等）持久化到知识库，在未来对话中自动注入
- **文献和知识上下文通过中间件注入**，不依赖对话历史，不会因为压缩而丢失

### 模板系统

用户可以在对话中上传学校/期刊/基金的写作模板（.docx、.tex、.txt、.md），问津会：

1. 用 LLM 解析模板，提取结构化的章节要求、排版规范、内容指引
2. 将解析结果存储为工作区的活跃模板
3. 在后续所有写作类操作中自动参考模板规范，影响大纲设计、正文撰写、编译排版

没有模板时，AI 自由发挥。模板是可选的增强，不是强制的前置条件。

### 成果系统（Artifact）

每次完成的工作产出——文献报告、论文大纲、章节草稿、图表、编译文档——都作为 Artifact 持久保存，带有：
- 来源追溯（由哪个 Feature + 哪次对话产生）
- 类型分类（DEEP_RESEARCH_REPORT / FRAMEWORK_OUTLINE / THESIS_CHAPTER / ...）
- 版本迭代（可多次生成，保留历史版本）

成果还驱动 Dashboard 的智能推荐：
- 无成果 → 推荐「开始深度调研」
- 有调研成果 → 推荐「大纲设计」
- 有大纲 → 推荐「开始写作」
- 有草稿 → 推荐「同行评审」或「编译导出」

---

## 技术栈

### 后端

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.12+ | 核心语言 |
| FastAPI | 最新 | API 网关 |
| SQLAlchemy | 2.0 async | ORM |
| PostgreSQL | 16+ | 主数据库 |
| pgvector | - | 向量存储（文献嵌入） |
| Redis | 7+ | 缓存 / Pub-Sub / 任务队列 |
| LangGraph | 最新 | Agent 执行图 |
| LangChain | 最新 | LLM 工具链 |
| Celery | 最新 | 后台任务 Worker |

### 前端

| 技术 | 版本 | 用途 |
|------|------|------|
| Next.js | 16 | 全栈框架（App Router） |
| React | 19 | UI 框架 |
| TypeScript | 5+ | 类型安全 |
| TailwindCSS | 4 | 样式 |
| Framer Motion | 最新 | 动画 |
| Zustand | 最新 | 状态管理 |
| react-markdown | 最新 | Markdown 渲染 |

---

## 快速开始

### 环境依赖
- Docker + Docker Compose
- PostgreSQL 16+（含 pgvector 扩展）
- Redis 7+
- 至少一个 LLM 提供商（OpenAI / Anthropic / 国内厂商，通过 config.yaml 配置）

### Docker Compose 启动（推荐）

```bash
# 克隆仓库
git clone <repository-url>
cd <repo-dir>

# 创建后端环境配置（不纳入版本控制）
cp backend/.env.example backend/.env
# 编辑 backend/.env，填入 LLM 提供商密钥和数据库连接信息

# 国内网络可选：使用 Docker 镜像加速
cp .env.docker-cn.example .env

# 启动所有服务
docker compose up -d --build

# 确认数据库迁移完成
docker compose logs -f migrate
```

访问 `http://localhost:3000` 即可使用。

### 本地开发

```bash
# 后端
cd backend
uv sync --extra dev
cp .env.example .env          # 编辑 .env 填写配置
uv run alembic upgrade head   # 初始化数据库
uv run uvicorn src.gateway.app:app --reload --port 8001

# Celery Worker（另一个终端）
cd backend
uv run celery -A src.task.celery_app worker --loglevel=info

# 前端（另一个终端）
cd frontend
npm install
npm run dev
```

---

## 项目结构

```
wenjin/
├── backend/
│   ├── src/
│   │   ├── gateway/                    # FastAPI 网关 + 路由
│   │   ├── agents/
│   │   │   ├── lead_agent/             # 对话 Agent + Skill 目录
│   │   │   │   ├── agent.py            # 系统提示 + 工作区类型专属 Prompt
│   │   │   │   └── chat_skill_catalog.py  # 21 个 Skill 定义
│   │   │   ├── middlewares/            # 17 层 Middleware Pipeline
│   │   │   └── workspace_lead_agent.py # Feature 执行 Agent
│   │   ├── academic/                   # 学术服务（文献检索、Semantic Scholar 等）
│   │   ├── database/                   # SQLAlchemy 数据模型
│   │   ├── models/                     # LLM 工厂 + 路由策略
│   │   ├── services/                   # 认证 / 记忆 / 模板 / 知识库
│   │   ├── task/                       # Celery 任务框架
│   │   └── workspace_features/         # Feature 注册表 + 执行图
│   ├── alembic/                        # 数据库迁移脚本
│   └── pyproject.toml
├── frontend/
│   ├── app/
│   │   ├── (workbench)/workspaces/[id]/  # 工作区主界面
│   │   │   ├── page.tsx                  # Dashboard（英雄区 + 推荐 + 功能卡片）
│   │   │   ├── chat/page.tsx             # 对话页（单线程模型）
│   │   │   ├── layout.tsx                # 工作区布局 + 数据加载
│   │   │   └── components/
│   │   │       ├── ChatPanel.tsx         # 对话面板（流式 + 状态栏）
│   │   │       ├── WorkspaceInspector.tsx # 成果 / 文献 / 活动面板
│   │   │       └── SkillSelector.tsx     # Skill 选择器
│   │   └── workspaces/                   # 工作区列表 + 创建
│   ├── components/                       # 通用 UI 组件
│   ├── lib/                              # API 客户端 / 图标映射 / 路由工具
│   └── stores/                           # Zustand 状态（chat / workspace / features / task）
├── docs/
│   ├── architecture/                     # 架构决策记录
│   ├── infrastructure/                   # 部署和运维手册
│   ├── plans/                            # 功能设计和实现计划
│   └── product/                          # 产品能力文档
├── docker-compose.yml
└── nginx.conf
```

---

## API 文档

### 认证
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 注册新用户 |
| POST | `/api/auth/login` | 登录获取 Token |
| POST | `/api/auth/refresh` | 刷新 Access Token |
| GET | `/api/auth/me` | 获取当前用户信息 |

### 工作区
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/workspaces` | 列出用户工作区 |
| POST | `/api/workspaces` | 创建工作区 |
| GET | `/api/workspaces/{id}` | 获取工作区详情 |
| PUT | `/api/workspaces/{id}` | 更新工作区 |
| DELETE | `/api/workspaces/{id}` | 删除工作区 |

### 对话
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat/stream` | 流式对话（SSE） |
| GET | `/api/threads` | 列出工作区对话线程 |
| GET | `/api/threads/{id}` | 获取线程与消息 |
| DELETE | `/api/threads/{id}` | 删除线程 |

> 每个工作区使用唯一的持续线程。前端自动加载已有线程，无则新建。Skill 选择持久化在线程级别。功能入口统一跳转 `/workspaces/{id}/chat?feature=xxx`。

### 功能与 Skill
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/workspaces/{workspace_id}/features` | 获取工作区功能列表 |
| POST | `/api/workspaces/{workspace_id}/features/{feature_id}/execute` | 执行功能 |
| GET | `/api/workspaces/{workspace_id}/skills` | 获取 Skill 列表（含引导 Prompt） |

### 文献
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/papers` | 列出文献 |
| POST | `/api/papers/upload` | 上传 PDF（需 `workspace_id`） |
| POST | `/api/papers/search` | 搜索文献 |
| POST | `/api/papers/{id}/extract` | 触发元数据提取任务 |

### 成果（Artifact）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/workspaces/{workspace_id}/artifacts` | 列出成果 |
| POST | `/api/workspaces/{workspace_id}/artifacts` | 创建成果 |
| GET | `/api/workspaces/{workspace_id}/artifacts/{id}` | 获取成果详情 |
| PUT | `/api/workspaces/{workspace_id}/artifacts/{id}` | 更新成果 |
| DELETE | `/api/workspaces/{workspace_id}/artifacts/{id}` | 删除成果 |
| GET | `/api/workspaces/{workspace_id}/artifacts/{id}/lineage` | 成果溯源 |

### 写作模板
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/workspaces/{workspace_id}/templates/upload` | 上传并解析模板文件 |
| GET | `/api/workspaces/{workspace_id}/templates` | 列出工作区模板 |
| GET | `/api/workspaces/{workspace_id}/templates/active` | 获取当前活跃模板 |
| PUT | `/api/workspaces/{workspace_id}/templates/{id}/activate` | 激活模板 |
| DELETE | `/api/workspaces/{workspace_id}/templates/{id}` | 删除模板 |

### 任务与事件
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tasks/{id}` | 获取任务状态 |
| GET | `/api/tasks/{id}/stream` | 订阅任务进度（SSE） |
| GET | `/api/workspaces/{workspace_id}/events` | 订阅工作区事件流（SSE） |

### Subagent
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/subagents/threads/{thread_id}/spawn` | 创建子 Agent 任务 |
| GET | `/api/subagents/threads/{thread_id}/tasks/{task_id}/status` | 获取子任务状态 |
| POST | `/api/subagents/threads/{thread_id}/tasks/{task_id}/cancel` | 取消子任务 |

---

## 测试

```bash
# 后端测试
cd backend
uv run pytest

# 覆盖率报告
uv run pytest --cov=src --cov-report=term-missing

# 前端静态检查
cd frontend
npx tsc --noEmit
npm run lint
npx next build
```

---

## 部署

详见 [docs/infrastructure/deployment-runbook.md](docs/infrastructure/deployment-runbook.md)。

---

## 开源协议

MIT
