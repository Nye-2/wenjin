# Team Real-Name Agent Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first production-ready B+ team-kernel vertical slice: DataService-backed agent templates, capability team policies, dynamic Lead Agent recruitment, execution facts for team members, and frontend projection of the active team.

**Architecture:** Keep Wenjin's existing Chat Agent -> Lead Agent -> ExecutionRecord -> result_card -> Rooms flow. Add `runtime.mode: team_kernel` as an explicit capability mode; dynamicity lives in structured `AgentInvocation` facts recorded through execution nodes/events, while LangGraph remains a stable control loop. Agent capability stays high-ceiling through broad tool affinity and sandbox-backed risk gates, not low-permission worker prompts.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Pydantic v2, LangGraph, DataService internal API/client, Next.js 16, React 19, TypeScript, Zustand, Vitest.

---

## Scope Check

The spec spans DataService catalog, Lead Agent runtime, execution projection, frontend UI, and seed data. This plan is a single vertical slice because each subsystem is required to make a visible team run work end-to-end. It deliberately does not implement the full admin dashboard editor for templates; backend DataService endpoints and seed loading make templates runtime-editable, and UI editing can be a later admin-dashboard plan.

## File Structure

Create:

- `backend/src/database/models/agent_template.py` — ORM storage for DataService-owned agent templates.
- `backend/alembic/versions/076_agent_templates.py` — migration for `agent_templates`.
- `backend/src/agents/lead_agent/v2/team/__init__.py` — team-kernel package export.
- `backend/src/agents/lead_agent/v2/team/contracts.py` — Pydantic contracts for templates, policies, invocations, blackboard, gates.
- `backend/src/agents/lead_agent/v2/team/policy.py` — capability policy parsing, validation, recruitment, effective tool/skill resolution.
- `backend/src/agents/lead_agent/v2/team/kernel.py` — fixed team-kernel runtime loop.
- `backend/seed/agent_templates/*.yaml` — initial expert archetype templates.
- `backend/tests/agents/lead_agent/v2/test_team_policy.py` — policy and permission tests.
- `backend/tests/agents/lead_agent/v2/test_team_kernel.py` — runtime loop tests.
- `frontend/lib/__tests__/execution-run-view.team.test.ts` — run projection tests for dynamic teams.

Modify:

- `backend/src/database/models/__init__.py` — export `AgentTemplate`.
- `backend/src/dataservice/domains/catalog/contracts.py` — add `AgentTemplateRecord`.
- `backend/src/dataservice/domains/catalog/projection.py` — project `AgentTemplate` rows.
- `backend/src/dataservice/domains/catalog/repository.py` — list/get/upsert/delete agent templates.
- `backend/src/dataservice/domains/catalog/service.py` — validate and materialize agent template values.
- `backend/src/dataservice/domains/catalog/seed_loader.py` — load `backend/seed/agent_templates/*.yaml`.
- `backend/src/dataservice/catalog_api.py` — public in-process DataService methods for templates.
- `backend/src/dataservice_app/routers/catalog.py` — internal HTTP endpoints for templates.
- `backend/src/dataservice_client/contracts/catalog.py` — client payload models for templates.
- `backend/src/dataservice_client/client.py` — client methods for templates.
- `backend/src/database/bootstrap_admin.py` — seed agent templates before capabilities.
- `backend/src/agents/lead_agent/v2/runtime.py` — route `team_kernel` capabilities to the new runtime and publish team graph structure.
- `backend/src/subagents/v2/base.py` — pass invocation/team metadata to subagents without changing existing subagent call sites.
- `frontend/lib/api/types.ts` — add optional team fields on execution graph nodes and runtime state.
- `frontend/lib/execution-run-view.ts` — project dynamic team roster and quality gates.
- `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx` — render team roster and gate summary from `RunView`.

---

## Task 1: DataService AgentTemplate Catalog

**Files:**
- Create: `backend/src/database/models/agent_template.py`
- Create: `backend/alembic/versions/076_agent_templates.py`
- Create: `backend/seed/agent_templates/research_scholar.yaml`
- Create: `backend/seed/agent_templates/writing_editor.yaml`
- Create: `backend/seed/agent_templates/critical_reviewer.yaml`
- Create: `backend/seed/agent_templates/generalist_assistant.yaml`
- Modify: `backend/src/database/models/__init__.py`
- Modify: `backend/src/dataservice/domains/catalog/contracts.py`
- Modify: `backend/src/dataservice/domains/catalog/projection.py`
- Modify: `backend/src/dataservice/domains/catalog/repository.py`
- Modify: `backend/src/dataservice/domains/catalog/service.py`
- Modify: `backend/src/dataservice/domains/catalog/seed_loader.py`
- Modify: `backend/src/dataservice/catalog_api.py`
- Modify: `backend/src/dataservice_app/routers/catalog.py`
- Modify: `backend/src/dataservice_client/contracts/catalog.py`
- Modify: `backend/src/dataservice_client/client.py`
- Modify: `backend/src/database/bootstrap_admin.py`
- Test: `backend/tests/dataservice/test_catalog_domain.py`
- Test: `backend/tests/dataservice/test_foundation.py`

- [ ] **Step 1: Write failing catalog domain tests**

Add tests to `backend/tests/dataservice/test_catalog_domain.py`:

```python
def _agent_template_v1_data() -> dict[str, Any]:
    return {
        "schema_version": "agent_template.v1",
        "id": "research_scholar.v1",
        "enabled": True,
        "display_role": "文献专家",
        "category": "research",
        "description": "检索、筛选、归纳文献，并检查引用与证据链质量。",
        "persona_prompt": "You are a rigorous academic research specialist.",
        "default_skills": ["literature_search.v1", "citation_screening.v1"],
        "tool_affinity": {
            "preferred": ["web_search", "library_read", "citation_parser"],
            "can_request": ["document_read", "artifact_create"],
        },
        "risk_profile": {
            "network": "normal",
            "filesystem": "no_direct_write",
            "code_execution": "not_needed",
            "room_write": "staged_only",
        },
        "output_contracts": ["literature_evidence_report.v1"],
        "quality_expectations": ["claims must map to source ids"],
        "runtime_defaults": {"max_turns": 8, "timeout_seconds": 300},
    }


@pytest.mark.asyncio
async def test_upsert_agent_template_materializes_template_json() -> None:
    service, repository, session = _service()
    repository.agent_template_values = None

    async def upsert_agent_template(values: dict[str, Any]):
        repository.agent_template_values = values
        return SimpleNamespace(created_at=None, updated_at=None, **values)

    repository.upsert_agent_template = upsert_agent_template  # type: ignore[attr-defined]

    record = await service.upsert_agent_template(
        _agent_template_v1_data(),
        checksum="template-checksum",
        source_path="seed/agent_templates/research_scholar.yaml",
    )

    assert record.schema_version == "agent_template.v1"
    assert record.id == "research_scholar.v1"
    assert record.display_role == "文献专家"
    assert record.template_json["tool_affinity"]["preferred"] == [
        "web_search",
        "library_read",
        "citation_parser",
    ]
    assert record.checksum == "template-checksum"
    assert repository.agent_template_values is not None
    assert session.commit_count == 1
```

Add a seed-loader test:

```python
@pytest.mark.asyncio
async def test_seed_loader_applies_agent_template_revision_once(tmp_path) -> None:
    service, repository, session = _service()
    repository.agent_template_values = None

    async def delete_all_agent_templates() -> None:
        repository.agent_template_values = None

    async def upsert_agent_template(values: dict[str, Any]):
        repository.agent_template_values = values
        return SimpleNamespace(created_at=None, updated_at=None, **values)

    service.delete_all_agent_templates = delete_all_agent_templates  # type: ignore[method-assign]
    service.upsert_agent_template = upsert_agent_template  # type: ignore[method-assign]

    seed_dir = tmp_path / "agent_templates"
    seed_dir.mkdir(parents=True)
    seed_file = seed_dir / "research_scholar.yaml"
    seed_file.write_text("id: research_scholar.v1\n", encoding="utf-8")

    def validate(path, text):
        assert path == seed_file
        assert "research_scholar.v1" in text
        return _agent_template_v1_data()

    result = await DataServiceCatalogSeedLoader(service, seed_dir).load_agent_templates(
        validate_yaml_text=validate,
    )

    assert result.loaded == 1
    assert result.skipped is False
    assert result.checksum
    assert repository.agent_template_values is not None
    assert repository.latest.metadata_json["schema_version"] == "agent_template.v1"
    assert session.commit_count == 1
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/dataservice/test_catalog_domain.py::test_upsert_agent_template_materializes_template_json tests/dataservice/test_catalog_domain.py::test_seed_loader_applies_agent_template_revision_once -q
```

Expected: fail with missing `upsert_agent_template` and missing `load_agent_templates`.

- [ ] **Step 3: Add the database model and migration**

Create `backend/src/database/models/agent_template.py`:

```python
"""AgentTemplate ORM model — DataService-owned recruitable expert archetypes."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class AgentTemplate(Base, TimestampMixin):
    """Recruitable expert archetype used by the Lead Agent team kernel."""

    __tablename__ = "agent_templates"
    __table_args__ = (
        Index(
            "ix_agent_templates_enabled_category",
            "enabled",
            "category",
            postgresql_where="enabled = true",
        ),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    schema_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="agent_template.v1",
        server_default="agent_template.v1",
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    display_role: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    persona_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    default_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    tool_affinity: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    risk_profile: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    output_contracts: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    quality_expectations: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    runtime_defaults: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    template_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Create `backend/alembic/versions/076_agent_templates.py`:

```python
"""agent_templates

Revision ID: 076_agent_templates
Revises: 075_enforce_workspace_owner_membership
Create Date: 2026-05-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "076_agent_templates"
down_revision: Union[str, None] = "075_enforce_workspace_owner_membership"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_templates",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("schema_version", sa.String(length=50), server_default="agent_template.v1", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("display_role", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("persona_prompt", sa.Text(), server_default="", nullable=False),
        sa.Column("default_skills", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("tool_affinity", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("risk_profile", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("output_contracts", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("quality_expectations", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("runtime_defaults", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("template_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_templates_enabled_category",
        "agent_templates",
        ["enabled", "category"],
        postgresql_where=sa.text("enabled = true"),
    )


def downgrade() -> None:
    op.drop_index("ix_agent_templates_enabled_category", table_name="agent_templates")
    op.drop_table("agent_templates")
```

Modify `backend/src/database/models/__init__.py` to import and export `AgentTemplate`.

- [ ] **Step 4: Add DataService contracts, projection, repository, and service methods**

Add to `backend/src/dataservice/domains/catalog/contracts.py`:

```python
class AgentTemplateRecord(BaseModel):
    """Canonical recruitable agent template projection."""

    id: str
    schema_version: str = "agent_template.v1"
    enabled: bool = True
    display_role: str
    category: str
    description: str = ""
    persona_prompt: str = ""
    default_skills: list[str] = Field(default_factory=list)
    tool_affinity: dict[str, Any] = Field(default_factory=dict)
    risk_profile: dict[str, Any] = Field(default_factory=dict)
    output_contracts: list[str] = Field(default_factory=list)
    quality_expectations: list[str] = Field(default_factory=list)
    runtime_defaults: dict[str, Any] = Field(default_factory=dict)
    template_json: dict[str, Any] = Field(default_factory=dict)
    checksum: str | None = None
    source_path: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

Add `agent_template_to_record()` to `backend/src/dataservice/domains/catalog/projection.py`:

```python
def agent_template_to_record(template: AgentTemplate) -> AgentTemplateRecord:
    return AgentTemplateRecord(
        id=template.id,
        schema_version=str(template.schema_version or "agent_template.v1"),
        enabled=bool(template.enabled),
        display_role=template.display_role,
        category=template.category,
        description=template.description or "",
        persona_prompt=template.persona_prompt or "",
        default_skills=list(template.default_skills or []),
        tool_affinity=dict(template.tool_affinity or {}),
        risk_profile=dict(template.risk_profile or {}),
        output_contracts=list(template.output_contracts or []),
        quality_expectations=list(template.quality_expectations or []),
        runtime_defaults=dict(template.runtime_defaults or {}),
        template_json=dict(template.template_json or {}),
        checksum=template.checksum,
        source_path=template.source_path,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )
```

Add repository methods to `backend/src/dataservice/domains/catalog/repository.py`:

```python
async def has_agent_templates(self) -> bool:
    return (await self.session.execute(select(AgentTemplate).limit(1))).first() is not None


async def list_agent_templates(self, *, enabled_only: bool = False) -> list[AgentTemplate]:
    query = select(AgentTemplate)
    if enabled_only:
        query = query.where(AgentTemplate.enabled.is_(True))
    result = await self.session.execute(query.order_by(AgentTemplate.category, AgentTemplate.id))
    return list(result.scalars().all())


async def get_agent_template(self, template_id: str, *, enabled_only: bool = False) -> AgentTemplate | None:
    query = select(AgentTemplate).where(AgentTemplate.id == template_id)
    if enabled_only:
        query = query.where(AgentTemplate.enabled.is_(True))
    return (await self.session.execute(query)).scalar_one_or_none()


async def upsert_agent_template(self, values: dict[str, Any]) -> AgentTemplate:
    record = await self.get_agent_template(str(values["id"]))
    if record is None:
        record = AgentTemplate(**values)
        self.session.add(record)
        return record
    for key, value in values.items():
        setattr(record, key, value)
    return record


async def delete_all_agent_templates(self) -> None:
    await self.session.execute(delete(AgentTemplate))


async def delete_agent_template(self, template_id: str) -> bool:
    result = await self.session.execute(delete(AgentTemplate).where(AgentTemplate.id == template_id))
    return bool(result.rowcount)
```

Add service methods and validation to `backend/src/dataservice/domains/catalog/service.py`:

```python
async def has_agent_templates(self) -> bool:
    return await self.repository.has_agent_templates()


async def list_agent_templates(self, *, enabled_only: bool = False) -> list[AgentTemplateRecord]:
    return [
        agent_template_to_record(item)
        for item in await self.repository.list_agent_templates(enabled_only=enabled_only)
    ]


async def get_agent_template(self, template_id: str, *, enabled_only: bool = False) -> AgentTemplateRecord | None:
    item = await self.repository.get_agent_template(template_id, enabled_only=enabled_only)
    return agent_template_to_record(item) if item is not None else None


async def upsert_agent_template(
    self,
    data: dict[str, Any],
    *,
    checksum: str | None = None,
    source_path: str | None = None,
) -> AgentTemplateRecord:
    values = self.agent_template_values(data, checksum=checksum, source_path=source_path)
    record = await self.repository.upsert_agent_template(values)
    await self._finish()
    await self._refresh_if_supported(record)
    return agent_template_to_record(record)


async def delete_all_agent_templates(self) -> None:
    await self.repository.delete_all_agent_templates()
    await self._finish()


async def delete_agent_template(self, template_id: str) -> bool:
    deleted = await self.repository.delete_agent_template(template_id)
    await self._finish()
    return deleted


@staticmethod
def agent_template_values(
    data: dict[str, Any],
    *,
    checksum: str | None = None,
    source_path: str | None = None,
) -> dict[str, Any]:
    schema_version = str(data.get("schema_version") or "")
    if schema_version != "agent_template.v1":
        raise ValueError("Agent template records must use schema_version agent_template.v1")
    template_id = str(data.get("id") or "").strip()
    display_role = str(data.get("display_role") or "").strip()
    category = str(data.get("category") or "").strip()
    if not template_id:
        raise ValueError("Agent template records require id")
    if not display_role:
        raise ValueError("Agent template records require display_role")
    if not category:
        raise ValueError("Agent template records require category")
    tool_affinity = data.get("tool_affinity")
    risk_profile = data.get("risk_profile")
    if not isinstance(tool_affinity, dict):
        raise ValueError("Agent template records require tool_affinity object")
    if not isinstance(risk_profile, dict):
        raise ValueError("Agent template records require risk_profile object")
    return {
        "id": template_id,
        "schema_version": schema_version,
        "enabled": bool(data.get("enabled", True)),
        "display_role": display_role,
        "category": category,
        "description": str(data.get("description") or ""),
        "persona_prompt": str(data.get("persona_prompt") or ""),
        "default_skills": list(data.get("default_skills") or []),
        "tool_affinity": tool_affinity,
        "risk_profile": risk_profile,
        "output_contracts": list(data.get("output_contracts") or []),
        "quality_expectations": list(data.get("quality_expectations") or []),
        "runtime_defaults": dict(data.get("runtime_defaults") or {}),
        "template_json": dict(data),
        "checksum": checksum,
        "source_path": source_path,
    }
```

- [ ] **Step 5: Add seed loading and internal/client APIs**

Add `load_agent_templates()` and `load_agent_template_items()` to `DataServiceCatalogSeedLoader` using `catalog_kind="agent_templates"`, `schema_version="agent_template.v1"`, and glob pattern `"*.yaml"`.

Add routes to `backend/src/dataservice_app/routers/catalog.py`:

```python
@router.get("/agent-templates")
async def list_agent_templates(
    enabled_only: bool = Query(default=False),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    records = await service.list_agent_templates(enabled_only=enabled_only)
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.get("/agent-templates/exists")
async def has_agent_templates(
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    return envelope_ok({"exists": await service.has_agent_templates()})


@router.get("/agent-templates/{template_id}")
async def get_agent_template(
    template_id: str,
    enabled_only: bool = Query(default=False),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    record = await service.get_agent_template(template_id, enabled_only=enabled_only)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.put("/agent-templates/{template_id}")
async def upsert_agent_template(
    template_id: str,
    payload: CatalogUpsertPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceCatalogService(uow.required_session, autocommit=False)
    data = dict(payload.data)
    data["id"] = template_id
    record = await service.upsert_agent_template(
        data,
        checksum=payload.checksum,
        source_path=payload.source_path,
    )
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))
```

Add matching payload classes to `backend/src/dataservice_client/contracts/catalog.py` and client methods:

```python
class AgentTemplatePayload(BaseModel):
    id: str
    schema_version: str = "agent_template.v1"
    enabled: bool = True
    display_role: str
    category: str
    description: str = ""
    persona_prompt: str = ""
    default_skills: list[str] = Field(default_factory=list)
    tool_affinity: dict[str, Any] = Field(default_factory=dict)
    risk_profile: dict[str, Any] = Field(default_factory=dict)
    output_contracts: list[str] = Field(default_factory=list)
    quality_expectations: list[str] = Field(default_factory=list)
    runtime_defaults: dict[str, Any] = Field(default_factory=dict)
    template_json: dict[str, Any] = Field(default_factory=dict)
    checksum: str | None = None
    source_path: str | None = None
```

```python
async def list_agent_templates(self, *, enabled_only: bool = False) -> list[AgentTemplatePayload]:
    payload = await self._request(
        "GET",
        "/internal/v1/catalog/agent-templates",
        params={"enabled_only": enabled_only},
    )
    return [AgentTemplatePayload.model_validate(item) for item in payload["data"]]


async def get_agent_template(
    self,
    template_id: str,
    *,
    enabled_only: bool = False,
) -> AgentTemplatePayload | None:
    payload = await self._request(
        "GET",
        f"/internal/v1/catalog/agent-templates/{template_id}",
        params={"enabled_only": enabled_only},
    )
    data = payload.get("data")
    return AgentTemplatePayload.model_validate(data) if data is not None else None
```

- [ ] **Step 6: Add initial template seed YAML files**

Create four initial templates. Use this shape for `backend/seed/agent_templates/research_scholar.yaml`; the other three use the same schema with their role-specific fields:

```yaml
schema_version: agent_template.v1
id: research_scholar.v1
enabled: true
display_role: 文献专家
category: research
description: 检索、筛选、归纳文献，并检查引用与证据链质量。
persona_prompt: |
  You are a rigorous academic literature and evidence specialist for Wenjin.
default_skills:
  - research-scout
  - citation-auditor
tool_affinity:
  preferred:
    - web_search
    - library_read
    - citation_parser
  can_request:
    - document_read
    - artifact_create
risk_profile:
  network: normal
  filesystem: no_direct_write
  code_execution: not_needed
  room_write: staged_only
output_contracts:
  - literature_evidence_report.v1
  - citation_quality_report.v1
quality_expectations:
  - important claims must map to source ids
  - missing evidence must be marked explicitly
runtime_defaults:
  max_turns: 8
  timeout_seconds: 300
```

Use these ids and display roles for the other seeds:

```yaml
id: writing_editor.v1
display_role: 写作编辑
category: writing
default_skills: [manuscript-writer]
```

```yaml
id: critical_reviewer.v1
display_role: 质量审稿人
category: review
default_skills: [review-critic, citation-auditor]
```

```yaml
id: generalist_assistant.v1
display_role: 综合助理
category: generalist
default_skills: [review-critic]
```

- [ ] **Step 7: Wire bootstrap seeding**

Modify `backend/src/database/bootstrap_admin.py` after skill seed and before capability seed:

```python
try:
    from pathlib import Path
    import yaml
    from src.dataservice.domains.catalog.seed_loader import DataServiceCatalogSeedLoader
    from src.dataservice.domains.catalog.service import DataServiceCatalogService

    seed_dir = Path(__file__).resolve().parents[3] / "seed" / "agent_templates"
    if seed_dir.exists():
        service = DataServiceCatalogService(session)

        def validate_agent_template(path: Path, text: str) -> dict[str, Any]:
            data = yaml.safe_load(text) or {}
            if not isinstance(data, dict):
                raise ValueError(f"{path} must contain an object")
            return data

        result = await DataServiceCatalogSeedLoader(service, seed_dir).load_agent_templates(
            validate_yaml_text=validate_agent_template,
        )
        if result.loaded:
            print(f"[bootstrap-admin] Seeded {result.loaded} agent template record(s)")
except Exception as template_exc:
    print(f"[bootstrap-admin] WARN: agent template seed failed: {template_exc}")
```

If `Any` is not already imported, add `from typing import Any`.

- [ ] **Step 8: Run Task 1 tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/dataservice/test_catalog_domain.py tests/dataservice/test_foundation.py -q
```

Expected: pass.

- [ ] **Step 9: Commit Task 1**

```bash
git add backend/src/database/models/agent_template.py backend/src/database/models/__init__.py backend/alembic/versions/076_agent_templates.py backend/src/dataservice backend/src/dataservice_app/routers/catalog.py backend/src/dataservice_client backend/src/database/bootstrap_admin.py backend/seed/agent_templates backend/tests/dataservice/test_catalog_domain.py backend/tests/dataservice/test_foundation.py
git commit -m "feat: add agent template catalog"
```

---

## Task 2: Team Contracts And Policy Resolution

**Files:**
- Create: `backend/src/agents/lead_agent/v2/team/__init__.py`
- Create: `backend/src/agents/lead_agent/v2/team/contracts.py`
- Create: `backend/src/agents/lead_agent/v2/team/policy.py`
- Modify: `backend/src/subagents/v2/base.py`
- Test: `backend/tests/agents/lead_agent/v2/test_team_policy.py`

- [ ] **Step 1: Write failing policy tests**

Create `backend/tests/agents/lead_agent/v2/test_team_policy.py`:

```python
from types import SimpleNamespace

import pytest

from src.agents.lead_agent.v2.team.contracts import (
    AgentTemplate,
    CapabilityTeamPolicy,
)
from src.agents.lead_agent.v2.team.policy import (
    TeamPolicyError,
    build_capability_team_policy,
    build_invocation_assignment,
    resolve_effective_skills,
    resolve_effective_tools,
)


def _template(template_id: str = "research_scholar.v1") -> AgentTemplate:
    return AgentTemplate(
        id=template_id,
        display_role="文献专家",
        category="research",
        description="Research role",
        persona_prompt="research",
        default_skills=["research-scout", "citation-auditor"],
        tool_affinity={
            "preferred": ["web_search", "library_read"],
            "can_request": ["citation_parser", "artifact_create"],
        },
        risk_profile={"room_write": "staged_only"},
        output_contracts=["literature_evidence_report.v1"],
        quality_expectations=["claims map to sources"],
        runtime_defaults={"max_turns": 8},
    )


def test_build_capability_team_policy_rejects_unknown_template() -> None:
    cap = SimpleNamespace(
        definition_json={
            "team_policy": {
                "core_templates": ["missing.v1"],
                "optional_templates": [],
                "limits": {"max_iterations": 3},
            }
        },
        runtime={"mode": "team_kernel"},
    )

    with pytest.raises(TeamPolicyError, match="unknown agent template"):
        build_capability_team_policy(cap, templates={"research_scholar.v1": _template()})


def test_build_capability_team_policy_applies_platform_caps() -> None:
    cap = SimpleNamespace(
        definition_json={
            "team_policy": {
                "core_templates": ["research_scholar.v1"],
                "optional_templates": [],
                "limits": {
                    "max_iterations": 99,
                    "max_parallel_invocations": 99,
                    "max_invocations_total": 99,
                    "max_invocations_per_template": 99,
                    "no_progress_rounds_before_stop": 9,
                },
                "budget": {"max_tokens_soft": 1000, "max_tokens_hard": 2000},
            }
        },
        runtime={"mode": "team_kernel"},
    )

    policy = build_capability_team_policy(cap, templates={"research_scholar.v1": _template()})

    assert policy.limits.max_iterations == 8
    assert policy.limits.max_parallel_invocations == 5
    assert policy.limits.max_invocations_total == 24
    assert policy.limits.max_invocations_per_template == 6


def test_effective_tools_keep_high_ceiling_but_block_direct_commit() -> None:
    policy = CapabilityTeamPolicy(
        core_templates=["research_scholar.v1"],
        optional_templates=[],
        capability_tools=["web_search", "library_read", "citation_parser", "room_commit"],
        workspace_tools=["web_search", "library_read", "citation_parser", "artifact_create"],
        user_tools=["web_search", "library_read", "citation_parser", "artifact_create", "room_commit"],
    )
    effective = resolve_effective_tools(_template(), policy)

    assert effective == ["web_search", "library_read", "citation_parser"]
    assert "room_commit" not in effective


def test_invocation_assignment_names_duplicate_templates() -> None:
    assignment_a = build_invocation_assignment(
        template=_template("code_engineer.v1"),
        iteration=1,
        template_invocation_count=1,
        reason="code required",
        input_brief={"task": "patch"},
        effective_tools=["sandbox_exec"],
        effective_skills=["code-patch-planning"],
    )
    assignment_b = build_invocation_assignment(
        template=_template("code_engineer.v1"),
        iteration=1,
        template_invocation_count=2,
        reason="parallel code review",
        input_brief={"task": "review"},
        effective_tools=["sandbox_exec"],
        effective_skills=["code-patch-planning"],
    )

    assert assignment_a.display_name.endswith("A")
    assert assignment_b.display_name.endswith("B")
    assert assignment_b.template_id == "code_engineer.v1"


def test_effective_skills_include_template_defaults_and_task_requested() -> None:
    effective = resolve_effective_skills(
        _template(),
        requested_skills=["evidence_traceability.v1"],
        capability_skills=["research-scout", "citation-auditor", "evidence_traceability.v1"],
    )

    assert effective == ["research-scout", "citation-auditor", "evidence_traceability.v1"]
```

- [ ] **Step 2: Run failing policy tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_policy.py -q
```

Expected: fail because `src.agents.lead_agent.v2.team` does not exist.

- [ ] **Step 3: Add team contracts**

Create `backend/src/agents/lead_agent/v2/team/contracts.py`:

```python
"""Contracts for Lead Agent team-kernel runtime."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AgentTemplate(BaseModel):
    id: str
    schema_version: str = "agent_template.v1"
    enabled: bool = True
    display_role: str
    category: str
    description: str = ""
    persona_prompt: str = ""
    default_skills: list[str] = Field(default_factory=list)
    tool_affinity: dict[str, Any] = Field(default_factory=dict)
    risk_profile: dict[str, Any] = Field(default_factory=dict)
    output_contracts: list[str] = Field(default_factory=list)
    quality_expectations: list[str] = Field(default_factory=list)
    runtime_defaults: dict[str, Any] = Field(default_factory=dict)


class TeamLimits(BaseModel):
    max_iterations: int = Field(default=5, ge=1, le=8)
    max_parallel_invocations: int = Field(default=3, ge=1, le=5)
    max_invocations_total: int = Field(default=12, ge=1, le=24)
    max_invocations_per_template: int = Field(default=3, ge=1, le=6)
    no_progress_rounds_before_stop: int = Field(default=2, ge=1, le=4)


class TeamBudget(BaseModel):
    max_tokens_soft: int | None = Field(default=None, ge=1)
    max_tokens_hard: int | None = Field(default=None, ge=1)
    max_sandbox_seconds: int | None = Field(default=None, ge=1)


class CapabilityTeamPolicy(BaseModel):
    core_templates: list[str] = Field(default_factory=list)
    optional_templates: list[str] = Field(default_factory=list)
    recruitment_triggers: dict[str, Any] = Field(default_factory=dict)
    quality_pipeline: list[str] = Field(default_factory=list)
    limits: TeamLimits = Field(default_factory=TeamLimits)
    budget: TeamBudget = Field(default_factory=TeamBudget)
    capability_tools: list[str] = Field(default_factory=list)
    workspace_tools: list[str] = Field(default_factory=list)
    user_tools: list[str] = Field(default_factory=list)
    capability_skills: list[str] = Field(default_factory=list)

    @field_validator("core_templates", "optional_templates")
    @classmethod
    def _dedupe_template_list(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in value:
            key = str(item).strip()
            if key and key not in seen:
                seen.add(key)
                result.append(key)
        return result


class AgentInvocation(BaseModel):
    id: str
    execution_id: str | None = None
    iteration: int
    template_id: str
    display_name: str
    assigned_role: str
    recruitment_reason: str
    input_brief: dict[str, Any] = Field(default_factory=dict)
    effective_tools: list[str] = Field(default_factory=list)
    effective_skills: list[str] = Field(default_factory=list)
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"] = "queued"
    output_report: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    token_usage: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class TeamBlackboard(BaseModel):
    mission_summary: str = ""
    confirmed_findings: list[dict[str, Any]] = Field(default_factory=list)
    evidence_items: list[dict[str, Any]] = Field(default_factory=list)
    citation_gaps: list[dict[str, Any]] = Field(default_factory=list)
    experiment_gaps: list[dict[str, Any]] = Field(default_factory=list)
    data_gaps: list[dict[str, Any]] = Field(default_factory=list)
    figure_table_requirements: list[dict[str, Any]] = Field(default_factory=list)
    writing_risks: list[dict[str, Any]] = Field(default_factory=list)
    format_risks: list[dict[str, Any]] = Field(default_factory=list)
    pending_decisions: list[dict[str, Any]] = Field(default_factory=list)
    rejected_claims: list[dict[str, Any]] = Field(default_factory=list)
    quality_gate_history: list[dict[str, Any]] = Field(default_factory=list)
    latest_leader_summary: str = ""


class QualityGateResult(BaseModel):
    gate_id: str
    status: Literal["pass", "warning", "fail"]
    severity: Literal["low", "medium", "high"] = "low"
    findings: list[dict[str, Any]] = Field(default_factory=list)
    required_fixes: list[dict[str, Any]] = Field(default_factory=list)
    suggested_recruits: list[dict[str, Any]] = Field(default_factory=list)
    next_action: Literal[
        "finish",
        "revise_existing",
        "recruit_more",
        "ask_user",
        "stop_with_warning",
    ] = "finish"
```

Create `backend/src/agents/lead_agent/v2/team/__init__.py`:

```python
"""Team-kernel runtime package for Lead Agent v2."""
```

- [ ] **Step 4: Add policy resolver**

Create `backend/src/agents/lead_agent/v2/team/policy.py`:

```python
"""Team policy validation and runtime assignment helpers."""

from __future__ import annotations

from typing import Any

from .contracts import AgentInvocation, AgentTemplate, CapabilityTeamPolicy

DIRECT_COMMIT_TOOLS = {"room_commit", "workspace_room_write", "prism_apply"}
PLATFORM_MAX = {
    "max_iterations": 8,
    "max_parallel_invocations": 5,
    "max_invocations_total": 24,
    "max_invocations_per_template": 6,
}


class TeamPolicyError(ValueError):
    """Raised when a capability team policy is invalid."""


def build_capability_team_policy(
    capability: Any,
    *,
    templates: dict[str, AgentTemplate],
    workspace_tools: list[str] | None = None,
    user_tools: list[str] | None = None,
) -> CapabilityTeamPolicy:
    definition = getattr(capability, "definition_json", None)
    if not isinstance(definition, dict):
        definition = {}
    raw_policy = definition.get("team_policy")
    if not isinstance(raw_policy, dict):
        raise TeamPolicyError("team_kernel capability requires definition_json.team_policy")
    raw_limits = dict(raw_policy.get("limits") or {})
    for key, platform_max in PLATFORM_MAX.items():
        if key in raw_limits:
            raw_limits[key] = min(int(raw_limits[key]), platform_max)
    raw_budget = dict(raw_policy.get("budget") or {})
    runtime = getattr(capability, "runtime", None)
    if not isinstance(runtime, dict):
        runtime = {}
    capability_tools = list(raw_policy.get("capability_tools") or runtime.get("allowed_tools") or [])
    capability_skills = list(raw_policy.get("capability_skills") or [])
    policy = CapabilityTeamPolicy(
        core_templates=list(raw_policy.get("core_templates") or []),
        optional_templates=list(raw_policy.get("optional_templates") or []),
        recruitment_triggers=dict(raw_policy.get("recruitment_triggers") or {}),
        quality_pipeline=list(raw_policy.get("quality_pipeline") or definition.get("quality_pipeline") or definition.get("quality_gates") or []),
        limits=raw_limits,
        budget=raw_budget,
        capability_tools=capability_tools,
        workspace_tools=list(workspace_tools or capability_tools),
        user_tools=list(user_tools or capability_tools),
        capability_skills=capability_skills,
    )
    known_ids = set(templates)
    for template_id in [*policy.core_templates, *policy.optional_templates]:
        if template_id not in known_ids:
            raise TeamPolicyError(f"unknown agent template: {template_id}")
    if not policy.core_templates and not policy.optional_templates:
        raise TeamPolicyError("team_policy must declare at least one template")
    return policy


def resolve_effective_tools(template: AgentTemplate, policy: CapabilityTeamPolicy) -> list[str]:
    affinity = template.tool_affinity or {}
    requested = [
        *list(affinity.get("preferred") or []),
        *list(affinity.get("can_request") or []),
    ]
    allowed = set(policy.capability_tools or requested)
    if policy.workspace_tools:
        allowed &= set(policy.workspace_tools)
    if policy.user_tools:
        allowed &= set(policy.user_tools)
    result: list[str] = []
    for tool in requested:
        if tool in DIRECT_COMMIT_TOOLS:
            continue
        if tool in allowed and tool not in result:
            result.append(tool)
    return result


def resolve_effective_skills(
    template: AgentTemplate,
    *,
    requested_skills: list[str] | None = None,
    capability_skills: list[str] | None = None,
) -> list[str]:
    requested = [*template.default_skills, *list(requested_skills or [])]
    allowed = set(capability_skills or requested)
    result: list[str] = []
    for skill_id in requested:
        if skill_id in allowed and skill_id not in result:
            result.append(skill_id)
    return result


def build_invocation_assignment(
    *,
    template: AgentTemplate,
    iteration: int,
    template_invocation_count: int,
    reason: str,
    input_brief: dict[str, Any],
    effective_tools: list[str],
    effective_skills: list[str],
) -> AgentInvocation:
    suffix = ""
    if template_invocation_count > 1 or template.id.endswith("code_engineer.v1"):
        suffix = f" {chr(64 + min(template_invocation_count, 26))}"
    display_name = f"{template.display_role}{suffix}"
    invocation_id = f"team.{iteration}.{template.id.replace('.', '_')}.{template_invocation_count}"
    return AgentInvocation(
        id=invocation_id,
        iteration=iteration,
        template_id=template.id,
        display_name=display_name,
        assigned_role=template.display_role,
        recruitment_reason=reason,
        input_brief=input_brief,
        effective_tools=effective_tools,
        effective_skills=effective_skills,
    )
```

- [ ] **Step 5: Extend SubagentContext with team metadata**

Modify `backend/src/subagents/v2/base.py`:

```python
    capability_policy: dict = field(default_factory=dict)
    skill: Any | None = None
    team_context: dict[str, Any] = field(default_factory=dict)
    invocation: dict[str, Any] | None = None
    emit_delta: Callable[[str, str], Awaitable[None]] | None = None
```

- [ ] **Step 6: Run Task 2 tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_policy.py -q
```

Expected: pass.

- [ ] **Step 7: Commit Task 2**

```bash
git add backend/src/agents/lead_agent/v2/team backend/src/subagents/v2/base.py backend/tests/agents/lead_agent/v2/test_team_policy.py
git commit -m "feat: add team policy contracts"
```

---

## Task 3: Team Kernel Runtime

**Files:**
- Create: `backend/src/agents/lead_agent/v2/team/kernel.py`
- Modify: `backend/src/agents/lead_agent/v2/runtime.py`
- Test: `backend/tests/agents/lead_agent/v2/test_team_kernel.py`

- [ ] **Step 1: Write failing team kernel tests**

Create `backend/tests/agents/lead_agent/v2/test_team_kernel.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.subagents.v2.types  # noqa: F401
from src.agents.contracts.task_brief import TaskBrief
from src.agents.lead_agent.v2.runtime import LeadAgentRuntime


def _team_capability() -> SimpleNamespace:
    return SimpleNamespace(
        id="team_research",
        workspace_type="thesis",
        display_name="团队调研",
        runtime={"mode": "team_kernel", "allowed_tools": ["web_search", "library_read", "citation_parser"]},
        graph_template={},
        definition_json={
            "mission": {"primary_surface": "rooms"},
            "team_policy": {
                "core_templates": ["research_scholar.v1", "critical_reviewer.v1"],
                "optional_templates": ["generalist_assistant.v1"],
                "capability_tools": ["web_search", "library_read", "citation_parser"],
                "capability_skills": ["research-scout", "citation-auditor", "review-critic"],
                "quality_pipeline": ["evidence_traceability", "critical_review"],
                "limits": {"max_iterations": 2, "max_parallel_invocations": 2, "max_invocations_total": 4},
            },
        },
    )


def _brief() -> TaskBrief:
    return TaskBrief(
        capability_id="team_research",
        raw_message="调研 transformer 在医学影像中的应用",
        workspace_id="ws-team",
        user_id="user-1",
        brief={"topic": "transformer medical imaging"},
    )


@pytest.mark.asyncio
async def test_team_kernel_runtime_publishes_team_events_and_report(monkeypatch) -> None:
    published: list[tuple[str, str, dict]] = []
    node_events: list[dict] = []

    async def publish(execution_id, event_name, payload):
        published.append((execution_id, event_name, payload))

    async def record_node_event(**kwargs):
        node_events.append(kwargs)

    async def fake_templates(*, enabled_only: bool = True):
        from src.dataservice_client.contracts.catalog import AgentTemplatePayload

        return [
            AgentTemplatePayload(
                id="research_scholar.v1",
                display_role="文献专家",
                category="research",
                default_skills=["research-scout", "citation-auditor"],
                tool_affinity={"preferred": ["web_search", "library_read"], "can_request": ["citation_parser"]},
                risk_profile={"room_write": "staged_only"},
            ),
            AgentTemplatePayload(
                id="critical_reviewer.v1",
                display_role="质量审稿人",
                category="review",
                default_skills=["review-critic"],
                tool_affinity={"preferred": ["library_read"], "can_request": []},
                risk_profile={"room_write": "staged_only"},
            ),
            AgentTemplatePayload(
                id="generalist_assistant.v1",
                display_role="综合助理",
                category="generalist",
                default_skills=["review-critic"],
                tool_affinity={"preferred": [], "can_request": []},
                risk_profile={"room_write": "staged_only"},
            ),
        ]

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        list_agent_templates = fake_templates

        async def list_catalog_skills(self, *, enabled_only: bool = True):
            from src.dataservice_client.contracts.catalog import CapabilitySkillPayload

            return [
                CapabilitySkillPayload(
                    id="research-scout",
                    display_name="Research Scout",
                    worker_type="research",
                    subagent_type="react",
                    prompt="Summarize research evidence as JSON.",
                    config={"output_kind": "json"},
                ),
                CapabilitySkillPayload(
                    id="citation-auditor",
                    display_name="Citation Auditor",
                    worker_type="research",
                    subagent_type="react",
                    prompt="Audit citations.",
                    config={"output_kind": "json"},
                ),
                CapabilitySkillPayload(
                    id="review-critic",
                    display_name="Review Critic",
                    worker_type="review",
                    subagent_type="react",
                    prompt="Review risks.",
                    config={"output_kind": "json"},
                ),
            ]

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: FakeClient(),
    )

    cap = _team_capability()
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=publish,
        get_workspace_type=AsyncMock(return_value="thesis"),
        record_node_event=record_node_event,
    )

    report = await runtime.run_session(execution_id="exec-team", brief=_brief())

    event_names = [event_name for _, event_name, _ in published]
    assert event_names[0] == "execution.graph_structure"
    assert "execution.team.invocation" in event_names
    assert "execution.team.quality_gate" in event_names
    assert event_names[-1] == "execution.completed"
    assert report.status == "completed"
    assert "团队调研" in report.narrative
    assert any(event["node_type"] == "agent_invocation" for event in node_events)


@pytest.mark.asyncio
async def test_team_kernel_runtime_stops_when_template_policy_invalid(monkeypatch) -> None:
    cap = _team_capability()
    cap.definition_json["team_policy"]["core_templates"] = ["missing_template.v1"]
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def list_agent_templates(self, *, enabled_only: bool = True):
            return []

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: FakeClient(),
    )

    runtime = LeadAgentRuntime(
        resolver=resolver,
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    report = await runtime.run_session(execution_id="exec-team-invalid", brief=_brief())

    assert report.status == "failed_partial"
    assert report.errors
    assert "unknown agent template" in report.errors[0].error
```

- [ ] **Step 2: Run failing team kernel tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_kernel.py -q
```

Expected: fail because `team.kernel` is missing and runtime does not route to team mode.

- [ ] **Step 3: Implement TeamKernelRuntime**

Create `backend/src/agents/lead_agent/v2/team/kernel.py`:

```python
"""Team-kernel runtime for capability-driven dynamic Lead Agent teams."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from src.agents.contracts.task_brief import TaskBrief
from src.agents.contracts.task_report import DocumentData, DocumentOutput, ResultError, TaskReport
from src.dataservice_client.provider import dataservice_client
from src.subagents.v2 import types as _types  # noqa: F401
from src.subagents.v2.base import SubagentContext, SubagentResult
from src.subagents.v2.registry import REGISTRY

from .contracts import AgentInvocation, AgentTemplate, QualityGateResult, TeamBlackboard
from .policy import (
    TeamPolicyError,
    build_capability_team_policy,
    build_invocation_assignment,
    resolve_effective_skills,
    resolve_effective_tools,
)

logger = logging.getLogger(__name__)


class TeamKernelRuntime:
    """Fixed control loop for dynamic Lead Agent team execution."""

    def __init__(
        self,
        *,
        publish_event,
        record_node_event,
        abort_check,
        load_workspace_data,
        needs_library_context,
        capability_policy_builder,
        collect_policy_memory_outputs,
    ) -> None:
        self.publish_event = publish_event
        self.record_node_event = record_node_event
        self.abort_check = abort_check
        self.load_workspace_data = load_workspace_data
        self.needs_library_context = needs_library_context
        self.capability_policy_builder = capability_policy_builder
        self.collect_policy_memory_outputs = collect_policy_memory_outputs

    async def run(self, *, execution_id: str, brief: TaskBrief, capability: Any, started_at: datetime) -> TaskReport:
        try:
            templates = await self._load_templates()
            team_policy = build_capability_team_policy(
                capability,
                templates=templates,
            )
            capability_policy = self.capability_policy_builder(capability)
            workspace_data = (
                await self.load_workspace_data(brief.workspace_id)
                if self.needs_library_context(capability_policy)
                else {}
            )
            blackboard = TeamBlackboard(mission_summary=brief.raw_message or capability.display_name)
            invocations = await self._run_iteration(
                execution_id=execution_id,
                brief=brief,
                capability=capability,
                templates=templates,
                team_policy=team_policy,
                capability_policy=capability_policy,
                workspace_data=workspace_data,
                blackboard=blackboard,
            )
            gates = self._run_quality_gates(team_policy.quality_pipeline, invocations, blackboard)
            for gate in gates:
                await self.publish_event(
                    execution_id,
                    "execution.team.quality_gate",
                    {"quality_gate": gate.model_dump(mode="json")},
                )
            duration = int((datetime.now(UTC) - started_at).total_seconds())
            outputs = self._outputs_from_invocations(invocations)
            outputs.extend(self.collect_policy_memory_outputs(capability, brief, outputs))
            narrative = self._build_narrative(capability, invocations, gates)
            return TaskReport(
                execution_id=execution_id,
                capability_id=brief.capability_id,
                status="completed",
                duration_seconds=duration,
                token_usage=self._aggregate_token_usage(invocations),
                narrative=narrative,
                outputs=outputs,
                errors=[],
            )
        except TeamPolicyError as exc:
            return self._failed_report(execution_id, brief, started_at, str(exc))
        except Exception as exc:
            logger.exception("team kernel failed", extra={"execution_id": execution_id})
            return self._failed_report(execution_id, brief, started_at, str(exc))

    async def _load_templates(self) -> dict[str, AgentTemplate]:
        async with dataservice_client() as client:
            records = await client.list_agent_templates(enabled_only=True)
        return {
            record.id: AgentTemplate.model_validate(record.model_dump(mode="json"))
            for record in records
        }

    async def _load_skills(self, skill_ids: list[str]) -> dict[str, Any]:
        if not skill_ids:
            return {}
        async with dataservice_client() as client:
            records = await client.list_catalog_skills(enabled_only=True)
        wanted = set(skill_ids)
        return {record.id: record for record in records if record.id in wanted}

    async def _run_iteration(
        self,
        *,
        execution_id: str,
        brief: TaskBrief,
        capability: Any,
        templates: dict[str, AgentTemplate],
        team_policy,
        capability_policy: dict[str, Any],
        workspace_data: dict[str, Any],
        blackboard: TeamBlackboard,
    ) -> list[AgentInvocation]:
        selected_template_ids = team_policy.core_templates[: team_policy.limits.max_parallel_invocations]
        counts: Counter[str] = Counter()
        invocations: list[AgentInvocation] = []
        for template_id in selected_template_ids:
            template = templates[template_id]
            counts[template_id] += 1
            effective_tools = resolve_effective_tools(template, team_policy)
            effective_skills = resolve_effective_skills(
                template,
                capability_skills=team_policy.capability_skills or template.default_skills,
            )
            invocation = build_invocation_assignment(
                template=template,
                iteration=1,
                template_invocation_count=counts[template_id],
                reason="core team member for capability",
                input_brief=self._build_member_brief(brief, capability, template, blackboard),
                effective_tools=effective_tools,
                effective_skills=effective_skills,
            )
            invocation.execution_id = execution_id
            invocations.append(invocation)
        await asyncio.gather(
            *[
                self._run_invocation(
                    invocation=invocation,
                    template=templates[invocation.template_id],
                    capability_policy=capability_policy,
                    workspace_data=workspace_data,
                    blackboard=blackboard,
                )
                for invocation in invocations
            ]
        )
        return invocations

    def _build_member_brief(
        self,
        brief: TaskBrief,
        capability: Any,
        template: AgentTemplate,
        blackboard: TeamBlackboard,
    ) -> dict[str, Any]:
        payload = dict(brief.brief or {})
        payload.setdefault("raw_message", brief.raw_message)
        payload.setdefault("workspace_id", brief.workspace_id)
        payload.setdefault("capability_id", brief.capability_id)
        payload["team_role"] = template.display_role
        payload["team_blackboard"] = blackboard.model_dump(mode="json")
        payload["capability_name"] = getattr(capability, "display_name", brief.capability_id)
        return payload

    async def _run_invocation(
        self,
        *,
        invocation: AgentInvocation,
        template: AgentTemplate,
        capability_policy: dict[str, Any],
        workspace_data: dict[str, Any],
        blackboard: TeamBlackboard,
    ) -> None:
        started_at = datetime.now(UTC)
        invocation.status = "running"
        await self._record_invocation(invocation, status="running", started_at=started_at)
        await self.publish_event(
            invocation.execution_id or "",
            "execution.team.invocation",
            {"invocation": invocation.model_dump(mode="json")},
        )
        try:
            if await self.abort_check(invocation.execution_id or ""):
                invocation.status = "cancelled"
                return
            skill_records = await self._load_skills(invocation.effective_skills)
            skill = skill_records.get(invocation.effective_skills[0]) if invocation.effective_skills else None
            subagent_type = getattr(skill, "subagent_type", None) or "react"
            subagent_cls = REGISTRY.get(subagent_type)
            ctx = SubagentContext(
                workspace_id=str(invocation.input_brief.get("workspace_id") or ""),
                execution_id=invocation.execution_id or "",
                prompt=template.persona_prompt,
                inputs=invocation.input_brief,
                tools=invocation.effective_tools,
                workspace_data=workspace_data,
                capability_policy=capability_policy,
                skill=skill,
                team_context=blackboard.model_dump(mode="json"),
                invocation=invocation.model_dump(mode="json"),
            )
            result: SubagentResult = await subagent_cls().run(ctx)
            invocation.status = "succeeded"
            invocation.output_report = result.output
            invocation.tool_calls = result.tool_calls or []
            invocation.token_usage = result.token_usage
            blackboard.latest_leader_summary = self._preview_output(result.output)
        except Exception as exc:
            invocation.status = "failed"
            invocation.error = {"message": str(exc)}
        completed_at = datetime.now(UTC)
        await self._record_invocation(invocation, status=invocation.status, completed_at=completed_at)
        await self.publish_event(
            invocation.execution_id or "",
            "execution.team.invocation",
            {"invocation": invocation.model_dump(mode="json")},
        )

    async def _record_invocation(
        self,
        invocation: AgentInvocation,
        *,
        status: str,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        await self.record_node_event(
            execution_id=invocation.execution_id or "",
            node_id=invocation.id,
            node_type="agent_invocation",
            label=invocation.display_name,
            status="completed" if status == "succeeded" else status,
            input_data=invocation.input_brief,
            output_data=invocation.output_report,
            tool_calls=invocation.tool_calls,
            token_usage=invocation.token_usage,
            error=invocation.error["message"] if invocation.error else None,
            node_metadata={
                "team": True,
                "template_id": invocation.template_id,
                "display_name": invocation.display_name,
                "assigned_role": invocation.assigned_role,
                "recruitment_reason": invocation.recruitment_reason,
                "effective_tools": invocation.effective_tools,
                "effective_skills": invocation.effective_skills,
            },
            started_at=started_at,
            completed_at=completed_at,
        )

    def _run_quality_gates(
        self,
        quality_pipeline: list[str],
        invocations: list[AgentInvocation],
        blackboard: TeamBlackboard,
    ) -> list[QualityGateResult]:
        failed = [item for item in invocations if item.status == "failed"]
        status = "warning" if failed else "pass"
        gates = quality_pipeline or ["team_output_available"]
        return [
            QualityGateResult(
                gate_id=gate,
                status=status,
                severity="medium" if failed else "low",
                findings=[
                    {"message": f"{len(failed)} team member invocation(s) failed"}
                ] if failed else [],
                next_action="stop_with_warning" if failed else "finish",
            )
            for gate in gates
        ]

    def _outputs_from_invocations(self, invocations: list[AgentInvocation]) -> list[DocumentOutput]:
        outputs: list[DocumentOutput] = []
        for invocation in invocations:
            if invocation.status != "succeeded":
                continue
            content = self._preview_output(invocation.output_report)
            outputs.append(
                DocumentOutput(
                    id=f"team-output-{invocation.id}",
                    kind="document",
                    preview=f"{invocation.display_name}: {content[:80]}",
                    default_checked=True,
                    data=DocumentData(
                        name=f"{invocation.display_name}产出.md",
                        doc_kind="team_member_report",
                        content=content,
                    ),
                )
            )
        return outputs

    def _build_narrative(
        self,
        capability: Any,
        invocations: list[AgentInvocation],
        gates: list[QualityGateResult],
    ) -> str:
        names = "、".join(item.display_name for item in invocations)
        warnings = sum(1 for gate in gates if gate.status != "pass")
        suffix = f"，{warnings} 个质量门需要注意" if warnings else "，质量门已通过"
        return f"完成 {capability.display_name}，团队成员：{names}{suffix}。"

    def _aggregate_token_usage(self, invocations: list[AgentInvocation]) -> dict[str, int] | None:
        usage = {"input": 0, "output": 0}
        for invocation in invocations:
            token_usage = invocation.token_usage or {}
            usage["input"] += int(token_usage.get("input", token_usage.get("input_tokens", 0)) or 0)
            usage["output"] += int(token_usage.get("output", token_usage.get("output_tokens", 0)) or 0)
        return usage if usage["input"] or usage["output"] else None

    def _failed_report(
        self,
        execution_id: str,
        brief: TaskBrief,
        started_at: datetime,
        error: str,
    ) -> TaskReport:
        return TaskReport(
            execution_id=execution_id,
            capability_id=brief.capability_id,
            status="failed_partial",
            duration_seconds=int((datetime.now(UTC) - started_at).total_seconds()),
            narrative=f"团队执行未能完成：{error}",
            outputs=[],
            errors=[ResultError(phase="team_kernel", task="team_kernel", error=error)],
        )

    @staticmethod
    def _preview_output(output: Any) -> str:
        if isinstance(output, dict):
            for key in ("summary", "report_markdown", "markdown", "text"):
                value = output.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return str(output)
        return str(output or "")
```

- [ ] **Step 4: Route team mode in LeadAgentRuntime**

Modify `backend/src/agents/lead_agent/v2/runtime.py` after resolving `cap` and before static graph publication:

```python
        runtime_kind = self._runtime_mode(cap)
        if runtime_kind == "team_kernel":
            graph_structure = self._to_team_panel_graph(cap)
            await self.publish_event(
                execution_id,
                "execution.graph_structure",
                {"graph_structure": graph_structure},
            )
            if self.set_graph_structure is not None:
                try:
                    await self.set_graph_structure(graph_structure)
                except Exception:
                    logger.warning("Failed to persist team graph_structure", exc_info=True)
            from src.agents.lead_agent.v2.team.kernel import TeamKernelRuntime

            report = await TeamKernelRuntime(
                publish_event=self.publish_event,
                record_node_event=self.record_node_event,
                abort_check=self._check_abort,
                load_workspace_data=self._load_workspace_data,
                needs_library_context=self._needs_library_context,
                capability_policy_builder=self._capability_policy,
                collect_policy_memory_outputs=self._collect_policy_memory_outputs,
            ).run(
                execution_id=execution_id,
                brief=brief,
                capability=cap,
                started_at=started_at,
            )
            await self.publish_event(
                execution_id,
                "execution.completed",
                report.model_dump(mode="json"),
            )
            return report
```

Add helpers to `LeadAgentRuntime`:

```python
    @staticmethod
    def _runtime_mode(cap: Any) -> str:
        runtime = getattr(cap, "runtime", None)
        if isinstance(runtime, dict) and runtime.get("mode") == "team_kernel":
            return "team_kernel"
        return "static_graph"

    def _to_team_panel_graph(self, cap: Any) -> dict[str, Any]:
        definition = getattr(cap, "definition_json", None)
        if not isinstance(definition, dict):
            definition = {}
        policy = definition.get("team_policy") if isinstance(definition.get("team_policy"), dict) else {}
        nodes = [
            {"id": "team_prepare", "phase": "team_kernel", "task": "prepare_context", "subagent_type": "leader", "label": "准备上下文"},
            {"id": "team_recruit", "phase": "team_kernel", "task": "recruit_members", "subagent_type": "leader", "label": "组建团队"},
            {"id": "team_dispatch", "phase": "team_kernel", "task": "dispatch_invocations", "subagent_type": "team", "label": "成员执行"},
            {"id": "team_quality_gate", "phase": "team_kernel", "task": "quality_gate", "subagent_type": "quality_gate", "label": "质量闭环"},
            {"id": "team_finish", "phase": "team_kernel", "task": "finish", "subagent_type": "leader", "label": "整理结果"},
        ]
        core_templates = list(policy.get("core_templates") or [])
        for index, template_id in enumerate(core_templates):
            nodes.append(
                {
                    "id": f"team_template_{index + 1}",
                    "phase": "team_members",
                    "task": template_id,
                    "subagent_type": "agent_template",
                    "label": template_id,
                    "team": {"template_id": template_id, "core": True},
                }
            )
        edges = [
            {"from": "team_prepare", "to": "team_recruit"},
            {"from": "team_recruit", "to": "team_dispatch"},
            {"from": "team_dispatch", "to": "team_quality_gate"},
            {"from": "team_quality_gate", "to": "team_finish"},
        ]
        return {"mode": "team_kernel", "nodes": nodes, "edges": edges}
```

- [ ] **Step 5: Run Task 3 tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_kernel.py tests/agents/lead_agent/v2/test_runtime.py -q
```

Expected: pass.

- [ ] **Step 6: Commit Task 3**

```bash
git add backend/src/agents/lead_agent/v2/runtime.py backend/src/agents/lead_agent/v2/team/kernel.py backend/tests/agents/lead_agent/v2/test_team_kernel.py
git commit -m "feat: add lead agent team kernel runtime"
```

---

## Task 4: Execution Projection For Team Facts

**Files:**
- Modify: `backend/src/dataservice_client/contracts/execution.py`
- Modify: `backend/src/dataservice/domains/execution/contracts.py`
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/lib/execution-run-view.ts`
- Test: `frontend/lib/__tests__/execution-run-view.team.test.ts`

- [ ] **Step 1: Write failing frontend projection tests**

Create `frontend/lib/__tests__/execution-run-view.team.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { runViewFromExecution } from "@/lib/execution-run-view";
import type { ExecutionRecord } from "@/lib/api/types";

describe("team execution run view", () => {
  it("projects team members from agent invocation nodes", () => {
    const record = {
      id: "exec-team",
      workspace_id: "ws-1",
      feature_id: "team_research",
      display_name: "团队调研",
      status: "running",
      created_at: "2026-05-30T00:00:00Z",
      started_at: "2026-05-30T00:00:00Z",
      completed_at: null,
      result: null,
      result_summary: null,
      message: null,
      error: null,
      last_error: null,
      progress: 40,
      graph_structure: { mode: "team_kernel", nodes: [], edges: [] },
      node_states: {
        "team.1.research_scholar_v1.1": {
          node_id: "team.1.research_scholar_v1.1",
          node_type: "agent_invocation",
          label: "文献专家",
          status: "completed",
          node_metadata: {
            team: true,
            template_id: "research_scholar.v1",
            display_name: "文献专家",
            effective_tools: ["web_search", "library_read"],
            effective_skills: ["research-scout"],
          },
        },
      },
    } as unknown as ExecutionRecord;

    const view = runViewFromExecution(record);

    expect(view.team?.members).toEqual([
      {
        id: "team.1.research_scholar_v1.1",
        templateId: "research_scholar.v1",
        displayName: "文献专家",
        status: "completed",
        effectiveTools: ["web_search", "library_read"],
        effectiveSkills: ["research-scout"],
      },
    ]);
    expect(view.team?.mode).toBe("team_kernel");
  });
});
```

- [ ] **Step 2: Run failing frontend test**

Run:

```bash
cd frontend && npx vitest run frontend/lib/__tests__/execution-run-view.team.test.ts
```

Expected: fail because `RunView` has no `team` field.

- [ ] **Step 3: Extend API and RunView types**

Modify `frontend/lib/execution-run-view.ts`:

```ts
export interface RunViewTeamMember {
  id: string;
  templateId?: string | null;
  displayName: string;
  status: string;
  effectiveTools: string[];
  effectiveSkills: string[];
}

export interface RunViewQualityGate {
  id: string;
  status: "pass" | "warning" | "fail";
  severity?: "low" | "medium" | "high";
  nextAction?: string | null;
}

export interface RunViewTeam {
  mode: "team_kernel";
  members: RunViewTeamMember[];
  qualityGates: RunViewQualityGate[];
}
```

Add `team?: RunViewTeam | null;` to `RunView`.

In `runViewFromExecution`, compute:

```ts
  const team = teamViewFromExecution(record);
```

and include `team` in the returned object.

Add helper functions:

```ts
function teamViewFromExecution(record: ExecutionRecord): RunViewTeam | null {
  const mode = record.graph_structure?.mode;
  const nodeStates = record.node_states ?? {};
  const members = Object.values(nodeStates)
    .filter((node) => node?.node_type === "agent_invocation")
    .map((node) => {
      const metadata =
        node.node_metadata && typeof node.node_metadata === "object"
          ? (node.node_metadata as Record<string, unknown>)
          : {};
      return {
        id: stringValue(node.node_id) ?? stringValue(node.id) ?? "",
        templateId: stringValue(metadata.template_id),
        displayName:
          stringValue(metadata.display_name) ??
          stringValue(node.label) ??
          "团队成员",
        status: stringValue(node.status) ?? "pending",
        effectiveTools: stringArray(metadata.effective_tools),
        effectiveSkills: stringArray(metadata.effective_skills),
      };
    })
    .filter((member) => member.id);
  const qualityGates = qualityGatesFromRecord(record);
  if (mode !== "team_kernel" && members.length === 0 && qualityGates.length === 0) {
    return null;
  }
  return { mode: "team_kernel", members, qualityGates };
}

function qualityGatesFromRecord(record: ExecutionRecord): RunViewQualityGate[] {
  const runtimeState = record.runtime_state;
  const gates =
    runtimeState &&
    typeof runtimeState === "object" &&
    Array.isArray((runtimeState as Record<string, unknown>).quality_gates)
      ? ((runtimeState as Record<string, unknown>).quality_gates as unknown[])
      : [];
  return gates
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object" && !Array.isArray(item)))
    .map((item) => ({
      id: stringValue(item.gate_id) ?? stringValue(item.id) ?? "quality_gate",
      status: normalizeGateStatus(item.status),
      severity: normalizeGateSeverity(item.severity),
      nextAction: stringValue(item.next_action),
    }));
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item)).filter(Boolean);
}

function normalizeGateStatus(value: unknown): "pass" | "warning" | "fail" {
  return value === "fail" || value === "warning" ? value : "pass";
}

function normalizeGateSeverity(value: unknown): "low" | "medium" | "high" | undefined {
  return value === "medium" || value === "high" || value === "low" ? value : undefined;
}
```

If `ExecutionRecord["graph_structure"]` lacks `mode`, add it to `frontend/lib/api/types.ts`:

```ts
export interface ExecutionGraphStructure {
  mode?: "static_graph" | "team_kernel";
  nodes: ExecutionGraphNode[];
  edges: ExecutionGraphEdge[];
}
```

Add optional `node_metadata?: Record<string, unknown> | null` to execution node state types when missing.

- [ ] **Step 4: Run Task 4 frontend test**

Run:

```bash
cd frontend && npx vitest run frontend/lib/__tests__/execution-run-view.team.test.ts
```

Expected: pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add frontend/lib/api/types.ts frontend/lib/execution-run-view.ts frontend/lib/__tests__/execution-run-view.team.test.ts
git commit -m "feat: project team execution facts"
```

---

## Task 5: LiveWorkflowPanel Team Display

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
- Test: `frontend/lib/__tests__/execution-run-view.team.test.ts`

- [ ] **Step 1: Add team display helpers**

In `LiveWorkflowPanel.tsx`, near the existing `RunView` component helpers, add:

```tsx
function TeamRoster({ team }: { team: import("@/lib/execution-run-view").RunViewTeam | null | undefined }) {
  if (!team || team.members.length === 0) return null;
  return (
    <div className="mt-3 rounded-lg border border-white/50 bg-white/35 p-3 backdrop-blur-xl">
      <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-slate-500">
        Team
      </div>
      <div className="space-y-2">
        {team.members.map((member) => (
          <div key={member.id} className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-slate-900">
                {member.displayName}
              </div>
              <div className="truncate text-xs text-slate-500">
                {member.effectiveSkills.slice(0, 2).join(" / ") || member.templateId || "team member"}
              </div>
            </div>
            <span className="shrink-0 rounded-full border border-white/60 bg-white/45 px-2 py-0.5 text-[11px] text-slate-600">
              {member.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function QualityGateStrip({ team }: { team: import("@/lib/execution-run-view").RunViewTeam | null | undefined }) {
  if (!team || team.qualityGates.length === 0) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-1.5">
      {team.qualityGates.slice(0, 4).map((gate) => (
        <span
          key={gate.id}
          className="rounded-full border border-white/60 bg-white/35 px-2 py-1 text-[11px] text-slate-600"
        >
          {gate.id}: {gate.status}
        </span>
      ))}
    </div>
  );
}
```

Use existing CSS token conventions if the surrounding component already has local helper styles. Do not add decorative nested cards; this is a compact execution detail group inside the existing run card.

- [ ] **Step 2: Render the team helpers in the active run card**

Inside the `RunView` JSX where summary/progress/node detail are rendered, add:

```tsx
<TeamRoster team={run.team} />
<QualityGateStrip team={run.team} />
```

Place it after the run summary and before result actions so users see who is working before they see outputs.

- [ ] **Step 3: Run frontend typecheck**

Run:

```bash
cd frontend && npm run typecheck
```

Expected: pass.

- [ ] **Step 4: Commit Task 5**

```bash
git add 'frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx'
git commit -m "feat: show dynamic team in workflow panel"
```

---

## Task 6: Team-Kernel Seed Capability

**Files:**
- Create: `backend/seed/capabilities/thesis/team_deep_research.yaml`
- Modify: `backend/tests/integration/test_capability_skill_seeds.py`
- Modify: `backend/tests/seed/test_capability_seeds_load.py`

- [ ] **Step 1: Add failing seed validation tests**

Modify `backend/tests/integration/test_capability_skill_seeds.py` with an explicit team-kernel branch.

Add this helper below `_is_hidden_capability`:

```python
def _is_team_kernel_capability(data: dict) -> bool:
    runtime = data.get("runtime") if isinstance(data.get("runtime"), dict) else {}
    return runtime.get("mode") == "team_kernel"
```

Update graph-template based tests to skip team-kernel capabilities because `team_kernel` does not use static task phases:

```python
def test_every_capability_skill_id_exists():
    skill_ids = _collect_skill_ids()
    assert skill_ids, "no skills found"

    for cap_path in _collect_capability_files():
        data = yaml.safe_load(cap_path.read_text())
        if _is_team_kernel_capability(data):
            continue
        for phase in data["graph_template"]["phases"]:
            for task in phase["tasks"]:
                if task.get("subagent_type") in SKILLLESS_SUBAGENTS:
                    continue
                sid = task.get("skill_id")
                assert sid is not None, f"{cap_path}: task {task.get('name')} missing skill_id"
                assert sid in skill_ids, (
                    f"{cap_path}: task {task['name']} references unknown skill_id '{sid}'. "
                    f"Available: {sorted(skill_ids)}"
                )
```

Apply the same early `if _is_team_kernel_capability(data): continue` branch in:

- `test_every_capability_subagent_type_is_registered`
- `test_searcher_capabilities_query_uses_runtime_request_fields`
- `test_visible_multistep_capabilities_are_sequential`

Modify `test_every_capability_required_fields_present` so `runtime` is allowed only for team-kernel records:

```python
def test_every_capability_required_fields_present():
    required = {
        "schema_version",
        "id",
        "workspace_type",
        "display",
        "intent",
        "mission",
        "inputs",
        "context_policy",
        "sandbox_policy",
        "review_policy",
        "quality_gates",
        "graph_template",
    }
    for cap_path in _collect_capability_files():
        data = yaml.safe_load(cap_path.read_text())
        missing = required - set(data.keys())
        assert not missing, f"{cap_path}: missing fields {missing}"
        assert data["schema_version"] == "capability.v2"
        if _is_hidden_capability(data):
            assert data["mission"]["primary_surface"] in {"prism", "sandbox", "none", "rooms"}
        elif _is_team_kernel_capability(data):
            assert data["mission"]["primary_surface"] in {"prism", "rooms"}
        else:
            assert data["mission"]["primary_surface"] == "prism"
        assert "requires_sandbox" not in data
        if _is_team_kernel_capability(data):
            assert data["runtime"]["mode"] == "team_kernel"
            assert isinstance(data.get("team_policy"), dict)
            assert data["graph_template"] == {}
        else:
            assert "runtime" not in data
```

Modify `test_every_capability_declares_result_exit` so team-kernel capabilities declare review exits through `review_policy` instead of static graph task outputs:

```python
        if _is_team_kernel_capability(data):
            targets = data.get("review_policy", {}).get("default_targets") or []
            assert targets, f"{cap_path}: team_kernel capability must declare review_policy.default_targets"
            continue
```

Place that branch after `data = yaml.safe_load(cap_path.read_text())` and before building the `outputs` list.

Add the new team-policy-specific test:

```python
def test_team_kernel_capabilities_declare_team_policy():
    for cap_path in _collect_capability_files():
        data = yaml.safe_load(cap_path.read_text())
        runtime = data.get("runtime") if isinstance(data.get("runtime"), dict) else {}
        if runtime.get("mode") != "team_kernel":
            continue
        team_policy = data.get("team_policy")
        assert isinstance(team_policy, dict), f"{cap_path}: team_kernel requires team_policy"
        assert team_policy.get("core_templates"), f"{cap_path}: team_policy.core_templates is required"
        assert team_policy.get("limits"), f"{cap_path}: team_policy.limits is required"
        assert data.get("graph_template") in ({}, None), f"{cap_path}: team_kernel must not keep static graph_template"
```

- [ ] **Step 2: Run failing seed test**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/integration/test_capability_skill_seeds.py::test_team_kernel_capabilities_declare_team_policy -q
```

Expected: fail until the test helper is adjusted or no team capability exists. If it passes because no team capability exists, proceed and use the next step to make it meaningful.

- [ ] **Step 3: Create the first team-kernel capability seed**

Create `backend/seed/capabilities/thesis/team_deep_research.yaml`:

```yaml
schema_version: capability.v2
id: team_deep_research
workspace_type: thesis
enabled: true
display:
  name: 专家团队深度调研
  description: 由文献专家、写作编辑和质量审稿人协作完成可审阅的深度调研结果
  icon: users
  color: blue
  order: 15
  entry_tier: primary
intent:
  description: 围绕研究主题组建专家团队，完成文献检索、证据归纳、质量审查和结果整理
  trigger_phrases:
    - 专家团队调研
    - 深度调研
    - 文献团队
  disambiguation: {}
mission:
  goal: produce_workspace_review_package
  primary_surface: rooms
  document_role: research_report
  user_promise: 生成可审阅的文献与证据调研包
  allowed_deliverables:
    - evidence_pack
    - review_report
inputs:
  required_decisions: []
  brief_schema:
    type: object
    properties:
      topic:
        type: string
      query:
        type: string
      raw_message:
        type: string
      constraints:
        type: string
context_policy:
  room_reads:
    library: summary
    documents: excerpts
    decisions: full
    memory: relevant
  prism_context: {}
  full_text_access: explicit_tool_only
sandbox_policy:
  mode: none
  profiles: []
  allowed_operations: []
review_policy:
  default_targets:
    - room_document
    - room_memory_candidate
    - room_task
  require_user_acceptance: true
  allow_bulk_accept: true
citation_policy:
  source_scope: workspace_library
  required_for_prism_manuscript: false
  record_usage: true
quality_gates:
  - evidence_traceability
  - citation_quality
  - writing_coherence
  - critical_review
  - thesis_structure_matches_school_template
  - chapter_claims_have_evidence
  - references_follow_target_style
runtime:
  mode: team_kernel
  entry_surface: workbench
  allowed_tools:
    - web_search
    - library_read
    - document_read
    - memory_read
    - citation_parser
    - artifact_create
team_policy:
  core_templates:
    - research_scholar.v1
    - writing_editor.v1
    - critical_reviewer.v1
  optional_templates:
    - generalist_assistant.v1
  capability_tools:
    - web_search
    - library_read
    - document_read
    - memory_read
    - citation_parser
    - artifact_create
  capability_skills:
    - research-scout
    - citation-auditor
    - manuscript-writer
    - review-critic
  quality_pipeline:
    - evidence_traceability
    - citation_quality
    - writing_coherence
    - critical_review
  recruitment_triggers:
    missing_sources:
      prefer: research_scholar.v1
    unsupported_claims:
      prefer: critical_reviewer.v1
    final_review_required:
      prefer: critical_reviewer.v1
  limits:
    max_iterations: 3
    max_parallel_invocations: 3
    max_invocations_total: 9
    max_invocations_per_template: 3
    no_progress_rounds_before_stop: 2
  budget:
    max_tokens_soft: 80000
    max_tokens_hard: 120000
graph_template: {}
ui_meta:
  icon: users
  color: blue
  order: 15
  entry_tier: primary
  stages:
    - 组建团队
    - 文献与证据整理
    - 质量审查
    - 结果归档
dashboard_meta: {}
notes: 首个 team_kernel 垂直切片能力，用于验证动态团队运行和前端投影。
```

- [ ] **Step 4: Ensure capability materialization preserves `team_policy`**

If `DataServiceCatalogService.capability_values()` only stores unknown top-level fields inside `definition_json`, no change is needed. If tests show `team_policy` is stripped, modify it so `definition_json = {**data}` remains intact and `runtime` stores `data["runtime"]`.

- [ ] **Step 5: Run seed tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/integration/test_capability_skill_seeds.py tests/seed/test_capability_seeds_load.py -q
```

Expected: pass.

- [ ] **Step 6: Commit Task 6**

```bash
git add backend/seed/capabilities/thesis/team_deep_research.yaml backend/tests/integration/test_capability_skill_seeds.py backend/tests/seed/test_capability_seeds_load.py
git commit -m "feat: seed team deep research capability"
```

---

## Task 7: Architecture Guards And Full Verification

**Files:**
- Modify: `backend/tests/architecture/test_super_agent_capability_cutover.py`
- Modify: `backend/tests/architecture/test_feature_execution_contract.py`

- [ ] **Step 1: Add architecture guard tests**

Add to `backend/tests/architecture/test_super_agent_capability_cutover.py`:

```python
def test_team_kernel_does_not_fallback_to_static_graph_runtime():
    runtime_source = Path("src/agents/lead_agent/v2/runtime.py").read_text(encoding="utf-8")
    assert "runtime.get(\"mode\") == \"team_kernel\"" in runtime_source
    assert "fallback" not in runtime_source.lower()
```

Add to `backend/tests/architecture/test_feature_execution_contract.py`:

```python
def test_subagents_do_not_commit_rooms_or_recruit_nested_teams():
    subagent_root = Path("src/subagents/v2")
    forbidden = ["CommitService(", "execution_commit_service", "TeamKernelRuntime(", "recruit_members"]
    for path in subagent_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path} must not use {token}"
```

If these files do not import `Path`, add:

```python
from pathlib import Path
```

- [ ] **Step 2: Run architecture guards**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/architecture/test_super_agent_capability_cutover.py tests/architecture/test_feature_execution_contract.py -q
```

Expected: pass.

- [ ] **Step 3: Run focused backend verification**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_policy.py tests/agents/lead_agent/v2/test_team_kernel.py tests/agents/lead_agent/v2/test_runtime.py tests/dataservice/test_catalog_domain.py tests/integration/test_capability_skill_seeds.py tests/seed/test_capability_seeds_load.py tests/architecture/test_super_agent_capability_cutover.py tests/architecture/test_feature_execution_contract.py -q
```

Expected: pass.

- [ ] **Step 4: Run frontend verification**

Run:

```bash
cd frontend && npx vitest run frontend/lib/__tests__/execution-run-view.team.test.ts
cd frontend && npm run typecheck
```

Expected: both pass.

- [ ] **Step 5: Run full verification if focused checks pass**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
cd frontend && npm run typecheck
cd frontend && npm run build
```

Expected: all pass.

- [ ] **Step 6: Commit Task 7**

```bash
git add backend/tests/architecture/test_super_agent_capability_cutover.py backend/tests/architecture/test_feature_execution_contract.py
git commit -m "test: guard team agent architecture boundaries"
```

---

## Implementation Notes

- Do not implement nested subagent recruitment in this slice.
- Do not let team members call room commit services.
- Keep `static_graph` and `team_kernel` explicit runtime modes.
- Store dynamic team facts in execution node/event facts first; do not create a separate execution state source.
- Let agent tools stay high-ceiling through `tool_affinity` plus runtime filtering; only direct commit/apply tools are hard-blocked for subagents.
- If a high-risk tool is needed later, add it behind sandbox/risk metadata instead of removing it from the agent model.
- If existing seed validators reject empty `graph_template`, update the validator to allow `{}` only when `runtime.mode == "team_kernel"`.

## Self-Review Checklist

- Spec coverage:
  - AgentTemplate catalog: Task 1.
  - Capability `team_policy`: Tasks 2 and 6.
  - Dynamic invocation facts: Task 3 and Task 4.
  - TeamBlackboard and QualityGate contracts: Task 2 and Task 3.
  - High-ceiling tools with safety boundaries: Task 2 and Task 7.
  - Frontend projection: Task 4 and Task 5.
  - Clean runtime modes without fallback: Task 3 and Task 7.
- Marker scan target: every task should be fully specified and ready to execute.
- Type consistency:
  - Backend contract name is `AgentTemplate`.
  - DataService projection name is `AgentTemplateRecord`.
  - Client payload name is `AgentTemplatePayload`.
  - Runtime fact name is `AgentInvocation`.
  - Frontend projection field is `RunView.team`.
