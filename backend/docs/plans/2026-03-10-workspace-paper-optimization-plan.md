# Workspace & Paper Services 优化实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 优化工作区和论文管理服务，清理重复代码，移除孤立字段，添加 LLM 工具，集成外部数据库导入。

**Architecture:** 分三个阶段渐进式优化：Phase 1 清理重复代码和孤立模型，Phase 2 添加 LLM 可调用的工作区/论文管理工具，Phase 3 集成外部数据库导入功能。

**Tech Stack:** Python 3.11, SQLAlchemy 2.0 (async), LangChain tools, Pytest

---

## Phase 1: 清理重复代码 + 孤立模型

### Task 1: 删除 WorkspaceService 中的重复方法

**Files:**
- Modify: `src/academic/services/workspace_service.py:175-265`
- Modify: `tests/academic/services/test_workspace_service.py:388-586`

**Step 1: 删除 add_paper 方法**

删除 `src/academic/services/workspace_service.py` 中的 `add_paper` 方法（第175-221行）：

```python
# 删除以下代码（第175-221行）:
    async def add_paper(
        self,
        workspace_id: str,
        paper_id: str,
        notes: str | None = None,
        tags: list[str] | None = None,
        is_primary: bool = False,
        read_status: str = "unread",
    ) -> WorkspacePaper:
        """Add a paper to a workspace.
        ...
        """
        # ... 整个方法体
```

**Step 2: 删除 remove_paper 方法**

删除 `src/academic/services/workspace_service.py` 中的 `remove_paper` 方法（第223-242行）：

```python
# 删除以下代码（第223-242行）:
    async def remove_paper(self, workspace_id: str, paper_id: str) -> bool:
        """Remove a paper from a workspace.
        ...
        """
        # ... 整个方法体
```

**Step 3: 删除 _get_workspace_paper 方法**

删除 `src/academic/services/workspace_service.py` 中的 `_get_workspace_paper` 方法（第244-265行）：

```python
# 删除以下代码（第244-265行）:
    async def _get_workspace_paper(
        self, workspace_id: str, paper_id: str
    ) -> WorkspacePaper | None:
        """Get WorkspacePaper association by workspace and paper IDs.
        ...
        """
        # ... 整个方法体
```

**Step 4: 删除测试类**

删除 `tests/academic/services/test_workspace_service.py` 中的三个测试类（第388-586行）：

```python
# 删除以下代码（第388-586行）:
class TestAddPaper:
    """Tests for add_paper method."""
    # ... 整个类

class TestRemovePaper:
    """Tests for remove_paper method."""
    # ... 整个类

class TestGetWorkspacePaper:
    """Tests for _get_workspace_paper helper method."""
    # ... 整个类
```

**Step 5: 运行测试验证**

Run: `cd /home/cjz/academiagpt-v2/backend && python -m pytest tests/academic/services/test_workspace_service.py -v`
Expected: PASS (remaining tests should still pass)

**Step 6: Commit**

```bash
git add src/academic/services/workspace_service.py tests/academic/services/test_workspace_service.py
git commit -m "refactor: remove duplicate paper methods from WorkspaceService

- Remove add_paper, remove_paper, _get_workspace_paper methods
- PaperService.add_to_workspace and remove_from_workspace are the canonical methods
- Update tests to remove tests for deleted methods"
```

---

### Task 2: 移除 PaperChunk.embedding 字段

**Files:**
- Modify: `src/database/models/paper.py:203-254`

**Step 1: 删除 embedding 字段**

修改 `src/database/models/paper.py` 中的 PaperChunk 类，删除 embedding 字段（第237-240行）：

```python
# 原代码（删除）:
    embedding: Mapped[list | None] = mapped_column(
        ARRAY(Float),
        nullable=True,
    )

# PaperChunk 类更新后的完整代码:
class PaperChunk(Base, UUIDMixin, TimestampMixin):
    """Paper chunk for index-based navigation.

    Each chunk is associated with both a paper and a workspace.
    This enables per-workspace isolation while allowing chunks
    from the same paper to exist in multiple workspaces.

    Attributes:
        paper_id: Foreign key to paper
        workspace_id: Foreign key to workspace
        chunk_index: Index of this chunk within the paper
        content: Text content of the chunk
        chunk_metadata: Additional metadata (page number, section, etc.)
    """

    __tablename__ = "paper_chunks"
    __table_args__ = (
        Index("ix_paper_chunks_paper_workspace", "paper_id", "workspace_id"),
    )

    paper_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    # Relationships
    paper: Mapped["Paper"] = relationship("Paper", back_populates="chunks")
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="paper_chunks")

    def __repr__(self) -> str:
        return f"<PaperChunk(paper={self.paper_id}, index={self.chunk_index})>"
```

**Step 2: 更新导入（如需要）**

检查 `paper.py` 顶部的导入，如果 `Float` 和 `ARRAY` 只被 `embedding` 字段使用，则移除：

```python
# 检查导入，如果 Float 和 ARRAY 不再使用则移除
from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
```

注意：如果其他地方仍在使用 `Float` 或 `ARRAY`，保留导入。

**Step 3: 运行测试验证**

Run: `cd /home/cjz/academiagpt-v2/backend && python -m pytest tests/academic/database/ -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/database/models/paper.py
git commit -m "refactor: remove PaperChunk.embedding field

RAG module has been removed, embedding field is no longer needed.
PaperChunk is now used for index-based navigation only."
```

---

### Task 3: 验证 Phase 1 完成

**Step 1: 运行完整测试套件**

Run: `cd /home/cjz/academiagpt-v2/backend && python -m pytest tests/academic/ -v`
Expected: All tests PASS

**Step 2: 检查无调用被删除的方法**

Run: `cd /home/cjz/academiagpt-v2/backend && grep -r "workspace_service.add_paper\|workspace_service.remove_paper\|workspace_service._get_workspace_paper" src/ --include="*.py"`
Expected: No matches

**Step 3: Commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: ensure no references to deleted WorkspaceService methods"
```

---

## Phase 2: 添加 LLM 工具

### Task 4: 添加 create_workspace 工具

**Files:**
- Modify: `src/academic/literature/tools.py`
- Test: `tests/academic/literature/test_tools.py`

**Step 1: 添加导入**

在 `src/academic/literature/tools.py` 顶部添加：

```python
from src.database import Workspace, WorkspaceType
from src.academic.services.workspace_service import WorkspaceService
```

**Step 2: 添加 create_workspace 工具**

在 `src/academic/literature/tools.py` 文件末尾添加：

```python
@tool
async def create_workspace(
    name: str,
    type: str,
    db: AsyncSession = InjectedToolArg,
    discipline: str | None = None,
    description: str | None = None,
) -> dict:
    """Create a new workspace.

    Args:
        name: Workspace name
        type: Workspace type (sci, thesis, proposal, grant, literature_review)
        discipline: Academic discipline (optional, e.g., computer_science)
        description: Workspace description (optional)

    Returns:
        Created workspace info with id, name, type
    """
    # Default user_id for now (should be injected from context in production)
    user_id = "default-user"

    service = WorkspaceService(db)
    try:
        workspace = await service.create(
            user_id=user_id,
            name=name,
            type=type,
            discipline=discipline,
            description=description,
        )
        return {
            "id": str(workspace.id),
            "name": workspace.name,
            "type": workspace.type.value,
            "discipline": workspace.discipline,
            "description": workspace.description,
        }
    except ValueError as e:
        return {"error": str(e)}
```

**Step 3: 添加测试**

在 `tests/academic/literature/test_tools.py` 文件末尾添加：

```python
class TestCreateWorkspaceTool:
    """Tests for create_workspace tool."""

    @pytest.mark.asyncio
    async def test_create_workspace_basic(self):
        """Test creating a workspace with minimal args."""
        mock_db = AsyncMock()

        mock_workspace = MagicMock()
        mock_workspace.id = "ws-123"
        mock_workspace.name = "Test Workspace"
        mock_workspace.type = MagicMock()
        mock_workspace.type.value = "sci"
        mock_workspace.discipline = None
        mock_workspace.description = None

        with patch(
            "src.academic.literature.tools.WorkspaceService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.create.return_value = mock_workspace
            mock_service_class.return_value = mock_service

            result = await literature_tools.create_workspace.coroutine(
                name="Test Workspace", type="sci", db=mock_db
            )

        assert result["id"] == "ws-123"
        assert result["name"] == "Test Workspace"
        assert result["type"] == "sci"

    @pytest.mark.asyncio
    async def test_create_workspace_with_all_fields(self):
        """Test creating a workspace with all fields."""
        mock_db = AsyncMock()

        mock_workspace = MagicMock()
        mock_workspace.id = "ws-456"
        mock_workspace.name = "Thesis Workspace"
        mock_workspace.type = MagicMock()
        mock_workspace.type.value = "thesis"
        mock_workspace.discipline = "computer_science"
        mock_workspace.description = "My thesis work"

        with patch(
            "src.academic.literature.tools.WorkspaceService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.create.return_value = mock_workspace
            mock_service_class.return_value = mock_service

            result = await literature_tools.create_workspace.coroutine(
                name="Thesis Workspace",
                type="thesis",
                discipline="computer_science",
                description="My thesis work",
                db=mock_db,
            )

        assert result["discipline"] == "computer_science"
        assert result["description"] == "My thesis work"

    @pytest.mark.asyncio
    async def test_create_workspace_invalid_type(self):
        """Test creating workspace with invalid type returns error."""
        mock_db = AsyncMock()

        with patch(
            "src.academic.literature.tools.WorkspaceService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.create.side_effect = ValueError("Invalid workspace type")
            mock_service_class.return_value = mock_service

            result = await literature_tools.create_workspace.coroutine(
                name="Bad Workspace", type="invalid_type", db=mock_db
            )

        assert "error" in result
```

**Step 4: 运行测试**

Run: `cd /home/cjz/academiagpt-v2/backend && python -m pytest tests/academic/literature/test_tools.py::TestCreateWorkspaceTool -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/academic/literature/tools.py tests/academic/literature/test_tools.py
git commit -m "feat: add create_workspace LLM tool"
```

---

### Task 5: 添加 get_workspace 工具

**Files:**
- Modify: `src/academic/literature/tools.py`
- Test: `tests/academic/literature/test_tools.py`

**Step 1: 添加 get_workspace 工具**

在 `src/academic/literature/tools.py` 的 `create_workspace` 之后添加：

```python
@tool
async def get_workspace(
    workspace_id: str,
    db: AsyncSession = InjectedToolArg,
) -> dict | None:
    """Get workspace details.

    Args:
        workspace_id: Workspace ID

    Returns:
        Workspace info including paper count, or None if not found
    """
    from sqlalchemy import func, select

    service = WorkspaceService(db)
    workspace = await service.get(workspace_id)

    if not workspace:
        return None

    # Count papers in workspace
    result = await db.execute(
        select(func.count()).where(WorkspacePaper.workspace_id == workspace_id)
    )
    paper_count = result.scalar() or 0

    return {
        "id": str(workspace.id),
        "name": workspace.name,
        "type": workspace.type.value,
        "discipline": workspace.discipline,
        "description": workspace.description,
        "paper_count": paper_count,
        "created_at": workspace.created_at.isoformat() if workspace.created_at else None,
    }
```

**Step 2: 添加测试**

在 `tests/academic/literature/test_tools.py` 的 `TestCreateWorkspaceTool` 之后添加：

```python
class TestGetWorkspaceTool:
    """Tests for get_workspace tool."""

    @pytest.mark.asyncio
    async def test_get_workspace_found(self):
        """Test getting an existing workspace."""
        mock_db = AsyncMock()

        mock_workspace = MagicMock()
        mock_workspace.id = "ws-123"
        mock_workspace.name = "Test Workspace"
        mock_workspace.type = MagicMock()
        mock_workspace.type.value = "sci"
        mock_workspace.discipline = "computer_science"
        mock_workspace.description = "A test workspace"
        mock_workspace.created_at = None

        # Mock count query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 5
        mock_db.execute.return_value = mock_count_result

        with patch(
            "src.academic.literature.tools.WorkspaceService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get.return_value = mock_workspace
            mock_service_class.return_value = mock_service

            result = await literature_tools.get_workspace.coroutine(
                workspace_id="ws-123", db=mock_db
            )

        assert result["id"] == "ws-123"
        assert result["name"] == "Test Workspace"
        assert result["paper_count"] == 5

    @pytest.mark.asyncio
    async def test_get_workspace_not_found(self):
        """Test getting a non-existent workspace."""
        mock_db = AsyncMock()

        with patch(
            "src.academic.literature.tools.WorkspaceService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get.return_value = None
            mock_service_class.return_value = mock_service

            result = await literature_tools.get_workspace.coroutine(
                workspace_id="nonexistent", db=mock_db
            )

        assert result is None
```

**Step 3: 运行测试**

Run: `cd /home/cjz/academiagpt-v2/backend && python -m pytest tests/academic/literature/test_tools.py::TestGetWorkspaceTool -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/academic/literature/tools.py tests/academic/literature/test_tools.py
git commit -m "feat: add get_workspace LLM tool"
```

---

### Task 6: 添加 list_workspaces 工具

**Files:**
- Modify: `src/academic/literature/tools.py`
- Test: `tests/academic/literature/test_tools.py`

**Step 1: 添加 list_workspaces 工具**

在 `src/academic/literature/tools.py` 的 `get_workspace` 之后添加：

```python
@tool
async def list_workspaces(
    db: AsyncSession = InjectedToolArg,
    user_id: str | None = None,
) -> list[dict]:
    """List all workspaces for current user.

    Args:
        user_id: User ID (optional, uses default if not provided)

    Returns:
        List of workspaces with id, name, type, paper_count
    """
    from sqlalchemy import func, select

    # Default user_id for now
    target_user_id = user_id or "default-user"

    service = WorkspaceService(db)
    workspaces = await service.list_by_user(target_user_id)

    result = []
    for ws in workspaces:
        # Count papers for each workspace
        count_result = await db.execute(
            select(func.count()).where(WorkspacePaper.workspace_id == str(ws.id))
        )
        paper_count = count_result.scalar() or 0

        result.append({
            "id": str(ws.id),
            "name": ws.name,
            "type": ws.type.value,
            "discipline": ws.discipline,
            "paper_count": paper_count,
        })

    return result
```

**Step 2: 添加测试**

在 `tests/academic/literature/test_tools.py` 的 `TestGetWorkspaceTool` 之后添加：

```python
class TestListWorkspacesTool:
    """Tests for list_workspaces tool."""

    @pytest.mark.asyncio
    async def test_list_workspaces_with_workspaces(self):
        """Test listing workspaces."""
        mock_db = AsyncMock()

        mock_workspace1 = MagicMock()
        mock_workspace1.id = "ws-1"
        mock_workspace1.name = "Workspace 1"
        mock_workspace1.type = MagicMock()
        mock_workspace1.type.value = "sci"
        mock_workspace1.discipline = "cs"

        mock_workspace2 = MagicMock()
        mock_workspace2.id = "ws-2"
        mock_workspace2.name = "Workspace 2"
        mock_workspace2.type = MagicMock()
        mock_workspace2.type.value = "thesis"
        mock_workspace2.discipline = "physics"

        # Mock count query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 3
        mock_db.execute.return_value = mock_count_result

        with patch(
            "src.academic.literature.tools.WorkspaceService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.list_by_user.return_value = [mock_workspace1, mock_workspace2]
            mock_service_class.return_value = mock_service

            result = await literature_tools.list_workspaces.coroutine(db=mock_db)

        assert len(result) == 2
        assert result[0]["name"] == "Workspace 1"
        assert result[1]["name"] == "Workspace 2"

    @pytest.mark.asyncio
    async def test_list_workspaces_empty(self):
        """Test listing workspaces when user has none."""
        mock_db = AsyncMock()

        with patch(
            "src.academic.literature.tools.WorkspaceService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.list_by_user.return_value = []
            mock_service_class.return_value = mock_service

            result = await literature_tools.list_workspaces.coroutine(db=mock_db)

        assert result == []
```

**Step 3: 运行测试**

Run: `cd /home/cjz/academiagpt-v2/backend && python -m pytest tests/academic/literature/test_tools.py::TestListWorkspacesTool -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/academic/literature/tools.py tests/academic/literature/test_tools.py
git commit -m "feat: add list_workspaces LLM tool"
```

---

### Task 7: 添加 add_paper_to_workspace 工具

**Files:**
- Modify: `src/academic/literature/tools.py`
- Test: `tests/academic/literature/test_tools.py`

**Step 1: 添加导入**

确保 `src/academic/literature/tools.py` 有：

```python
from src.academic.services.paper_service import PaperService
```

**Step 2: 添加 add_paper_to_workspace 工具**

在 `src/academic/literature/tools.py` 的 `list_workspaces` 之后添加：

```python
@tool
async def add_paper_to_workspace(
    paper_id: str,
    workspace_id: str,
    db: AsyncSession = InjectedToolArg,
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
    service = PaperService(db)

    # Check if paper exists
    paper = await service.get(paper_id)
    if not paper:
        return f"Error: Paper {paper_id} not found"

    # Add to workspace
    try:
        await service.add_to_workspace(
            paper_id=paper_id,
            workspace_id=workspace_id,
            notes=notes,
            tags=tags,
        )
        return f"Successfully added '{paper.title}' to workspace"
    except Exception as e:
        return f"Error: {str(e)}"
```

**Step 3: 添加测试**

在 `tests/academic/literature/test_tools.py` 的 `TestListWorkspacesTool` 之后添加：

```python
class TestAddPaperToWorkspaceTool:
    """Tests for add_paper_to_workspace tool."""

    @pytest.mark.asyncio
    async def test_add_paper_success(self):
        """Test adding paper to workspace."""
        mock_db = AsyncMock()

        mock_paper = MagicMock()
        mock_paper.id = "paper-123"
        mock_paper.title = "Test Paper"

        with patch(
            "src.academic.literature.tools.PaperService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get.return_value = mock_paper
            mock_service.add_to_workspace.return_value = MagicMock()
            mock_service_class.return_value = mock_service

            result = await literature_tools.add_paper_to_workspace.coroutine(
                paper_id="paper-123",
                workspace_id="ws-456",
                notes="Important paper",
                tags=["primary"],
                db=mock_db,
            )

        assert "Successfully added" in result
        assert "Test Paper" in result

    @pytest.mark.asyncio
    async def test_add_paper_not_found(self):
        """Test adding non-existent paper."""
        mock_db = AsyncMock()

        with patch(
            "src.academic.literature.tools.PaperService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get.return_value = None
            mock_service_class.return_value = mock_service

            result = await literature_tools.add_paper_to_workspace.coroutine(
                paper_id="nonexistent",
                workspace_id="ws-456",
                db=mock_db,
            )

        assert "Error" in result
        assert "not found" in result
```

**Step 4: 运行测试**

Run: `cd /home/cjz/academiagpt-v2/backend && python -m pytest tests/academic/literature/test_tools.py::TestAddPaperToWorkspaceTool -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/academic/literature/tools.py tests/academic/literature/test_tools.py
git commit -m "feat: add add_paper_to_workspace LLM tool"
```

---

### Task 8: 添加 remove_paper_from_workspace 工具

**Files:**
- Modify: `src/academic/literature/tools.py`
- Test: `tests/academic/literature/test_tools.py`

**Step 1: 添加 remove_paper_from_workspace 工具**

在 `src/academic/literature/tools.py` 的 `add_paper_to_workspace` 之后添加：

```python
@tool
async def remove_paper_from_workspace(
    paper_id: str,
    workspace_id: str,
    db: AsyncSession = InjectedToolArg,
) -> str:
    """Remove paper from workspace.

    Args:
        paper_id: Paper ID
        workspace_id: Workspace ID

    Returns:
        Status message
    """
    service = PaperService(db)

    # Remove from workspace
    removed = await service.remove_from_workspace(
        paper_id=paper_id,
        workspace_id=workspace_id,
    )

    if removed:
        return f"Successfully removed paper {paper_id} from workspace"
    else:
        return f"Error: Paper {paper_id} not found in workspace"
```

**Step 2: 添加测试**

在 `tests/academic/literature/test_tools.py` 的 `TestAddPaperToWorkspaceTool` 之后添加：

```python
class TestRemovePaperFromWorkspaceTool:
    """Tests for remove_paper_from_workspace tool."""

    @pytest.mark.asyncio
    async def test_remove_paper_success(self):
        """Test removing paper from workspace."""
        mock_db = AsyncMock()

        with patch(
            "src.academic.literature.tools.PaperService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.remove_from_workspace.return_value = True
            mock_service_class.return_value = mock_service

            result = await literature_tools.remove_paper_from_workspace.coroutine(
                paper_id="paper-123",
                workspace_id="ws-456",
                db=mock_db,
            )

        assert "Successfully removed" in result

    @pytest.mark.asyncio
    async def test_remove_paper_not_in_workspace(self):
        """Test removing paper that's not in workspace."""
        mock_db = AsyncMock()

        with patch(
            "src.academic.literature.tools.PaperService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.remove_from_workspace.return_value = False
            mock_service_class.return_value = mock_service

            result = await literature_tools.remove_paper_from_workspace.coroutine(
                paper_id="paper-123",
                workspace_id="ws-456",
                db=mock_db,
            )

        assert "Error" in result
        assert "not found" in result
```

**Step 3: 运行测试**

Run: `cd /home/cjz/academiagpt-v2/backend && python -m pytest tests/academic/literature/test_tools.py::TestRemovePaperFromWorkspaceTool -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/academic/literature/tools.py tests/academic/literature/test_tools.py
git commit -m "feat: add remove_paper_from_workspace LLM tool"
```

---

### Task 9: 更新 agent.py 注册新工具

**Files:**
- Modify: `src/agents/lead_agent/agent.py:168-177`

**Step 1: 更新工具导入**

修改 `src/agents/lead_agent/agent.py` 中的 literature tools 导入部分：

```python
    # Literature navigation tools (TOC-driven)
    try:
        from src.academic.literature.tools import (
            list_papers,
            get_section,
            search_external,
            get_paper_by_doi,
            # New workspace/paper management tools
            create_workspace,
            get_workspace,
            list_workspaces,
            add_paper_to_workspace,
            remove_paper_from_workspace,
        )
        tools.extend([
            list_papers,
            get_section,
            search_external,
            get_paper_by_doi,
            create_workspace,
            get_workspace,
            list_workspaces,
            add_paper_to_workspace,
            remove_paper_from_workspace,
        ])
    except ImportError:
        pass  # Literature tools not yet implemented
```

**Step 2: 运行测试**

Run: `cd /home/cjz/academiagpt-v2/backend && python -m pytest tests/agents/test_pipeline_assembly.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add src/agents/lead_agent/agent.py
git commit -m "feat: register new workspace/paper management tools in lead agent"
```

---

### Task 10: 验证 Phase 2 完成

**Step 1: 运行完整测试套件**

Run: `cd /home/cjz/academiagpt-v2/backend && python -m pytest tests/academic/literature/test_tools.py -v`
Expected: All tests PASS

**Step 2: 验证工具可用**

Run: `cd /home/cjz/academiagpt-v2/backend && python -c "from src.academic.literature.tools import create_workspace, get_workspace, list_workspaces, add_paper_to_workspace, remove_paper_from_workspace; print('All tools imported successfully')"`
Expected: "All tools imported successfully"

---

## Phase 3: 外部数据库导入集成

### Task 11: 添加 Paper.source_url 字段

**Files:**
- Modify: `src/database/models/paper.py:15-102`

**Step 1: 添加 source_url 字段**

在 `src/database/models/paper.py` 的 Paper 类中添加 `source_url` 字段：

```python
class Paper(Base, UUIDMixin, TimestampMixin):
    """Paper model for academic literature (globally shared).
    ...
    """

    __tablename__ = "papers"

    doi: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    venue: Mapped[str | None] = mapped_column(Text, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="manual_upload",
    )
    # NEW: External source URL
    source_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    external_ids: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    toc: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    citation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ... rest of the class remains unchanged
```

**Step 2: 更新 PaperService.create 方法签名**

修改 `src/academic/services/paper_service.py` 的 `create` 方法，添加 `source_url` 参数：

```python
async def create(
    self,
    title: str,
    authors: list[dict],
    doi: str | None = None,
    year: int | None = None,
    venue: str | None = None,
    abstract: str | None = None,
    source: str = "manual_upload",
    source_url: str | None = None,  # NEW
) -> Paper:
    """Create a new paper.

    Args:
        title: Paper title
        authors: List of author dicts with 'name' and optionally 'affiliation'
        doi: Digital Object Identifier (optional)
        year: Publication year (optional)
        venue: Publication venue (optional)
        abstract: Paper abstract (optional)
        source: Source of paper data (default: "manual_upload")
        source_url: External source URL (optional)

    Returns:
        Created paper object
    """
    # Check if paper with same DOI exists
    if doi:
        existing = await self.get_by_doi(doi)
        if existing:
            return existing

    paper = Paper(
        doi=doi,
        title=title,
        authors=authors or [],
        year=year,
        venue=venue,
        abstract=abstract,
        source=source,
        source_url=source_url,  # NEW
    )
    self.db.add(paper)
    await self.db.commit()
    await self.db.refresh(paper)
    return paper
```

**Step 3: 运行测试**

Run: `cd /home/cjz/academiagpt-v2/backend && python -m pytest tests/academic/services/test_paper_service.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/database/models/paper.py src/academic/services/paper_service.py
git commit -m "feat: add source_url field to Paper model

Used to store external database URL when importing papers."
```

---

### Task 12: 添加 import_paper 工具

**Files:**
- Modify: `src/academic/literature/tools.py`
- Test: `tests/academic/literature/test_tools.py`

**Step 1: 添加 import_paper 工具**

在 `src/academic/literature/tools.py` 的 `remove_paper_from_workspace` 之后添加：

```python
@tool
async def import_paper(
    query: str,
    workspace_id: str,
    db: AsyncSession = InjectedToolArg,
    source: Literal["semantic_scholar", "arxiv", "crossref", "openalex"] = "semantic_scholar",
) -> str:
    """Search external database and import paper to workspace.

    Args:
        query: Search query (title, DOI, or keywords)
        workspace_id: Target workspace ID
        source: External database to search (default: semantic_scholar)

    Returns:
        Import status with paper info
    """
    # Map source to client
    clients = {
        "semantic_scholar": SemanticScholarClient,
        "arxiv": ArxivClient,
        "crossref": CrossrefClient,
        "openalex": OpenAlexClient,
    }

    client_class = clients.get(source)
    if not client_class:
        return f"Error: Unknown source '{source}'"

    client = client_class()

    # Search for paper
    try:
        results = await client.search(query, limit=1)
        if not results:
            return f"No papers found for query: {query}"

        paper_data = results[0]
    except Exception as e:
        return f"Error searching {source}: {str(e)}"

    # Create paper record
    paper_service = PaperService(db)

    try:
        paper = await paper_service.create(
            title=paper_data.title,
            authors=[
                {"name": a.name, "affiliation": a.affiliation}
                for a in paper_data.authors
            ],
            doi=paper_data.doi,
            year=paper_data.year,
            venue=paper_data.venue,
            abstract=paper_data.abstract,
            source=source,
            source_url=paper_data.url,
        )

        # Add to workspace
        await paper_service.add_to_workspace(
            paper_id=str(paper.id),
            workspace_id=workspace_id,
        )

        return f"Successfully imported: {paper.title} (from {source})"
    except Exception as e:
        return f"Error importing paper: {str(e)}"
```

**Step 2: 添加测试**

在 `tests/academic/literature/test_tools.py` 的 `TestRemovePaperFromWorkspaceTool` 之后添加：

```python
class TestImportPaperTool:
    """Tests for import_paper tool."""

    @pytest.mark.asyncio
    async def test_import_paper_success(self):
        """Test importing paper from external database."""
        mock_db = AsyncMock()

        # Mock search result
        mock_author = MagicMock()
        mock_author.name = "John Doe"
        mock_author.affiliation = "MIT"

        mock_result = MagicMock()
        mock_result.title = "Test Paper"
        mock_result.authors = [mock_author]
        mock_result.doi = "10.1234/test"
        mock_result.year = 2024
        mock_result.venue = "NeurIPS"
        mock_result.abstract = "Test abstract"
        mock_result.url = "https://example.com/paper"

        # Mock paper
        mock_paper = MagicMock()
        mock_paper.id = "paper-new"
        mock_paper.title = "Test Paper"

        with patch(
            "src.academic.literature.tools.SemanticScholarClient"
        ) as mock_client_class, patch(
            "src.academic.literature.tools.PaperService"
        ) as mock_service_class:
            mock_client = AsyncMock()
            mock_client.search.return_value = [mock_result]
            mock_client_class.return_value = mock_client

            mock_service = AsyncMock()
            mock_service.create.return_value = mock_paper
            mock_service.add_to_workspace.return_value = MagicMock()
            mock_service_class.return_value = mock_service

            result = await literature_tools.import_paper.coroutine(
                query="machine learning",
                workspace_id="ws-123",
                source="semantic_scholar",
                db=mock_db,
            )

        assert "Successfully imported" in result
        assert "Test Paper" in result

    @pytest.mark.asyncio
    async def test_import_paper_no_results(self):
        """Test importing when no papers found."""
        mock_db = AsyncMock()

        with patch(
            "src.academic.literature.tools.SemanticScholarClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.search.return_value = []
            mock_client_class.return_value = mock_client

            result = await literature_tools.import_paper.coroutine(
                query="nonexistent paper xyz123",
                workspace_id="ws-123",
                source="semantic_scholar",
                db=mock_db,
            )

        assert "No papers found" in result

    @pytest.mark.asyncio
    async def test_import_paper_arxiv_source(self):
        """Test importing from arXiv."""
        mock_db = AsyncMock()

        mock_author = MagicMock()
        mock_author.name = "Jane Smith"
        mock_author.affiliation = None

        mock_result = MagicMock()
        mock_result.title = "arXiv Paper"
        mock_result.authors = [mock_author]
        mock_result.doi = None
        mock_result.year = 2024
        mock_result.venue = None
        mock_result.abstract = "Abstract"
        mock_result.url = "https://arxiv.org/abs/1234.5678"

        mock_paper = MagicMock()
        mock_paper.id = "paper-arxiv"
        mock_paper.title = "arXiv Paper"

        with patch(
            "src.academic.literature.tools.ArxivClient"
        ) as mock_client_class, patch(
            "src.academic.literature.tools.PaperService"
        ) as mock_service_class:
            mock_client = AsyncMock()
            mock_client.search.return_value = [mock_result]
            mock_client_class.return_value = mock_client

            mock_service = AsyncMock()
            mock_service.create.return_value = mock_paper
            mock_service.add_to_workspace.return_value = MagicMock()
            mock_service_class.return_value = mock_service

            result = await literature_tools.import_paper.coroutine(
                query="deep learning",
                workspace_id="ws-456",
                source="arxiv",
                db=mock_db,
            )

        assert "Successfully imported" in result
        assert "arXiv Paper" in result
```

**Step 3: 运行测试**

Run: `cd /home/cjz/academiagpt-v2/backend && python -m pytest tests/academic/literature/test_tools.py::TestImportPaperTool -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/academic/literature/tools.py tests/academic/literature/test_tools.py
git commit -m "feat: add import_paper LLM tool for external database import"
```

---

### Task 13: 更新 agent.py 注册 import_paper 工具

**Files:**
- Modify: `src/agents/lead_agent/agent.py`

**Step 1: 更新工具导入**

修改 `src/agents/lead_agent/agent.py` 中的 literature tools 导入部分，添加 `import_paper`：

```python
    # Literature navigation tools (TOC-driven)
    try:
        from src.academic.literature.tools import (
            list_papers,
            get_section,
            search_external,
            get_paper_by_doi,
            # Workspace/paper management tools
            create_workspace,
            get_workspace,
            list_workspaces,
            add_paper_to_workspace,
            remove_paper_from_workspace,
            # External import tool
            import_paper,
        )
        tools.extend([
            list_papers,
            get_section,
            search_external,
            get_paper_by_doi,
            create_workspace,
            get_workspace,
            list_workspaces,
            add_paper_to_workspace,
            remove_paper_from_workspace,
            import_paper,
        ])
    except ImportError:
        pass  # Literature tools not yet implemented
```

**Step 2: 运行测试**

Run: `cd /home/cjz/academiagpt-v2/backend && python -m pytest tests/agents/ -v`
Expected: PASS

**Step 3: Commit**

```bash
git add src/agents/lead_agent/agent.py
git commit -m "feat: register import_paper tool in lead agent"
```

---

### Task 14: 验证 Phase 3 完成

**Step 1: 运行完整测试套件**

Run: `cd /home/cjz/academiagpt-v2/backend && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

**Step 2: 验证所有工具可用**

Run: `cd /home/cjz/academiagpt-v2/backend && python -c "
from src.academic.literature.tools import (
    list_papers, get_section, search_external, get_paper_by_doi,
    create_workspace, get_workspace, list_workspaces,
    add_paper_to_workspace, remove_paper_from_workspace,
    import_paper
)
print('All 10 tools imported successfully')
"`
Expected: "All 10 tools imported successfully"

**Step 3: 最终提交**

```bash
git add -A
git commit -m "feat: complete workspace/paper services optimization

Phase 1: Remove duplicate code and orphaned fields
- Delete WorkspaceService.add_paper, remove_paper, _get_workspace_paper
- Remove PaperChunk.embedding field

Phase 2: Add LLM tools
- create_workspace, get_workspace, list_workspaces
- add_paper_to_workspace, remove_paper_from_workspace

Phase 3: External database import
- Add Paper.source_url field
- Add import_paper tool

All tools registered in lead agent"
```

---

## 验收清单

### Phase 1
- [ ] WorkspaceService 重复方法已删除
- [ ] PaperChunk.embedding 字段已删除
- [ ] 测试通过

### Phase 2
- [ ] 5 个新 LLM 工具可用
- [ ] 工具已注册到 agent
- [ ] 工具测试通过

### Phase 3
- [ ] import_paper 工具可用
- [ ] Paper.source_url 字段已添加
- [ ] 端到端测试通过
