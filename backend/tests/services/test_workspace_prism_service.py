"""Tests for workspace Prism surface binding service."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.latex_project import LatexProject
from tests.database.conftest import DbUser, DbWorkspace


def test_workspace_latex_project_service_uses_authoritative_template_packs() -> None:
    from src.services.workspace_latex_projects import WorkspaceLatexProjectService

    assert (
        WorkspaceLatexProjectService._default_template_for_workspace("software_copyright")
        == "software_copyright_cn_application_pack"
    )
    assert (
        WorkspaceLatexProjectService._default_template_for_workspace("math_modeling")
        == "math_modeling_cumcm2026_paper_pack"
    )


def test_workspace_latex_project_service_does_not_reference_legacy_software_template() -> None:
    source = Path("src/services/workspace_latex_projects.py").read_text(encoding="utf-8")
    assert "software_copyright_default" not in source


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
                mission_review_item_id varchar(36),
                mission_commit_id varchar(36),
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
