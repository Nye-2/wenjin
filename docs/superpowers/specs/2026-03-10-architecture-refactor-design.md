# AcademiaGPT-V2 架构重构设计文档

> 创建日期: 2026-03-10
> 状态: 已批准
> 作者: Claude + 用户

## 1. 概述

### 1.1 背景

AcademiaGPT-V2 是将原始 **AcademiaGPT**（Vue3+FastAPI+CrewAI）与 **deer-flow**（LangGraph超级代理平台）的架构融合的重构项目。

### 1.2 目标

- **架构优先**：先对齐 deer-flow 的核心架构设计，确保系统可扩展性和一致性
- **分阶段进行**：集中解决最关键的架构问题，后续迭代完善
- **适合学术场景**：在借鉴 deer-flow 架构的同时，针对学术写作场景进行优化

### 1.3 重点架构组件

| 优先级 | 组件 | 说明 |
|--------|------|------|
| 1 | 沙箱系统 | 完整的沙箱抽象层、虚拟路径系统、本地/Docker 提供商 |
| 2 | 子代理系统 | 双重线程池、SSE 事件流、超时控制、并发限制 |
| 3 | MCP 集成 | OAuth 支持、缓存系统、多传输支持 (stdio/SSE/HTTP) |
| 4 | 记忆系统 | 长期记忆存储、事实提取、去重机制、队列更新 |

## 2. 阶段 1：沙箱系统

### 2.1 设计目标

重新设计适合学术场景的沙箱系统，支持：
- **学术工具集成**：PDF 处理、LaTeX 编译、文献管理等学术专用工具
- **简化架构**：保持沙箱接口简洁，方便后续扩展
- **代码执行**：支持在沙箱中运行 Python/R 代码进行数据分析
- **混合模式**：本地开发 + Docker 生产

### 2.2 目录结构

```
src/sandbox/
├── __init__.py
├── base.py              # Sandbox 抽象接口
├── providers/
│   ├── __init__.py
│   ├── local.py         # LocalSandboxProvider (开发用)
│   └── docker.py        # DockerSandboxProvider (生产用)
├── tools.py             # 沙箱工具集 (bash, read, write, str_replace)
├── academic_tools.py    # 学术专用工具 (latex, pdf, citation)
├── middleware.py        # SandboxMiddleware
├── paths.py             # 虚拟路径系统
└── config.py            # 沙箱配置
```

### 2.3 核心接口

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class CommandResult:
    """命令执行结果"""
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False

@dataclass
class FileInfo:
    """文件信息"""
    name: str
    path: str
    is_dir: bool
    size: Optional[int] = None

class Sandbox(ABC):
    """沙箱抽象接口"""

    @abstractmethod
    async def execute_command(
        self,
        command: str,
        timeout: int = 300
    ) -> CommandResult:
        """执行命令"""
        pass

    @abstractmethod
    async def read_file(self, path: str) -> str:
        """读取文件"""
        pass

    @abstractmethod
    async def write_file(self, path: str, content: str) -> None:
        """写入文件"""
        pass

    @abstractmethod
    async def list_dir(self, path: str) -> list[FileInfo]:
        """列出目录内容"""
        pass

    @property
    @abstractmethod
    def sandbox_id(self) -> str:
        """沙箱唯一标识"""
        pass

class SandboxProvider(ABC):
    """沙箱提供商抽象接口"""

    @abstractmethod
    async def acquire(self, thread_id: str) -> Sandbox:
        """获取沙箱实例"""
        pass

    @abstractmethod
    async def release(self, sandbox: Sandbox) -> None:
        """释放沙箱实例"""
        pass

    @abstractmethod
    async def get(self, sandbox_id: str) -> Optional[Sandbox]:
        """获取已存在的沙箱"""
        pass
```

### 2.4 虚拟路径系统

```python
class VirtualPathMapper:
    """虚拟路径映射器"""

    # 虚拟路径前缀
    VIRTUAL_PREFIX = "/mnt/user-data"

    # 映射规则
    MAPPINGS = {
        "/mnt/user-data/workspace": "threads/{thread_id}/workspace",
        "/mnt/user-data/uploads": "threads/{thread_id}/uploads",
        "/mnt/user-data/outputs": "threads/{thread_id}/outputs",
        "/mnt/skills": "skills/public",
    }

    def to_physical(self, virtual_path: str, thread_id: str) -> str:
        """将虚拟路径转换为物理路径"""
        pass

    def to_virtual(self, physical_path: str, thread_id: str) -> str:
        """将物理路径转换为虚拟路径"""
        pass

    def translate_command(self, command: str, thread_id: str) -> str:
        """翻译命令中的虚拟路径"""
        pass
```

### 2.5 学术工具扩展

```python
class AcademicSandboxTools:
    """学术专用沙箱工具"""

    async def latex_compile(
        self,
        source: str,
        output_dir: str = "/mnt/user-data/outputs"
    ) -> "PDFResult":
        """
        LaTeX 编译

        Args:
            source: LaTeX 源码或 .tex 文件路径
            output_dir: 输出目录

        Returns:
            PDFResult: 包含 PDF 路径和编译日志
        """
        pass

    async def pdf_extract(
        self,
        pdf_path: str,
        pages: Optional[list[int]] = None
    ) -> "PDFContent":
        """
        PDF 文本提取

        Args:
            pdf_path: PDF 文件路径
            pages: 指定页码（None 表示全部）

        Returns:
            PDFContent: 包含文本、元数据、页数
        """
        pass

    async def citation_format(
        self,
        citations: list["Citation"],
        style: str = "apa"  # apa, mla, chicago, ieee
    ) -> str:
        """
        引用格式化

        Args:
            citations: 引用列表
            style: 引用格式

        Returns:
            str: 格式化后的引用文本
        """
        pass

    async def code_execute(
        self,
        code: str,
        language: str,  # python, r
        timeout: int = 60
    ) -> "CodeResult":
        """
        代码执行

        Args:
            code: 源代码
            language: 编程语言
            timeout: 超时时间（秒）

        Returns:
            CodeResult: 包含输出、错误、图表
        """
        pass
```

### 2.6 配置

```yaml
# config.yaml
sandbox:
  # 沙箱模式: local | docker
  mode: local

  # 本地沙箱配置
  local:
    base_dir: .academiagpt/threads

  # Docker 沙箱配置
  docker:
    image: academiagpt/sandbox:latest
    timeout: 300
    memory: 2g
    cpu_limit: 2

  # 学术工具配置
  academic:
    latex:
      enabled: true
      engine: xelatex  # xelatex | pdflatex
    code_execution:
      enabled: true
      languages: [python, r]
```

## 3. 阶段 2：子代理系统

### 3.1 设计目标

- 双重线程池架构，支持并行任务处理
- SSE 事件流，实时反馈子代理状态
- 超时控制和并发限制
- 学术专用代理（研究者、写作者、评审者、分析师）

### 3.2 目录结构

```
src/subagents/
├── __init__.py
├── executor.py          # 并行执行器
├── registry.py          # 代理注册表
├── events.py            # SSE 事件流
├── limit.py             # 并发限制
├── task_tool.py         # 任务委托工具
└── academic/            # 学术专用代理
    ├── __init__.py
    ├── researcher.py    # 文献搜索代理
    ├── writer.py        # 论文写作代理
    ├── reviewer.py      # 同行评审代理
    └── analyst.py       # 数据分析代理
```

### 3.3 执行器设计

```python
@dataclass
class SubagentTask:
    """子代理任务"""
    task_id: str
    subagent_type: str
    prompt: str
    max_turns: int = 10
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class SubagentEvent:
    """子代理事件"""
    event_type: str  # task_started, task_running, task_completed, task_failed
    task_id: str
    data: dict
    timestamp: datetime = field(default_factory=datetime.now)

class SubagentExecutor:
    """子代理执行器"""

    # 并发配置
    MAX_CONCURRENT = 3
    TIMEOUT_SECONDS = 900  # 15 分钟

    def __init__(self):
        # 双重线程池
        self._scheduler_pool = ThreadPoolExecutor(max_workers=3)
        self._execution_pool = ThreadPoolExecutor(max_workers=3)
        self._active_tasks: dict[str, asyncio.Task] = {}

    async def execute(self, task: SubagentTask) -> AsyncIterator[SubagentEvent]:
        """执行子代理任务，产生事件流"""
        pass

    async def cancel(self, task_id: str) -> bool:
        """取消任务"""
        pass

    def get_status(self, task_id: str) -> Optional[str]:
        """获取任务状态"""
        pass
```

### 3.4 学术专用代理

| 代理 | 职责 | 可用工具 |
|------|------|----------|
| researcher | 文献搜索、证据收集 | semantic_scholar, arxiv, rag_retrieve |
| writer | 学术章节写作 | write_file, read_file, citation_format |
| reviewer | 学术质量评审 | read_file, ask_clarification |
| analyst | 数据分析 | code_execute, bash, python |

## 4. 阶段 3：MCP 集成

### 4.1 设计目标

- 标准化工具协议集成
- 支持 stdio、SSE、HTTP 三种传输方式
- OAuth 认证支持
- 工具缓存和失效机制

### 4.2 目录结构

```
src/mcp/
├── __init__.py
├── client.py            # MCP 客户端
├── cache.py             # 工具缓存
├── registry.py          # MCP 服务器注册
├── oauth.py             # OAuth 认证
├── transports/
│   ├── __init__.py
│   ├── stdio.py
│   ├── sse.py
│   └── http.py
└── academic/            # 学术 MCP 服务器配置
    ├── __init__.py
    ├── semantic_scholar.py
    ├── arxiv.py
    └── pubmed.py
```

### 4.3 配置示例

```json
// extensions_config.json
{
  "mcpServers": {
    "semantic-scholar": {
      "enabled": true,
      "type": "http",
      "url": "https://api.semanticscholar.org/mcp",
      "description": "Semantic Scholar 学术搜索"
    },
    "arxiv": {
      "enabled": true,
      "type": "stdio",
      "command": "uvx",
      "args": ["arxiv-mcp-server"],
      "description": "ArXiv 论文检索"
    },
    "pubmed": {
      "enabled": true,
      "type": "http",
      "url": "https://pubmed.ncbi.nlm.nih.gov/mcp",
      "oauth": {
        "type": "client_credentials",
        "token_url": "https://oauth.ncbi.nlm.nih.gov/token",
        "client_id": "$PUBMED_CLIENT_ID",
        "client_secret": "$PUBMED_CLIENT_SECRET"
      },
      "description": "PubMed 生物医学文献"
    }
  }
}
```

## 5. 阶段 4：记忆系统

### 5.1 设计目标

- 长期记忆存储，支持学术上下文持久化
- LLM 驱动的事实提取和分类
- 防抖更新队列，避免频繁写入
- 原子写入确保数据一致性

### 5.2 目录结构

```
src/agents/memory/
├── __init__.py
├── store.py             # 记忆存储
├── updater.py           # LLM 驱动的事实提取
├── queue.py             # 防抖更新队列
├── prompts.py           # 记忆更新提示词
└── schema.py            # 数据结构定义
```

### 5.3 数据结构

```python
@dataclass
class AcademicFact:
    """学术事实"""
    id: str
    content: str
    category: str  # preference, knowledge, paper, method, finding
    confidence: float  # 0.0 - 1.0
    source: str  # 来源会话 ID
    created_at: datetime

@dataclass
class AcademicMemory:
    """学术记忆"""
    # 用户研究上下文
    research_interests: list[str]
    writing_style: str
    citation_style: str  # apa, mla, chicago, ieee
    domain_expertise: list[str]

    # 历史上下文
    recent_projects: list[str]
    ongoing_research: str

    # 事实存储
    facts: list[AcademicFact]

    # 元数据
    last_updated: datetime
    version: int
```

### 5.4 记忆更新流程

```
1. MemoryMiddleware 拦截对话结束
2. 过滤出用户输入 + 最终 AI 响应
3. 加入防抖队列（30秒等待）
4. 批量提交给 LLM 提取事实
5. 原子写入到 memory.json
6. 下次对话注入 top 15 事实到系统提示
```

## 6. 实施顺序

```
Phase 1: 沙箱系统 (基础)
    │
    │  所有其他系统都依赖安全的执行环境
    │
    ▼
Phase 2: 子代理系统 (依赖沙箱执行)
    │
    │  需要沙箱来执行复杂任务
    │
    ▼
Phase 3: MCP 集成 (工具扩展)
    │
    │  在核心稳定后添加更多工具
    │
    ▼
Phase 4: 记忆系统 (跨会话持久化)
    │
    │  用户数据持久化，需要稳定的基础设施
    │
    ▼
完成
```

## 7. 测试策略

每个阶段都需要完整的测试覆盖：

| 阶段 | 测试重点 |
|------|----------|
| 沙箱系统 | 单元测试 + 集成测试（本地/Docker） |
| 子代理系统 | 并发测试 + 超时测试 + 事件流测试 |
| MCP 集成 | 单元测试 + 模拟服务器测试 |
| 记忆系统 | 单元测试 + 持久化测试 + 并发写入测试 |

## 8. 文档更新

每个阶段完成后需更新：
- README.md - 用户可见的功能更新
- CLAUDE.md - 开发者架构文档
- API 文档 - 新增的 API 端点
- 配置文档 - 新增的配置选项

## 9. 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| Docker 沙箱复杂度高 | 先完成本地沙箱，Docker 作为后续迭代 |
| 记忆系统数据丢失 | 使用原子写入 + 定期备份 |
| MCP 服务器不稳定 | 实现重试机制和降级策略 |
| 子代理并发冲突 | 严格的并发限制和状态隔离 |

## 10. 验收标准

- [ ] 沙箱系统：本地和 Docker 模式都能正常工作
- [ ] 子代理系统：支持 3 个并发代理，15 分钟超时
- [ ] MCP 集成：至少 3 个学术 MCP 服务器正常工作
- [ ] 记忆系统：事实提取准确率 > 80%
- [ ] 所有新功能有 > 80% 测试覆盖率
- [ ] 文档完整且最新
