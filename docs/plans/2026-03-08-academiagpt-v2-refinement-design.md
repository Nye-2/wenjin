# AcademiaGPT v2 完善设计方案

> Date: 2026-03-08
> Status: Approved
> Approach: 渐进式完善（方案 A）

## 1. 项目概述

### 1.1 目标
将 academiagpt-v2 从当前骨架状态完善为可用的多用户生产系统。

### 1.2 部署方案
- **容器编排**: Docker Compose
- **数据库**: PostgreSQL 16 (必用)
- **缓存**: Redis 7 (必用)
- **反向代理**: Nginx

### 1.3 LLM 配置
多提供商支持，复用原项目配置系统：
- 每个模型独立 `api_key` + `base_url`
- 支持 DeepSeek, GLM, Kimi, Qwen, OpenAI, Anthropic 等
- 通过环境变量 JSON 数组配置

### 1.4 认证方案
自建认证系统，邮箱验证登录，复用原 AcademiaGPT 实现。

### 1.5 开发优先级
1. **Phase 1**: Lead Agent + Skills（核心 AI 能力）
2. **Phase 2**: PDF 上传 + 索引导航式 RAG
3. **Phase 3**: 前端工作台
4. **Phase 4**: 认证系统

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Docker Compose 部署                           │
├─────────────────────────────────────────────────────────────────┤
│  nginx (反向代理)                                                │
│    ├── :2026 → frontend (Next.js)                               │
│    ├── :2026/api → gateway (FastAPI)                            │
│    └── :2026/langgraph → langgraph (Agent Server)               │
├─────────────────────────────────────────────────────────────────┤
│  frontend (Next.js 16 + React 19)                               │
│    ├── Liquid Glass 组件库                                       │
│    ├── 三栏工作台 (Knowledge | Chat | Literature)               │
│    └── Zustand 状态管理                                          │
├─────────────────────────────────────────────────────────────────┤
│  gateway (FastAPI)                                              │
│    ├── /api/auth - 认证（Phase 4）                               │
│    ├── /api/workspaces - Workspace CRUD                         │
│    ├── /api/papers - 文献管理 + 上传                             │
│    ├── /api/artifacts - 产物管理                                 │
│    └── /api/chat → SSE 流式转发到 LangGraph                      │
├─────────────────────────────────────────────────────────────────┤
│  langgraph (Agent Server)                                       │
│    ├── Lead Agent (create_react_agent)                          │
│    ├── Middleware Chain (5个学术Middleware)                      │
│    ├── Skills Loader (Markdown Skills)                          │
│    └── Subagent Registry (Scout, Writer, Synthesizer, Analyst)  │
├─────────────────────────────────────────────────────────────────┤
│  postgres (PostgreSQL 16)                                       │
│    ├── users, sessions, workspaces, papers, artifacts           │
│    └── paper_sections (章节索引，无向量)                         │
├─────────────────────────────────────────────────────────────────┤
│  redis (必用)                                                   │
│    ├── 会话缓存                                                  │
│    ├── RAG 索引缓存                                              │
│    ├── Agent 状态追踪                                            │
│    └── 速率限制                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Phase 1: Lead Agent + Skills

### 3.1 Lead Agent 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Lead Agent (LangGraph)                    │
├─────────────────────────────────────────────────────────────┤
│  Entry: make_lead_agent(config)                              │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │           Middleware Chain (before_model)            │    │
│  │  Workspace → Literature → Knowledge → Discipline     │    │
│  │  → Citation                                          │    │
│  └─────────────────────────────────────────────────────┘    │
│                         ↓                                    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Prompt Assembly                         │    │
│  │  base_prompt + workspace + literature + knowledge   │    │
│  │  + discipline_norms + skills_list                   │    │
│  └─────────────────────────────────────────────────────┘    │
│                         ↓                                    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              ReAct Agent Loop                        │    │
│  │  Model → Tool Call → Execution → Response           │    │
│  └─────────────────────────────────────────────────────┘    │
│                         ↓                                    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │           Middleware Chain (after_model)             │    │
│  │  Citation (extract citations)                        │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 模型工厂

```python
# src/models/factory.py

def create_chat_model(
    model_id: str,
    temperature: float = 0.7,
    thinking_enabled: bool = False,
) -> BaseChatModel:
    """根据 model_id 创建模型实例"""
    config = get_model_full_config(model_id)  # 从 model_registry 获取

    if "anthropic" in config["base_url"] or "claude" in config["model"]:
        return ChatAnthropic(
            model=config["model"],
            api_key=config["api_key"],
            base_url=config["base_url"],
            temperature=temperature,
            max_tokens=config["max_tokens"],
        )
    else:
        return ChatOpenAI(
            model=config["model"],
            api_key=config["api_key"],
            base_url=config["base_url"],
            temperature=temperature,
            max_tokens=config["max_tokens"],
        )
```

### 3.3 五个学术 Middleware

| Middleware | 触发时机 | 职责 | 输入 | 输出 |
|------------|---------|------|------|------|
| **WorkspaceContext** | before_model | 加载 workspace 配置 | workspace_id | workspace_type, discipline, config |
| **LiteratureContext** | before_model | 索引导航检索 | workspace_id, 最近消息 | _literature_context |
| **KnowledgeContext** | before_model | 注入已有 artifacts | workspace_id | _knowledge_context |
| **DisciplineContext** | before_model | 学科写作规范 | discipline, workspace_type | _discipline_norms |
| **CitationContext** | after_model | 追踪引用来源 | AI 响应 | cited_papers |

### 3.4 四个学术 Subagent

```python
ACADEMIC_SUBAGENTS = {
    "scout": SubagentConfig(
        name="Scout",
        description="文献探索，扩展文献库、追踪引用链",
        tools=["semantic_scholar_search"],
        max_turns=10,
    ),
    "writer": SubagentConfig(
        name="Writer",
        description="学术写作，按学科规范写作",
        tools=["get_paper_section"],
        max_turns=15,
    ),
    "synthesizer": SubagentConfig(
        name="Synthesizer",
        description="综合分析，生成创新洞察",
        tools=["get_paper_section", "get_artifact"],
        max_turns=10,
    ),
    "analyst": SubagentConfig(
        name="Analyst",
        description="数据分析，统计和实验设计",
        tools=["get_paper_section"],
        max_turns=10,
    ),
}
```

### 3.5 Skills 系统

```
backend/skills/
├── public/
│   ├── deep-research/SKILL.md
│   ├── framework-designer/SKILL.md
│   ├── fullpaper-writer/SKILL.md
│   ├── literature-review/SKILL.md
│   ├── proposal-writer/SKILL.md
│   ├── experiment-designer/SKILL.md
│   ├── peer-reviewer/SKILL.md
│   └── journal-recommender/SKILL.md
└── custom/  # 用户自定义（预留）
```

---

## 4. Phase 2: PDF/索引系统

### 4.1 设计理念
**不使用 Embedding 向量检索**，采用索引导航式检索：
1. LLM 先查看文献目录（Table of Contents）
2. 根据目录导航到指定章节
3. 取出该章节完整内容

### 4.2 文献提取管道

```
PDF 上传
    ↓
Tier 1: 工程提取（PyMuPDF）
├── 元数据 (title, authors, year, venue)
├── 目录结构 (TOC) ← 关键
├── 按章节/页面分块 (sections)
└── 存储完整文本
    ↓
Tier 2: 轻量 LLM 提取（可选）
├── 摘要理解
├── 领域/关键词
└── 不做 embedding
```

### 4.3 数据模型

```sql
papers (
    id, doi, title, authors, year, venue,
    abstract, file_path,
    toc JSONB  -- 目录结构
)

paper_sections (
    id, paper_id, workspace_id,
    section_title TEXT,
    section_path TEXT,       -- "3.2.1 Model Architecture"
    page_start INT,
    page_end INT,
    content TEXT,
    metadata JSONB
)
-- 无 embedding 字段
```

### 4.4 检索工具

```python
@tool
def get_paper_toc(paper_id: str) -> str:
    """获取论文目录结构，用于导航"""

@tool
def get_paper_section(paper_id: str, section_path: str) -> str:
    """获取指定章节内容"""

@tool
def search_papers_by_metadata(workspace_id: str, query: str) -> list:
    """基于元数据搜索论文（标题/作者/关键词）"""
```

---

## 5. Phase 3: 前端工作台

### 5.1 页面结构

```
app/
├── (auth)/
│   ├── login/page.tsx
│   └── register/page.tsx
├── (dashboard)/
│   └── workspaces/
│       ├── page.tsx           # 列表
│       └── new/page.tsx       # 新建
└── (workbench)/
    └── workspaces/[id]/
        ├── page.tsx           # 三栏工作台
        └── components/
            ├── KnowledgePanel.tsx
            ├── ChatPanel.tsx
            ├── LiteraturePanel.tsx
            └── SkillSelector.tsx
```

### 5.2 三栏布局

```
┌────────────┬────────────────────────────┬────────────────────┐
│ Knowledge  │         Agent Chat         │   Literature       │
│ (左栏)     │         (中栏)             │   (右栏)           │
├────────────┼────────────────────────────┼────────────────────┤
│ Timeline   │  [Skill 选择器]            │  搜索 / 上传       │
│            │                            │                    │
│ ○ Idea #1  │  AI 响应区域               │  📄 paper1.pdf     │
│ ├─ Method  │  (Markdown 渲染)           │  📄 paper2.pdf     │
│ └─ Frame   │                            │  📄 paper3.pdf     │
│            │                            │                    │
│ ○ Draft    │  输入框                    │                    │
├────────────┴────────────────────────────┴────────────────────┤
│ [deep-research] [framework-designer] [fullpaper-writer] ...  │
└──────────────────────────────────────────────────────────────┘
```

### 5.3 状态管理

```typescript
// stores/workspace.ts
interface WorkspaceState {
  workspace: Workspace | null;
  artifacts: Artifact[];
  papers: Paper[];
  loadWorkspace: (id: string) => Promise<void>;
}

// stores/chat.ts
interface ChatState {
  messages: Message[];
  isStreaming: boolean;
  currentSkill: string | null;
  sendMessage: (content: string, skill?: string) => Promise<void>;
}
```

---

## 6. Phase 4: 认证系统

### 6.1 迁移来源
从原 AcademiaGPT 项目迁移：
- `services/auth.py` → JWT 工具函数
- `api/auth.py` → 认证端点
- `services/user_service.py` → 用户 CRUD
- `services/email_service.py` → 邮箱验证码

### 6.2 认证流程

**注册流程**:
1. `POST /api/auth/send-verification-code` → 发送验证码
2. `POST /api/auth/register` → 验证码验证 + 创建用户 + JWT

**登录流程**:
1. `POST /api/auth/login` → 验证密码 + 创建会话 + JWT

### 6.3 用户模型

```python
class User(Base):
    id: UUID
    email: str          # unique
    password_hash: str
    username: str | None
    display_name: str | None
    institution: str | None
    is_active: bool = True
    is_verified: bool = False
    role: str = "user"  # user, premium, admin
    daily_quota: int = 10
    credits: int = 0
    created_at: datetime
    last_login_at: datetime | None
```

---

## 7. 测试与错误处理

### 7.1 测试结构

```
tests/
├── conftest.py
├── unit/
│   ├── services/test_auth.py
│   ├── models/test_factory.py
│   └── middlewares/test_middlewares.py
├── integration/
│   ├── test_api_auth.py
│   ├── test_api_workspaces.py
│   └── test_agent_flow.py
└── fixtures/
    └── sample_paper.pdf
```

### 7.2 异常体系

```python
class AppException(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400)

class NotFoundError(AppException):     # 404
class QuotaExceededError(AppException): # 429
class PaperExtractionError(AppException): # 422
```

---

## 8. Docker Compose 部署

### 8.1 服务编排

```yaml
services:
  nginx:       # 反向代理 :2026
  frontend:    # Next.js :3000
  gateway:     # FastAPI :8001
  langgraph:   # Agent :2024
  postgres:    # PostgreSQL 16
  redis:       # Redis 7 (必用)

volumes:
  postgres_data:
  redis_data:
  uploads:
```

### 8.2 Redis 用途

```
├── session:{user_id}:{session_id}     # 会话
├── rag:toc:{paper_id}                 # 目录缓存
├── rag:section:{paper_id}:{path}      # 章节缓存
├── agent:thread:{thread_id}:status    # Agent 状态
├── ratelimit:{user_id}:{endpoint}     # 速率限制
└── verify:{email}:{purpose}           # 验证码
```

### 8.3 启动命令

```bash
cp .env.example .env
docker compose up -d postgres
docker compose exec gateway uv run alembic upgrade head
docker compose up -d
```

---

## 9. 目录结构

```
academiagpt-v2/
├── docker-compose.yml
├── nginx.conf
├── .env
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic/
│   ├── src/
│   │   ├── gateway/         # FastAPI 路由
│   │   ├── agents/          # Lead Agent + Middleware
│   │   ├── academic/        # 文献、知识服务
│   │   ├── database/        # SQLAlchemy 模型
│   │   ├── models/          # LLM 工厂
│   │   ├── services/        # 业务服务
│   │   ├── tools/           # 内置工具
│   │   ├── subagents/       # 子代理
│   │   ├── skills/          # Skill 加载器
│   │   └── config/          # 配置
│   ├── skills/              # Markdown Skills
│   └── tests/
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── app/
    ├── components/
    ├── lib/
    └── stores/
```

---

*Design completed: 2026-03-08*
