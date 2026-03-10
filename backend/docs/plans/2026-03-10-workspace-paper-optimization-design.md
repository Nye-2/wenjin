# Workspace & Paper Services 优化设计文档

> **创建日期**: 2026-03-10
> **状态**: 已批准
> **作者**: Claude + 用户

## 1. 概述

### 1.1 背景

AcademiaGPT v2 完成文献模块 TOC 驱动重构后，工作区和论文服务存在以下问题：
- `WorkspaceService` 和 `PaperService` 存在重复代码
- `PaperChunk.embedding` 字段孤立（RAG 已移除）
- 缺少 LLM 可调用的工作区/论文管理工具
- 外部数据库搜索结果无法直接导入到工作区

### 1.2 目标

优化工作区和论文管理服务：
- 清理重复代码
- 移除孤立字段
- 添加 LLM 工具
- 集成外部数据库导入

## 2. Phase 1: 清理重复代码 + 孤立模型

### 2.1 删除重复代码

**删除 WorkspaceService 中的重复方法**：

| 方法 | 处理 |
|------|------|
| `WorkspaceService.add_paper()` | 删除，统一使用 `PaperService.add_to_workspace()` |
| `WorkspaceService.remove_paper()` | 删除，
统一使用 `PaperService.remove_from_workspace()` |
| `WorkspaceService._get_workspace_paper()` | 删除 |

**保留**：
- `PaperService.add_to_workspace()` - 论文加入工作区
- `PaperService.remove_from_workspace()` - 论文移出工作区

### 2.2 清理孤立模型

**修改 PaperChunk 模型**：

```python
# src/database/models/paper.py

class PaperChunk(Base, UUIDMixin, TimestampMixin):
    """Paper chunk for index-based navigation (no embeddings)."""

    paper_id: Mapped[str] = ...
    workspace_id: Mapped[str] = ...
    chunk_index: Mapped[int] = ...
    content: Mapped[str] = ...
    # embedding: 删除此字段
    chunk_metadata: Mapped[dict] = ...
```

### 2.3 文件变更

| 文件 | 变更 |
|------|------|
| `src/academic/services/workspace_service.py` | 删除 add_paper, remove_paper,
_get_workspace_paper |
| `src/database/models/paper.py` | 删除 PaperChunk.embedding 字段 |
| `alembic/versions/` | 可选：创建迁移移除 embedding 列 |

## 3. Phase 2: 添加 LLM 工具

### 3.1 新增工作区管理工具

```python
# src/academic/literature/tools.py (扩展)

@tool
async def create_workspace(
    name: str,
    type: str,
    db: AsyncSession,
    discipline: str | None = None,
    description: str | None = None,
) -> dict:
    """Create a new workspace.

    Args:
        name: Workspace name
        type: Workspace type (sci, thesis, proposal, grant, literature_review)
        discipline: Academic discipline (optional)
        description: Workspace description (optional)

    Returns:
        Created workspace info
    """
    pass

@tool
async def get_workspace(
    workspace_id: str,
    db: AsyncSession,
) -> dict:
    """Get workspace details.

    Args:
        workspace_id: Workspace ID

    Returns:
        Workspace info including paper count
    """
    pass

@tool
async def list_workspaces(
    db: AsyncSession,
    user_id: str | None = None,
) -> list[dict]:
    """List all workspaces for current user.

    Returns:
        List of workspaces
    """
    pass
```

### 3.2 新增论文管理工具

```python
@tool
async def add_paper_to_workspace(
    paper_id: str,
    workspace_id: str,
    db: AsyncSession,
    notes: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Add an existing paper to workspace.

    Args:
        paper_id: Paper ID
        workspace_id: Target workspace ID
        notes: User notes (optional)
        tags: Tags for categorization (optional)

    Returns:
        Status message
    """
    pass

@tool
async def remove_paper_from_workspace(
    paper_id: str,
    workspace_id: str,
    db: AsyncSession,
) -> str:
    """Remove paper from workspace.

    Args:
        paper_id: Paper ID
        workspace_id: Workspace ID

    Returns:
        Status message
    """
    pass
```

### 3.3 工具注入

使用 `InjectedToolArg` 模式注入 `AsyncSession`：

```python
from langchain_core.tools import InjectedToolArg

# 在工具中使用
db = InjectedToolArg(AsyncSession, "db")
```

## 4. Phase 3: 外部数据库导入集成

### 4.1 新增导入工具

```python
@tool
async def import_paper(
    query: str,
    workspace_id: str,
    source: Literal["semantic_scholar", "arxiv", "crossref", "openalex"] = "semantic_scholar",
    db: AsyncSession,
) -> str:
    """Search external database and import paper to workspace.

    Args:
        query: Search query (title, DOI, or keywords)
        workspace_id: Target workspace ID
        source: External database to search

    Returns:
        Import status with paper info
    """
    pass
```

### 4.2 导入流程

```
1. 调用外部数据库客户端搜索
2. 获取第一个结果（或最匹配）
3. 创建 Paper 记录
4. 关联到 WorkspacePaper
5. 返回导入结果
```

### 4.3 数据映射

| 外部字段 | 内部字段 |
|----------|----------|
| title | title |
| authors | authors (标准化为 [{name, affiliation}]) |
| year | year |
| doi | doi |
| url | source_url (新增字段) |
| abstract | abstract |
| venue | venue |
| source | source (设为 "semantic_scholar" 等) |

### 4.4 Paper 模型扩展

```python
# src/database/models/paper.py

class Paper(Base, UUIDMixin, TimestampMixin):
    # ... 现有字段 ...
    source_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )  # 新增：外部来源 URL
```

## 5. 验收标准

### Phase 1
- [ ] WorkspaceService 重复方法已删除
- [ ] PaperChunk.embedding 字段已删除
- [ ] 所有测试通过

### Phase 2
- [ ] 5 个新 LLM 工具可用
- [ ] 工具已注册到 agent
- [ ] 工具测试通过

### Phase 3
- [ ] import_paper 工具可用
- [ ] 4 个外部数据库均可导入
- [ ] Paper.source_url 字段已添加
- [ ] 端到端测试通过

## 6. 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 删除方法影响现有调用 | 全局搜索确保无遗漏调用 |
| 工具注入失败 | 参考现有 list_papers 工具模式 |
| 外部 API 限流 | 复用现有客户端的 httpx 超时配置 |
