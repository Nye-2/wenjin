"""Tests for workspace Prism surface binding service."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.latex_project import LatexProject
from tests.database.conftest import DbUser, DbWorkspace


class _DbBackedDataServiceClient:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_workspace(self, workspace_id: str) -> SimpleNamespace | None:
        workspace = await self.db.get(DbWorkspace, workspace_id)
        if workspace is None:
            return None
        return SimpleNamespace(
            id=workspace.id,
            created_by_user_id=workspace.user_id,
            name=workspace.name,
            workspace_type=workspace.type,
        )

    async def get_prism_primary_project(self, workspace_id: str):
        from src.dataservice.prism_api import PrismDataService

        return await PrismDataService(self.db, autocommit=False).get_primary_project(workspace_id)

    async def get_prism_surface(self, workspace_id: str):
        from src.dataservice.prism_api import PrismDataService

        return await PrismDataService(self.db, autocommit=False).get_surface(workspace_id)

    async def ensure_prism_primary_project(self, workspace_id: str, command: object):
        from src.dataservice.prism_api import PrismDataService

        return await PrismDataService(self.db, autocommit=False).ensure_primary_project(command)

    async def list_prism_protected_scopes(self, project_id: str, *, limit: int = 200):
        from src.dataservice.prism_api import PrismDataService

        return await PrismDataService(self.db, autocommit=False).list_protected_scopes(project_id, limit=limit)

    async def get_latex_project(self, project_id: str):
        from src.dataservice.latex_api import LatexDataService

        return await LatexDataService(self.db, autocommit=False).get_project(project_id)

    async def get_workspace_primary_latex_project(
        self,
        *,
        workspace_id: str,
        owner_user_id: str,
        template: str | None = None,
    ):
        from src.dataservice.latex_api import LatexDataService

        return await LatexDataService(self.db, autocommit=False).get_workspace_primary_project(
            workspace_id=workspace_id,
            owner_user_id=owner_user_id,
            template=template,
        )

    async def create_latex_project(self, command: object):
        from src.dataservice.latex_api import LatexDataService

        return await LatexDataService(self.db, autocommit=False).create_project(**command.model_dump())

    async def update_latex_project(self, project_id: str, command: object):
        from src.dataservice.latex_api import LatexDataService

        service = LatexDataService(self.db, autocommit=False)
        project = await service.get_project(project_id)
        if project is None:
            return None
        return await service.update_project(project, **command.model_dump(exclude_unset=True))

    async def touch_latex_project(self, project_id: str, command: object):
        from src.dataservice.latex_api import LatexDataService

        service = LatexDataService(self.db, autocommit=False)
        project = await service.get_project(project_id)
        if project is None:
            return None
        return await service.touch_project(project, **command.model_dump(exclude_unset=True))

    async def attach_workspace_latex_project(self, project_id: str, command: object):
        from src.dataservice.latex_api import LatexDataService

        service = LatexDataService(self.db, autocommit=False)
        project = await service.get_project(project_id)
        if project is None:
            return None
        return await service.attach_workspace_project(project, workspace_id=command.workspace_id)

    async def clear_pending_prism_file_change(self, command: object) -> bool:
        from src.dataservice.prism_review_api import PrismReviewDataService

        return await PrismReviewDataService(self.db, autocommit=False).clear_pending_file_change(
            **command.model_dump(mode="json")
        )

    async def upsert_pending_prism_file_change(self, command: object):
        from src.dataservice.prism_review_api import PrismReviewDataService

        return await PrismReviewDataService(self.db, autocommit=False).upsert_pending_file_change(
            **command.model_dump(mode="json")
        )

    async def list_review_items(self, **kwargs: object):
        from src.dataservice.review_api import ReviewDataService

        return await ReviewDataService(self.db, autocommit=False).list_items(**kwargs)

    async def list_provenance_links(self, **kwargs: object):
        from src.dataservice.provenance_api import ProvenanceDataService

        return await ProvenanceDataService(self.db, autocommit=False).list_links(**kwargs)

    async def list_room_decisions(self, workspace_id: str) -> list[object]:
        from src.dataservice.rooms_api import RoomsDataService

        return await RoomsDataService(self.db, autocommit=False).list_active_decisions(workspace_id)

    async def list_room_memory_facts(self, *, workspace_id: str, limit: int = 15, category: str | None = None):
        from src.dataservice.rooms_api import RoomsDataService

        return await RoomsDataService(self.db, autocommit=False).list_memory_facts(
            workspace_id=workspace_id,
            limit=limit,
            category=category,
        )

    async def list_executions(self, *, workspace_id: str, limit: int = 5, **_kwargs: object):
        result = await self.db.execute(
            text(
                """
                select id, workspace_id, execution_id, capability_id, title, summary,
                       status, artifact_count, duration_seconds, created_at
                from run_history
                where workspace_id = :workspace_id
                order by created_at desc
                limit :limit
                """
            ),
            {"workspace_id": workspace_id, "limit": limit},
        )
        return [SimpleNamespace(**dict(row)) for row in result.mappings().all()]

    async def get_latex_binding_integrity_report(self, *, user_id: str | None = None):
        params: dict[str, object] = {"surface_role": "primary_manuscript"}
        user_filter = ""
        if user_id is not None:
            params["user_id"] = user_id
            user_filter = "where w.user_id = :user_id"
        result = await self.db.execute(
            text(
                f"""
                select w.id as workspace_id, w.user_id as user_id,
                       w.name as workspace_name, count(lp.id) as primary_count
                from workspaces w
                left join latex_projects lp
                  on lp.workspace_id = w.id
                 and lp.surface_role = :surface_role
                {user_filter}
                group by w.id, w.user_id, w.name
                having count(lp.id) = 0 or count(lp.id) > 1
                order by w.id
                """
            ),
            params,
        )
        missing_primary: list[dict[str, object]] = []
        duplicate_primary: list[dict[str, object]] = []
        for row in result.mappings():
            item = {
                "workspace_id": str(row["workspace_id"]),
                "user_id": str(row["user_id"]),
                "workspace_name": str(row["workspace_name"] or ""),
                "primary_count": int(row["primary_count"] or 0),
            }
            if item["primary_count"] == 0:
                missing_primary.append(item)
            else:
                duplicate_primary.append(item)
        return {"missing_primary": missing_primary, "duplicate_primary": duplicate_primary}


@pytest_asyncio.fixture
async def db(test_session: AsyncSession) -> AsyncSession:
    await test_session.execute(
        text(
            """
            create table review_batches (
                id varchar(36) primary key,
                workspace_id varchar(36) not null,
                execution_id varchar(36),
                source_type varchar(64) not null,
                source_id varchar(255),
                review_kind varchar(64) not null,
                status varchar(32) not null default 'pending',
                title varchar(255) not null,
                summary text,
                schema_version varchar(50) not null default 'review_batch.v1',
                item_count integer not null default 0,
                accepted_count integer not null default 0,
                rejected_count integer not null default 0,
                applied_count integer not null default 0,
                failed_count integer not null default 0,
                payload_json json not null default '{}',
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp
            )
            """
        )
    )
    await test_session.execute(
        text(
            """
            create table review_items (
                id varchar(36) primary key,
                batch_id varchar(36) not null,
                workspace_id varchar(36) not null,
                source_item_id varchar(255),
                item_kind varchar(64) not null,
                target_domain varchar(64) not null,
                target_kind varchar(64) not null,
                target_ref_json json not null default '{}',
                status varchar(32) not null default 'pending',
                title varchar(255) not null,
                summary text,
                payload_json json not null default '{}',
                preview_json json not null default '{}',
                result_json json,
                error_text text,
                provenance_json json not null default '{}',
                sort_order integer not null default 0,
                applied_at datetime,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp
            )
            """
        )
    )
    await test_session.execute(
        text(
            """
            create table review_action_logs (
                id varchar(36) primary key,
                batch_id varchar(36) not null,
                item_id varchar(36),
                workspace_id varchar(36) not null,
                action varchar(64) not null,
                actor_id varchar(36),
                status_from varchar(32),
                status_to varchar(32),
                payload_json json not null default '{}',
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
            create table prism_projects (
                id varchar(36) primary key,
                workspace_id varchar(36) not null,
                role varchar(64) not null,
                title varchar(255) not null,
                adapter_kind varchar(50) not null default 'latex',
                adapter_ref_id varchar(100),
                status varchar(32) not null default 'active',
                settings_json json not null default '{}',
                adapter_metadata_json json not null default '{}',
                trashed_at datetime,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp
            )
            """
        )
    )
    await test_session.execute(
        text(
            """
            create table prism_documents (
                id varchar(36) primary key,
                workspace_id varchar(36) not null,
                project_id varchar(36) not null,
                document_kind varchar(50) not null,
                title varchar(255) not null,
                adapter_kind varchar(50) not null default 'latex',
                status varchar(32) not null default 'active',
                root_file_id varchar(36),
                metadata_json json not null default '{}',
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp
            )
            """
        )
    )
    await test_session.execute(
        text(
            """
            create table prism_files (
                id varchar(36) primary key,
                workspace_id varchar(36) not null,
                document_id varchar(36) not null,
                path varchar(1024) not null,
                file_role varchar(50) not null,
                mime_type varchar(100),
                current_version_id varchar(36),
                content_hash varchar(128),
                sort_order integer not null default 0,
                metadata_json json not null default '{}',
                deleted_at datetime,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                unique (document_id, path)
            )
            """
        )
    )
    await test_session.execute(
        text(
            """
            create table prism_file_versions (
                id varchar(36) primary key,
                workspace_id varchar(36) not null,
                file_id varchar(36) not null,
                version_no integer not null,
                review_item_id varchar(36),
                content_inline text,
                content_asset_id varchar(36),
                content_hash varchar(128) not null,
                created_by varchar(100) not null,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                unique (file_id, version_no)
            )
            """
        )
    )
    await test_session.execute(
        text(
            """
            create table prism_protected_scopes (
                id varchar(36) primary key,
                workspace_id varchar(36) not null,
                project_id varchar(36) not null,
                document_id varchar(36),
                file_id varchar(36),
                file_path varchar(1024) not null,
                section_key varchar(255) not null default '',
                scope varchar(32) not null,
                reason varchar(1000),
                source varchar(64) not null,
                metadata_json json not null default '{}',
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp,
                unique (project_id, file_path, section_key, scope)
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
    await test_session.execute(
        text(
            """
            create table sources (
                id varchar(36) primary key,
                workspace_id varchar(36) not null,
                source_kind varchar(50) not null default 'paper',
                title varchar(1000) not null,
                normalized_title varchar(1000) not null,
                authors_json json not null default '[]',
                year integer,
                venue varchar(500),
                publication_type varchar(100),
                doi varchar(255),
                url varchar(1000),
                abstract text,
                citation_count integer,
                ingest_kind varchar(50) not null default 'manual',
                ingest_label varchar(255),
                ingest_execution_id varchar(36),
                verified_at datetime,
                library_status varchar(50) not null default 'candidate',
                evidence_level varchar(50) not null default 'metadata_only',
                fulltext_status varchar(50) not null default 'none',
                citation_key varchar(255) not null,
                bibtex_entry_type varchar(50) not null default 'article',
                bibtex_fields_json json not null default '{}',
                read_status varchar(50) not null default 'unread',
                tags_json json not null default '[]',
                notes text,
                is_deleted boolean not null default 0,
                created_at datetime not null default current_timestamp,
                updated_at datetime not null default current_timestamp
            )
            """
        )
    )
    await test_session.execute(
        text(
            """
            create table provenance_links (
                id varchar(36) primary key,
                workspace_id varchar(36) not null,
                source_id varchar(36),
                source_anchor_id varchar(36),
                target_domain varchar(64) not null,
                target_kind varchar(64) not null,
                target_id varchar(100),
                target_ref_json json not null default '{}',
                relation_kind varchar(64) not null,
                citation_key varchar(255),
                claim_text text,
                generated_text text,
                review_item_id varchar(36),
                execution_id varchar(36),
                metadata_json json not null default '{}',
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
    from src.dataservice.prism_api import PrismDataService
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
    await db.flush()
    await PrismDataService(db, autocommit=False).ensure_latex_primary_project(
        workspace_id="ws-1",
        title="Explicit Manuscript",
        latex_project_id="latex-explicit",
        main_file="main.tex",
    )
    await db.commit()

    project = await WorkspacePrismService(dataservice=_DbBackedDataServiceClient(db)).get_primary_project(
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

    project = await WorkspacePrismService(dataservice=_DbBackedDataServiceClient(db)).get_primary_project(
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

    project = await WorkspacePrismService(dataservice=_DbBackedDataServiceClient(db)).ensure_primary_project(
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

    service = WorkspaceLatexProjectService(dataservice=_DbBackedDataServiceClient(db))
    service.sync_project = AsyncMock(side_effect=AssertionError("unexpected sync"))  # type: ignore[method-assign]

    project = await service.ensure_workspace_project(workspace_id=workspace.id)

    assert str(project.id) == "latex-explicit"


@pytest.mark.asyncio
async def test_pending_file_change_records_canonical_source_links_from_citations(
    db: AsyncSession,
    user: SimpleNamespace,
    workspace: SimpleNamespace,
) -> None:
    from src.dataservice.prism_review_api import PrismReviewDataService

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
            insert into sources (
                id, workspace_id, source_kind, title, normalized_title,
                authors_json, ingest_kind, library_status, evidence_level,
                fulltext_status, citation_key, bibtex_entry_type,
                bibtex_fields_json, read_status, tags_json, is_deleted
            )
            values
                (
                    'source-1', :workspace_id, 'paper', 'Doe 2026', 'doe 2026',
                    '[]', 'manual', 'core', 'metadata_only', 'none',
                    'doe2026', 'article', '{}', 'unread', '[]', 0
                ),
                (
                    'source-deleted', :workspace_id, 'paper', 'Deleted 2026',
                    'deleted 2026', '[]', 'manual', 'core', 'metadata_only',
                    'none', 'deleted2026', 'article', '{}', 'unread', '[]', 1
                )
            """
        ),
        {"workspace_id": workspace.id},
    )
    await db.commit()

    review_item = await PrismReviewDataService(db).upsert_pending_file_change(
        workspace_id=workspace.id,
        latex_project_id=str(project.id),
        logical_key="section:intro",
        path="sections/intro.tex",
        reason="feature_proposal",
        pending_content=r"Grounded claim \cite{doe2026,missing2026,deleted2026}.",
        pending_hash="hash-new",
        current_hash="hash-old",
        source_execution_id="exec-1",
        source_task_id="task-1",
        academic_style_contract={
            "schema": "wenjin.prism.academic_style_contract.v1",
            "target_path": "sections/intro.tex",
            "basis": "member_self_check",
            "risk": "low",
            "academic_style_score": 4,
            "signals": ["citation_grounding", "formal_register"],
            "anti_patterns": [],
            "raw_before": "As an AI, this section is very good.",
            "style_delta": {
                "schema": "wenjin.prism.academic_style_delta.v1",
                "baseline_academic_style_score": 1,
                "raw_after": "Generated section",
            },
        },
    )

    assert review_item.payload_json["academic_style_contract"] == {
        "schema": "wenjin.prism.academic_style_contract.v1",
        "target_path": "sections/intro.tex",
        "basis": "member_self_check",
        "risk": "low",
        "academic_style_score": 4,
        "signals": ["citation_grounding", "formal_register"],
        "anti_patterns": [],
        "style_delta": {
            "schema": "wenjin.prism.academic_style_delta.v1",
            "baseline_academic_style_score": 1,
        },
    }
    assert "raw_before" not in review_item.payload_json["academic_style_contract"]
    assert "raw_after" not in review_item.payload_json["academic_style_contract"]["style_delta"]
    assert review_item.preview_json["academic_style_contract"] == review_item.payload_json[
        "academic_style_contract"
    ]

    result = await db.execute(
        text(
            """
            select review_item_id, source_id, target_ref_json, citation_key,
                   relation_kind, metadata_json
            from provenance_links
            order by source_id
            """
        )
    )
    links = [dict(row) for row in result.mappings().all()]
    for link in links:
        link["target_ref_json"] = json.loads(str(link["target_ref_json"]))
        link["metadata_json"] = json.loads(str(link["metadata_json"]))
    assert links == [
        {
            "review_item_id": str(review_item.id),
            "source_id": "source-1",
            "target_ref_json": {
                "latex_project_id": "latex-source-links",
                "logical_key": "section:intro",
                "file_path": "sections/intro.tex",
            },
            "citation_key": "doe2026",
            "relation_kind": "cited",
            "metadata_json": {"usage": "cited", "section_key": "section:intro"},
        }
    ]

    await PrismReviewDataService(db).upsert_pending_file_change(
        workspace_id=workspace.id,
        latex_project_id=str(project.id),
        logical_key="section:intro",
        path="sections/intro.tex",
        reason="feature_proposal",
        pending_content="No citation in this revision.",
        pending_hash="hash-newer",
        current_hash="hash-old",
    )

    count_result = await db.execute(text("select count(*) from provenance_links"))
    assert count_result.scalar_one() == 0


@pytest.mark.asyncio
async def test_manual_protect_records_canonical_protected_section(
    db: AsyncSession,
    workspace: SimpleNamespace,
) -> None:
    from src.dataservice.prism_api import PrismDataService

    surface = await PrismDataService(db, autocommit=False).ensure_latex_primary_project(
        workspace_id=workspace.id,
        title="Protected Manuscript",
        latex_project_id="latex-manual-protect",
        main_file="main.tex",
    )
    await PrismDataService(db, autocommit=False).upsert_latex_protected_scope(
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
            from prism_protected_scopes
            where project_id = :project_id
            """
        ),
        {"project_id": surface.project.id},
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
    from src.dataservice.prism_api import PrismDataService
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
    surface = await PrismDataService(db, autocommit=False).ensure_latex_primary_project(
        workspace_id=workspace.id,
        title="Prism Manuscript",
        latex_project_id="latex-prism",
        main_file="main.tex",
        adapter_metadata_json={
            "latex_project_id": "latex-prism",
            "main_file": "main.tex",
            "source_metadata": {"section_map": {"intro": "sections/intro.tex"}},
        },
    )
    await db.execute(
        text(
            """
            insert into review_batches (
                id, workspace_id, execution_id, source_type, source_id,
                review_kind, status, title, item_count
            )
            values (
                'batch-1', :workspace_id, 'exec-1', 'execution', 'exec-1',
                'prism_file_change', 'pending', 'Prism changes', 1
            )
            """
        ),
        {"workspace_id": workspace.id},
    )
    await db.execute(
        text(
            """
            insert into review_items (
                id, batch_id, workspace_id, source_item_id, item_kind,
                target_domain, target_kind, target_ref_json, title, summary,
                status, payload_json, preview_json
            )
            values (
                'review-1', 'batch-1', :workspace_id, 'section:intro',
                'file_change', 'prism', 'prism_file_change',
                '{"latex_project_id":"latex-prism","logical_key":"section:intro","file_path":"sections/intro.tex"}',
                'Intro rewrite', 'feature_proposal', 'pending',
                :payload_json,
                '{"pending_content":"Generated intro"}'
            )
            """
        ),
        {
            "workspace_id": workspace.id,
            "payload_json": json.dumps(
                {
                    "source_execution_id": "exec-1",
                    "source_task_id": "task-1",
                    "path": "sections/intro.tex",
                    "pending_content": "Generated intro",
                    "academic_style_contract": {
                        "schema": "untrusted",
                        "target_path": "sections/intro.tex",
                        "basis": "member_self_check",
                        "risk": "low",
                        "academic_style_score": 4,
                        "signals": ["formal_register"],
                        "anti_patterns": [],
                        "raw_before": "As an AI, this intro is very good.",
                        "style_delta": {
                            "baseline_academic_style_score": 1,
                            "raw_after": "Generated intro",
                        },
                    },
                }
            ),
        },
    )
    await db.execute(
        text(
            """
            insert into provenance_links (
                id, workspace_id, source_id, target_domain, target_kind, target_id,
                target_ref_json, relation_kind, citation_key, claim_text,
                review_item_id, execution_id, metadata_json
            )
            values (
                'source-1', :workspace_id, 'source-lib-1', 'prism',
                'prism_file_change', 'review-1',
                '{"latex_project_id":"latex-prism","logical_key":"section:intro","file_path":"sections/intro.tex"}',
                'cited', 'doe2026', 'key excerpt', 'review-1', 'exec-1',
                '{"usage":"cited","section_key":"section:intro"}'
            )
            """
        ),
        {"workspace_id": workspace.id},
    )
    await db.execute(
        text(
            """
            insert into prism_protected_scopes (
                id, workspace_id, project_id, file_path, section_key,
                scope, reason, source, metadata_json
            )
            values (
                'protected-1', :workspace_id, :project_id, 'sections/intro.tex',
                'section:intro', 'section', 'user_protected', 'review_reject',
                '{}'
            )
            """
        ),
        {"workspace_id": workspace.id, "project_id": surface.project.id},
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

    projection = await WorkspacePrismService(dataservice=_DbBackedDataServiceClient(db)).get_surface_projection(
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
    assert "academic_style_contract" not in projection["file_changes"][0]
    assert projection["review_items"][0]["id"] == "review-1"
    assert projection["review_items"][0]["kind"] == "prism_file_change"
    assert projection["review_items"][0]["target"]["logical_key"] == "section:intro"
    assert projection["review_items"][0]["target"]["file_path"] == "sections/intro.tex"
    style_contract = projection["review_items"][0]["preview"]["academic_style_contract"]
    assert style_contract["schema"] == "wenjin.prism.academic_style_contract.v1"
    assert style_contract["style_delta"] == {
        "schema": "wenjin.prism.academic_style_delta.v1",
        "baseline_academic_style_score": 1,
        "pending_academic_style_score": style_contract["academic_style_score"],
        "score_delta": style_contract["academic_style_score"] - 1,
        "improves_academic_style": style_contract["academic_style_score"] > 1,
    }
    assert "raw_before" not in style_contract
    assert "raw_after" not in style_contract["style_delta"]
    assert {
        action["action"] for action in projection["review_items"][0]["actions"]
    } == {
        "preview_prism_change",
        "apply_prism_change",
        "reject_prism_change",
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

    launch_context = await WorkspacePrismService(dataservice=_DbBackedDataServiceClient(db)).get_launch_context_projection(
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

    report = await WorkspacePrismService(dataservice=_DbBackedDataServiceClient(db)).get_binding_integrity_report(
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
