# Dead Code Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove all confirmed dead code and redundant architecture remnants after migration to the super agent harness.

**Architecture:** Two-phase approach — first land the in-progress phase1 infrastructure refactoring (merge branch + commit dirty working tree), then systematically delete confirmed-dead modules, classes, functions, and orphaned tests. Each deletion is verified by running the full test suite.

**Tech Stack:** Python 3.13, pytest, git

---

### Task 0: Land phase1 infrastructure refactoring

**Context:** The working tree has 58 modified files + 3 new files from `feat/phase1-pipeline-infrastructure`. These include subagent runtime/task_builder extraction, handler DI, type annotations, and the deletion of `src/subagents/executor.py`. All of this must be committed to master before we can clean up dead code on top.

**Step 1: Merge the phase1 branch commit**

```bash
cd /home/cjz/wenjin/backend
git merge feat/phase1-pipeline-infrastructure
```

**Step 2: Stage and commit all remaining working tree changes**

```bash
git add -A
git commit -m "refactor: land phase1 pipeline infrastructure

- Extract subagent runtime bootstrap to src/subagents/runtime.py
- Extract task construction to src/subagents/task_builder.py
- Add handler DI factories in src/gateway/deps/application.py
- Add thread binding validation and per-task model selection
- Comprehensive type annotations across subagents, task, gateway
- Delete obsolete src/subagents/executor.py
- Fix Celery worker signal registration (explicit connect)"
```

**Step 3: Run tests to verify**

```bash
python -m pytest tests/ --ignore=tests/agents/lead_agent/test_feature_bridge.py -q
```

Expected: 2379+ passed, same 3 pre-existing failures in test_upload_paper.py

**Step 4: Push**

```bash
git push
```

---

### Task 1: Delete dead gateway adapters

**Files:**
- Delete: `src/gateway/adapters/skill_adapter.py`
- Delete: `src/gateway/adapters/workspace_adapter.py`
- Modify: `src/gateway/adapters/__init__.py`
- Delete: `tests/gateway/test_adapters.py`

**Evidence:** Both adapter classes have zero production imports. `SkillAdapter` wraps `load_skills()` but is never instantiated. `WorkspaceAdapter` is an in-memory mock never used anywhere.

**Step 1: Delete adapter files and their test**

```bash
rm src/gateway/adapters/skill_adapter.py
rm src/gateway/adapters/workspace_adapter.py
rm tests/gateway/test_adapters.py
```

**Step 2: Clean up `src/gateway/adapters/__init__.py`**

Replace entire contents with:

```python
"""Frontend API adapters for bridging frontend with backend services."""
```

If the adapters directory has no other files besides `__init__.py`, delete the entire directory instead:

```bash
rm -r src/gateway/adapters/
```

But first check if any other adapter files exist.

**Step 3: Run tests**

```bash
python -m pytest tests/ --ignore=tests/agents/lead_agent/test_feature_bridge.py -q
```

Expected: Same pass count minus the deleted adapter tests. No new failures.

**Step 4: Commit**

```bash
git add -u
git commit -m "refactor: remove dead gateway adapters (SkillAdapter, WorkspaceAdapter)

Both classes had zero production callers. SkillAdapter was a wrapper
around load_skills() never instantiated. WorkspaceAdapter was an
in-memory mock placeholder."
```

---

### Task 2: Delete dead skills parser module

**Files:**
- Delete: `src/skills/parser.py`
- Delete: `tests/skills/test_parser.py`
- Modify: `src/skills/__init__.py`

**Evidence:** `SkillParser` and `ParsedSkill` have zero production callers. The skill loader (`src/skills/loader.py`) implements its own inline parsing logic and does NOT use SkillParser.

**Step 1: Delete parser files**

```bash
rm src/skills/parser.py
rm tests/skills/test_parser.py
```

**Step 2: Remove parser exports from `src/skills/__init__.py`**

Remove the import line:
```python
from .parser import ParsedSkill, SkillParser
```

Remove from `__all__`:
```python
    "SkillParser",
    "ParsedSkill",
```

The result should be:

```python
"""Skills module initialization."""

from .base import BaseSkill, SkillInput, SkillOutput
from .executor import (
    SkillExecutionError,
    SkillExecutor,
    SkillNotFoundError,
    SkillValidationError,
)
from .loader import Skill, load_skills

__all__ = [
    # Loader
    "load_skills",
    "Skill",
    # Base skill classes
    "BaseSkill",
    "SkillInput",
    "SkillOutput",
    # Executor
    "SkillExecutor",
    "SkillExecutionError",
    "SkillNotFoundError",
    "SkillValidationError",
]
```

**Step 3: Run tests**

```bash
python -m pytest tests/ --ignore=tests/agents/lead_agent/test_feature_bridge.py -q
```

Expected: Same pass count minus deleted parser tests. No new failures.

**Step 4: Commit**

```bash
git add -u
git commit -m "refactor: remove dead SkillParser module

SkillParser/ParsedSkill had zero production callers. The skill loader
implements its own inline parsing and never uses this module."
```

---

### Task 3: Delete dead workspace tool functions from literature/tools.py

**Files:**
- Modify: `src/academic/literature/tools.py` (lines 254-580)

**Evidence:** Seven @tool functions (`create_workspace`, `get_workspace`, `list_workspaces`, `add_paper_to_workspace`, `remove_paper_from_workspace`, `import_paper`, `search_workspace`) are defined but NOT exported from `src/academic/literature/__init__.py` and not imported anywhere.

**Step 1: Delete lines 253-580 from `src/academic/literature/tools.py`**

Remove everything after the `get_paper_by_doi` function (after line 252). The file should end after `get_paper_by_doi` returns `None`.

Also check if the `WorkspaceService` import (line 12) and `_build_import_client` helper (lines 38-48) and `_serialize_import_author` helper (lines 51-61) are still needed after the deletion. If `import_paper` was the only caller of `_build_import_client` and `_serialize_import_author`, remove those too. `search_external` also uses `_build_import_client` via direct client construction so it doesn't use the helper — but check `_build_import_client` callers.

Actually, looking at the code: `_build_import_client` is only used by `import_paper` (line 459). `_serialize_import_author` is only used by `import_paper` (line 477). Both can be removed.

After deletion, also check if `WorkspaceService` import is still used — it was only used by `create_workspace` (line 276), `get_workspace` (line 311), and `list_workspaces` (line 353). Remove the import.

The `PaperSection` import from line 13 — only used by `search_workspace`. Remove it.

The `WorkspacePaper` import from line 13 — used by `list_papers` (line 81) and `get_workspace`/`list_workspaces` (dead). Still needed for `list_papers`.

Final state of imports:

```python
import logging
from typing import Annotated, Any, Literal

from langchain_core.tools import InjectedToolArg, tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.services.paper_service import PaperService
from src.database import Paper, PaperExtraction, WorkspacePaper

from .external import (
    ArxivClient,
    CrossrefClient,
    ExternalDBBase,
    OpenAlexClient,
    SemanticScholarClient,
)
from .navigation.section_loader import SectionLoader
from .navigation.toc_service import TocService
```

Note: `PaperSection` removed, `WorkspaceService` removed.

**Step 2: Run tests**

```bash
python -m pytest tests/ --ignore=tests/agents/lead_agent/test_feature_bridge.py -q
```

Expected: Same pass count. No failures (these functions had no tests since they were never wired in).

**Step 3: Commit**

```bash
git add src/academic/literature/tools.py
git commit -m "refactor: remove 7 dead workspace tool functions from literature/tools

create_workspace, get_workspace, list_workspaces, add_paper_to_workspace,
remove_paper_from_workspace, import_paper, search_workspace were defined
but never exported or imported. Also removed their helper functions
(_build_import_client, _serialize_import_author) and unused imports."
```

---

### Task 4: Delete dead TaskService.list_task_records() method

**Files:**
- Modify: `src/task/service.py` (lines 321-334)

**Evidence:** Zero callers. `list_tasks()` (line 297) is the method actually used by routes.

**Step 1: Delete lines 321-334 from `src/task/service.py`**

Remove:
```python
    async def list_task_records(
        self,
        user_id: str,
        status: str | None = None,
        task_type: str | None = None,
        limit: int = 20,
    ) -> list[Any]:
        """List persisted task records for a user."""
        return await self._store.list_user_tasks(
            user_id=user_id,
            status=status,
            task_type=task_type,
            limit=limit,
        )
```

Check if the `Any` import from `typing` is still needed elsewhere in the file. If not, remove it from the import line.

**Step 2: Run tests**

```bash
python -m pytest tests/ --ignore=tests/agents/lead_agent/test_feature_bridge.py -q
```

Expected: Same pass count. No failures.

**Step 3: Commit**

```bash
git add src/task/service.py
git commit -m "refactor: remove dead TaskService.list_task_records()

Zero callers. list_tasks() is the method actually used by routes."
```

---

### Task 5: Delete empty legacy middleware directory

**Files:**
- Delete: `src/agents/middleware/` (singular — the empty directory with only `__pycache__`)

**Evidence:** This directory was renamed to `middlewares/` (plural) during refactoring. It contains only `__pycache__/`, no Python source files. Zero imports reference `agents.middleware` (singular).

**Step 1: Delete the empty directory**

```bash
rm -rf src/agents/middleware/
```

**Step 2: Run tests**

```bash
python -m pytest tests/ --ignore=tests/agents/lead_agent/test_feature_bridge.py -q
```

Expected: Same pass count. No failures.

**Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove empty legacy agents/middleware/ directory

Renamed to agents/middlewares/ (plural) during earlier refactoring.
Only contained __pycache__."
```

---

### Task 6: Full regression run + push

**Step 1: Run full test suite**

```bash
cd /home/cjz/wenjin/backend
python -m pytest tests/ --ignore=tests/agents/lead_agent/test_feature_bridge.py -q
```

Expected: 2370+ passed (slightly fewer than before due to removed dead tests), same 3 pre-existing failures in test_upload_paper.py. Zero new failures.

**Step 2: Push all changes**

```bash
git push
```

**Step 3: Clean up stale local branches**

```bash
git branch -d feat/phase1-pipeline-infrastructure
```

Delete worktree branches if no longer needed:
```bash
git branch -d worktree-agent-a771ac03 worktree-agent-a87a3f3a 2>/dev/null || true
```
