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
                section_key varchar(255) not null default '',
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
                section_key varchar(255) not null default '',
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
    await test_session.execute(
        text(
            """
            create table workspace_references (
                id varchar(36) primary key,
                workspace_id varchar(36) not null,
                citation_key varchar(255) not null,
                is_deleted boolean not null default 0
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
async def test_pending_file_change_records_canonical_source_links_from_citations(
    db: AsyncSession,
    user: SimpleNamespace,
    workspace: SimpleNamespace,
) -> None:
    from src.services.prism_review_service import PrismReviewService

    project = LatexProject(
        id="latex-source-links",
        user_id=user.id,
        name="Source Link Manuscript",
        workspace_id=workspace.id,
        surface_role="primary_manuscript",
        main_file="main.tex",
        llm_config={"metadata": {}},
    )
    db.add(project)
    await db.execute(
        text(
            """
            insert into workspace_references (
                id, workspace_id, citation_key, is_deleted
            )
            values
                ('ref-1', :workspace_id, 'doe2026', 0),
                ('ref-deleted', :workspace_id, 'deleted2026', 1)
            """
        ),
        {"workspace_id": workspace.id},
    )
    await db.commit()

    review_item = await PrismReviewService(db).upsert_pending_file_change(
        project,
        logical_key="section:intro",
        path="sections/intro.tex",
        reason="feature_proposal",
        pending_content=r"Grounded claim \cite{doe2026,missing2026,deleted2026}.",
        pending_hash="hash-new",
        current_hash="hash-old",
        source_execution_id="exec-1",
        source_task_id="task-1",
    )

    result = await db.execute(
        text(
            """
            select review_item_id, source_type, source_id, file_path,
                   section_key, citation_key, usage
            from prism_source_links
            order by source_id
            """
        )
    )
    links = [dict(row) for row in result.mappings().all()]
    assert links == [
        {
            "review_item_id": str(review_item.id),
            "source_type": "library_item",
            "source_id": "ref-1",
            "file_path": "sections/intro.tex",
            "section_key": "section:intro",
            "citation_key": "doe2026",
            "usage": "cited",
        }
    ]

    await PrismReviewService(db).upsert_pending_file_change(
        project,
        logical_key="section:intro",
        path="sections/intro.tex",
        reason="feature_proposal",
        pending_content="No citation in this revision.",
        pending_hash="hash-newer",
        current_hash="hash-old",
    )

    count_result = await db.execute(text("select count(*) from prism_source_links"))
    assert count_result.scalar_one() == 0


@pytest.mark.asyncio
async def test_manual_protect_records_canonical_protected_section(
    db: AsyncSession,
    workspace: SimpleNamespace,
) -> None:
    from src.services.prism_review_service import PrismReviewService

    await PrismReviewService(db).upsert_protected_section(
        workspace_id=workspace.id,
        latex_project_id="latex-manual-protect",
        file_path="sections/introduction.tex",
        section_key="",
        scope="file",
        reason="user_manual_protect",
        source="manual_edit",
    )
    await db.commit()

    result = await db.execute(
        text(
            """
            select file_path, section_key, scope, reason, source
            from prism_protected_sections
            where latex_project_id = 'latex-manual-protect'
            """
        )
    )
    assert dict(result.mappings().one()) == {
        "file_path": "sections/introduction.tex",
        "section_key": "",
        "scope": "file",
        "reason": "user_manual_protect",
        "source": "manual_edit",
    }


@pytest.mark.asyncio
async def test_surface_projection_includes_review_provenance_and_protection(
    db: AsyncSession,
    user: SimpleNamespace,
    workspace: SimpleNamespace,
) -> None:
    from src.services.workspace_prism_service import WorkspacePrismService

    project = LatexProject(
        id="latex-prism",
        user_id=user.id,
        name="Prism Manuscript",
        workspace_id=workspace.id,
        surface_role="primary_manuscript",
        main_file="main.tex",
        llm_config={"metadata": {"section_map": {"intro": "sections/intro.tex"}}},
    )
    db.add(project)
    await db.flush()
    await db.execute(
        text(
            """
            insert into prism_review_items (
                id, workspace_id, latex_project_id, logical_key, source_type,
                source_execution_id, source_task_id, target_kind, target_file_path,
                title, summary, status, preview_payload
            )
            values (
                'review-1', :workspace_id, 'latex-prism', 'section:intro', 'execution',
                'exec-1', 'task-1', 'prism_file_change', 'sections/intro.tex',
                'Intro rewrite', 'feature_proposal', 'pending',
                '{"pending_content":"Generated intro"}'
            )
            """
        ),
        {"workspace_id": workspace.id},
    )
    await db.execute(
        text(
            """
            insert into prism_source_links (
                id, workspace_id, latex_project_id, review_item_id, source_type,
                source_id, file_path, section_key, quote, citation_key, usage
            )
            values (
                'source-1', :workspace_id, 'latex-prism', 'review-1', 'library',
                'lib-1', 'sections/intro.tex', 'section:intro', 'key excerpt',
                'doe2026', 'citation'
            )
            """
        ),
        {"workspace_id": workspace.id},
    )
    await db.execute(
        text(
            """
            insert into prism_protected_sections (
                id, workspace_id, latex_project_id, file_path, section_key,
                scope, reason, source
            )
            values (
                'protected-1', :workspace_id, 'latex-prism', 'sections/intro.tex',
                'section:intro', 'section', 'user_protected', 'review_reject'
            )
            """
        ),
        {"workspace_id": workspace.id},
    )
    await db.execute(
        text(
            """
            insert into decisions (
                id, workspace_id, key, value, confidence, extracted_by
            )
            values (
                'decision-1', :workspace_id, 'citation_style', 'APA 7', 1.0, 'user'
            )
            """
        ),
        {"workspace_id": workspace.id},
    )
    await db.execute(
        text(
            """
            insert into memory_facts (
                id, workspace_id, category, content, confidence, reference_count
            )
            values (
                'memory-1', :workspace_id, 'writing_style',
                'Prefer concise topic sentences', 0.9, 3
            )
            """
        ),
        {"workspace_id": workspace.id},
    )
    await db.execute(
        text(
            """
            insert into run_history (
                id, workspace_id, execution_id, capability_id, title, summary,
                status, artifact_count, duration_seconds
            )
            values (
                'run-1', :workspace_id, 'exec-1', 'writing', 'Intro drafting',
                'Generated manuscript update', 'completed', 1, 12
            )
            """
        ),
        {"workspace_id": workspace.id},
    )
    await db.commit()

    projection = await WorkspacePrismService(db).get_surface_projection(
        workspace.id,
        user_id=user.id,
    )

    assert projection["review_summary"] == {
        "pending_count": 1,
        "applied_count": 0,
        "source_link_count": 1,
        "protected_section_count": 1,
    }
    assert projection["file_changes"][0]["source_execution_id"] == "exec-1"
    assert projection["file_changes"][0]["pending_content"] == "Generated intro"
    assert projection["review_items"][0]["id"] == "review-1"
    assert projection["review_items"][0]["kind"] == "prism_file_change"
    assert projection["review_items"][0]["target"]["file_path"] == "sections/intro.tex"
    assert {
        action["action"] for action in projection["review_items"][0]["actions"]
    } == {
        "preview_prism_change",
        "apply_prism_change",
        "reject_prism_change",
        "defer_prism_change",
    }
    assert projection["source_links"][0]["citation_key"] == "doe2026"
    assert projection["protected_sections"][0]["reason"] == "user_protected"
    assert projection["decisions"][0]["key"] == "citation_style"
    assert projection["memory_preferences"][0]["content"] == (
        "Prefer concise topic sentences"
    )
    activity_titles = {item["title"] for item in projection["recent_activity"]}
    assert "Intro drafting" in activity_titles
    assert "待确认稿件修改: Intro rewrite" in activity_titles
    assert projection["context_summary"] == {
        "decision_count": 1,
        "memory_preference_count": 1,
        "recent_activity_count": 2,
    }

    launch_context = await WorkspacePrismService(db).get_launch_context_projection(
        workspace.id,
        user_id=user.id,
    )
    assert launch_context["main_file"] == "main.tex"
    assert launch_context["pending_review_items"][0]["id"] == "review-1"
    assert launch_context["pending_review_items"][0]["target_file_path"] == (
        "sections/intro.tex"
    )
    assert launch_context["source_links"][0]["citation_key"] == "doe2026"
    assert "pending_content" not in launch_context["pending_review_items"][0]


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
