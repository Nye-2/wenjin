"""Tests for workspace Prism surface binding service."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.latex_project import LatexProject
from tests.database.conftest import DbUser, DbWorkspace


@pytest_asyncio.fixture
async def db(test_session: AsyncSession) -> AsyncSession:
    await test_session.execute(
        text(
            """
            create table prism_review_items (
                id varchar(36) primary key,
                workspace_id varchar(36) not null,
                latex_project_id varchar(36) not null,
                logical_key varchar(255) not null,
                source_type varchar(64) not null,
                source_execution_id varchar(36),
                source_task_id varchar(36),
                target_kind varchar(64) not null,
                target_file_path varchar(1024),
                target_room varchar(64),
                target_item_id varchar(36),
                title varchar(255) not null,
                summary varchar(1000),
                status varchar(32) not null default 'pending',
                preview_payload json not null default '{}',
                applied_at datetime,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                unique (latex_project_id, logical_key)
            )
            """
        )
    )
    await test_session.execute(
        text(
            """
            create table prism_protected_sections (
                id varchar(36) primary key,
                workspace_id varchar(36) not null,
                latex_project_id varchar(36) not null,
                file_path varchar(1024) not null,
                section_key varchar(255),
                scope varchar(32) not null,
                reason varchar(1000),
                source varchar(64) not null,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                unique (latex_project_id, file_path, section_key, scope)
            )
            """
        )
    )
    await test_session.execute(
        text(
            """
            create table prism_source_links (
                id varchar(36) primary key,
                workspace_id varchar(36) not null,
                latex_project_id varchar(36) not null,
                review_item_id varchar(36),
                source_type varchar(64) not null,
                source_id varchar(255) not null,
                file_path varchar(1024) not null,
                section_key varchar(255),
                quote varchar(4000),
                citation_key varchar(255),
                usage varchar(64) not null,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp
            )
            """
        )
    )
    await test_session.execute(
        text(
            """
            create table latex_projects (
                id varchar(36) primary key,
                user_id varchar(36) not null,
                name varchar(255) not null,
                template_id varchar(50),
                main_file varchar(255) not null default 'main.tex',
                tags json not null default '[]',
                archived boolean not null default 0,
                trashed boolean not null default 0,
                trashed_at datetime,
                file_order json not null default '{}',
                llm_config json,
                workspace_id varchar(36),
                surface_role varchar(64),
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp
            )
            """
        )
    )
    await test_session.commit()
    return test_session


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> SimpleNamespace:
    row = DbUser(
        id="user-1",
        email="user-1@example.com",
        name="User 1",
        hashed_password="hashed",
    )
    db.add(row)
    await db.commit()
    return SimpleNamespace(id=row.id)


@pytest_asyncio.fixture
async def workspace(db: AsyncSession, user: SimpleNamespace) -> SimpleNamespace:
    row = DbWorkspace(
        id="ws-1",
        user_id=user.id,
        name="Workspace 1",
        type="thesis",
        thread_id=None,
    )
    db.add(row)
    await db.commit()
    return SimpleNamespace(id=row.id, user_id=row.user_id, name=row.name)


@pytest.mark.asyncio
async def test_get_primary_project_prefers_explicit_workspace_binding(
    db: AsyncSession,
    user: SimpleNamespace,
) -> None:
    from src.services.workspace_prism_service import WorkspacePrismService

    explicit = LatexProject(
        id="latex-explicit",
        user_id=user.id,
        name="Explicit Manuscript",
        workspace_id="ws-1",
        surface_role="primary_manuscript",
        llm_config={"workspace_id": "legacy-ws", "bridge": "workspace_latex_project"},
    )
    legacy = LatexProject(
        id="latex-legacy",
        user_id=user.id,
        name="Legacy Manuscript",
        llm_config={"workspace_id": "ws-1", "bridge": "workspace_latex_project"},
    )
    db.add_all([explicit, legacy])
    await db.commit()

    project = await WorkspacePrismService(db).get_primary_project(
        "ws-1",
        user_id=user.id,
    )

    assert project is not None
    assert str(project.id) == "latex-explicit"


@pytest.mark.asyncio
async def test_get_primary_project_ignores_legacy_llm_config_binding(
    db: AsyncSession,
    user: SimpleNamespace,
) -> None:
    from src.services.workspace_prism_service import WorkspacePrismService

    legacy = LatexProject(
        id="latex-legacy",
        user_id=user.id,
        name="Legacy Manuscript",
        llm_config={"workspace_id": "ws-2", "bridge": "workspace_latex_project"},
    )
    db.add(legacy)
    await db.commit()

    project = await WorkspacePrismService(db).get_primary_project(
        "ws-2",
        user_id=user.id,
    )

    assert project is None


@pytest.mark.asyncio
async def test_ensure_primary_project_creates_explicit_binding_without_promoting_legacy(
    db: AsyncSession,
    user: SimpleNamespace,
    workspace: SimpleNamespace,
) -> None:
    from src.services.workspace_prism_service import WorkspacePrismService

    legacy = LatexProject(
        id="latex-legacy",
        user_id=user.id,
        name="Legacy Manuscript",
        llm_config={"workspace_id": workspace.id, "bridge": "workspace_latex_project"},
    )
    db.add(legacy)
    await db.commit()

    project = await WorkspacePrismService(db).ensure_primary_project(
        workspace.id,
        user_id=user.id,
        project_name="Workspace 1",
    )

    await db.refresh(legacy)

    assert str(project.id) != "latex-legacy"
    assert project.workspace_id == workspace.id
    assert project.surface_role == "primary_manuscript"
    assert legacy.workspace_id is None
    assert legacy.surface_role is None


@pytest.mark.asyncio
async def test_workspace_latex_project_service_finds_explicit_binding_without_legacy_llm_config(
    db: AsyncSession,
    user: SimpleNamespace,
    workspace: SimpleNamespace,
) -> None:
    from src.services.workspace_latex_projects import WorkspaceLatexProjectService

    explicit = LatexProject(
        id="latex-explicit",
        user_id=user.id,
        name="Explicit Manuscript",
        workspace_id=workspace.id,
        surface_role="primary_manuscript",
        llm_config={"template": "thesis_default"},
    )
    db.add(explicit)
    await db.commit()

    service = WorkspaceLatexProjectService(db)
    service.sync_project = AsyncMock(side_effect=AssertionError("unexpected sync"))  # type: ignore[method-assign]

    project = await service.ensure_workspace_project(workspace_id=workspace.id)

    assert str(project.id) == "latex-explicit"


@pytest.mark.asyncio
async def test_binding_integrity_report_flags_missing_and_duplicate_primary_projects(
    db: AsyncSession,
    user: SimpleNamespace,
) -> None:
    from src.services.workspace_prism_service import WorkspacePrismService

    db.add_all(
        [
            DbWorkspace(
                id="ws-missing",
                user_id=user.id,
                name="Missing Prism",
                type="thesis",
                thread_id=None,
            ),
            DbWorkspace(
                id="ws-ok",
                user_id=user.id,
                name="Healthy Prism",
                type="thesis",
                thread_id=None,
            ),
            DbWorkspace(
                id="ws-duplicate",
                user_id=user.id,
                name="Duplicate Prism",
                type="thesis",
                thread_id=None,
            ),
        ]
    )
    db.add_all(
        [
            LatexProject(
                id="latex-ok",
                user_id=user.id,
                name="Healthy Manuscript",
                workspace_id="ws-ok",
                surface_role="primary_manuscript",
            ),
            LatexProject(
                id="latex-duplicate-1",
                user_id=user.id,
                name="Duplicate Manuscript 1",
                workspace_id="ws-duplicate",
                surface_role="primary_manuscript",
            ),
            LatexProject(
                id="latex-duplicate-2",
                user_id=user.id,
                name="Duplicate Manuscript 2",
                workspace_id="ws-duplicate",
                surface_role="primary_manuscript",
            ),
        ]
    )
    await db.commit()

    report = await WorkspacePrismService(db).get_binding_integrity_report(
        user_id=user.id,
    )

    missing_ids = {item["workspace_id"] for item in report["missing_primary"]}
    duplicate_counts = {
        item["workspace_id"]: item["primary_count"]
        for item in report["duplicate_primary"]
    }
    assert "ws-missing" in missing_ids
    assert "ws-ok" not in missing_ids
    assert duplicate_counts == {"ws-duplicate": 2}
