"""Migrate legacy data to v2 8-room workspace tables.

Usage:
    cd backend && python -m scripts.migrate_workspace_v2 --dry-run
    cd backend && python -m scripts.migrate_workspace_v2 --commit

This script is idempotent -- running it multiple times is safe.  It will
skip any records that have already been migrated.

Migrations performed:
    1. Threads without a workspace.thread_id link -> new Workspace record
    2. WorkspaceReference -> LibraryItem (reference library room)
    3. Artifact -> DocumentV2 (documents room)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("migrate_workspace_v2")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


@dataclass
class MigrationResult:
    """Counts from a migration run."""

    workspaces_migrated: int = 0
    library_items_migrated: int = 0
    documents_migrated: int = 0
    skipped_existing: int = 0
    errors: list[str] = field(default_factory=list)


@runtime_checkable
class _HasId(Protocol):
    id: Any


@runtime_checkable
class _ThreadLike(Protocol):
    id: Any
    user_id: Any
    title: Any


@runtime_checkable
class _WorkspaceLike(Protocol):
    id: Any
    user_id: Any
    name: Any
    type: Any
    thread_id: Any


# ---------------------------------------------------------------------------
# Migration helpers
# ---------------------------------------------------------------------------


async def _migrate_workspaces(
    session: AsyncSession,
    result: MigrationResult,
    *,
    Thread: type,
    Workspace: type,
) -> None:
    """Find threads without a workspace.thread_id link and create a workspace."""
    # Find thread IDs that are already linked as workspace.thread_id
    linked_thread_ids: set[str] = set()
    linked_q = await session.execute(select(Workspace.thread_id))
    for (tid,) in linked_q.all():
        if tid is not None:
            linked_thread_ids.add(tid)

    # Find all threads
    all_threads_q = await session.execute(select(Thread))
    all_threads = list(all_threads_q.scalars())

    for thread in all_threads:
        if thread.id in linked_thread_ids:
            result.skipped_existing += 1
            continue

        ws = Workspace(
            user_id=thread.user_id,
            name=thread.title or "Untitled Workspace",
            type="thesis",
            thread_id=thread.id,
        )
        session.add(ws)
        result.workspaces_migrated += 1


async def _migrate_references_to_library(
    session: AsyncSession,
    result: MigrationResult,
    *,
    WorkspaceReference: type,
    LibraryItem: type,
) -> None:
    """Migrate WorkspaceReference records to LibraryItem."""
    # Check if the WorkspaceReference table exists in this session's metadata
    # by attempting a count query; if it fails, skip silently.
    try:
        refs_q = await session.execute(select(WorkspaceReference))
    except Exception:
        return
    all_refs = list(refs_q.scalars())

    if not all_refs:
        return

    # Build set of already-migrated (workspace_id, title, doi) tuples
    existing_q = await session.execute(select(LibraryItem))
    existing_items = list(existing_q.scalars())
    existing_keys: set[tuple[str, str, str | None]] = set()
    for item in existing_items:
        existing_keys.add((item.workspace_id, item.title, item.doi))

    for ref in all_refs:
        key = (ref.workspace_id, ref.title, ref.doi)
        if key in existing_keys:
            result.skipped_existing += 1
            continue

        lib_item = LibraryItem(
            workspace_id=ref.workspace_id,
            item_type=getattr(ref, "publication_type", None) or "article",
            title=ref.title,
            authors=list(ref.authors) if ref.authors else [],
            year=ref.year,
            venue=ref.venue,
            doi=ref.doi,
            url=ref.url,
            abstract=ref.abstract,
            metadata_json={
                "migrated_from": "workspace_references",
                "source_ref_id": ref.id,
                "source_type": ref.source_type,
                "citation_key": ref.citation_key,
            },
            tags=[],
            cited_in_documents=[],
            added_by="migration_script",
        )
        session.add(lib_item)
        result.library_items_migrated += 1


async def _migrate_artifacts_to_documents(
    session: AsyncSession,
    result: MigrationResult,
    *,
    Artifact: type,
    DocumentV2: type,
) -> None:
    """Migrate Artifact records to DocumentV2."""
    try:
        artifacts_q = await session.execute(select(Artifact))
    except Exception:
        return
    all_artifacts = list(artifacts_q.scalars())

    if not all_artifacts:
        return

    # Build set of already-migrated (workspace_id, name, version) tuples
    existing_q = await session.execute(select(DocumentV2))
    existing_docs = list(existing_q.scalars())
    existing_keys: set[tuple[str, str, int]] = set()
    for doc in existing_docs:
        existing_keys.add((doc.workspace_id, doc.name, doc.version))

    for artifact in all_artifacts:
        doc_name = artifact.title or artifact.type
        key = (artifact.workspace_id, doc_name, artifact.version)
        if key in existing_keys:
            result.skipped_existing += 1
            continue

        doc = DocumentV2(
            workspace_id=artifact.workspace_id,
            name=doc_name,
            kind=_artifact_type_to_kind(artifact.type),
            mime_type=None,
            storage_path=None,
            size_bytes=None,
            version=artifact.version,
            metadata_json={
                "migrated_from": "artifacts",
                "source_artifact_id": artifact.id,
                "artifact_type": artifact.type,
                "artifact_status": artifact.status,
                "created_by_skill": artifact.created_by_skill,
                "content": artifact.content,
            },
            added_by=artifact.created_by_skill or "migration_script",
        )
        session.add(doc)
        result.documents_migrated += 1


def _artifact_type_to_kind(artifact_type: str) -> str:
    """Map artifact type to document kind."""
    mapping = {
        "research_idea": "draft",
        "methodology": "draft",
        "outline": "outline",
        "draft": "draft",
        "figure": "figure",
        "export": "export",
        "upload": "upload",
    }
    return mapping.get(artifact_type, "draft")


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------


async def migrate(
    session: AsyncSession,
    *,
    dry_run: bool = True,
    models: dict[str, type] | None = None,
) -> MigrationResult:
    """Migrate legacy data to v2 8-room tables.

    Args:
        session: Async database session.
        dry_run: If True, rollback after reporting counts.
        models: Optional dict of model classes to use.  When *None* the
            production models from ``src.database.models`` are imported.
            Keys: ``Thread``, ``Workspace``, ``WorkspaceReference``,
            ``LibraryItem``, ``Artifact``, ``DocumentV2``.

    Returns:
        MigrationResult with counts of migrated/skipped records and any errors.
    """
    result = MigrationResult()

    try:
        m = _resolve_models(models)

        await _migrate_workspaces(
            session, result,
            Thread=m["Thread"],
            Workspace=m["Workspace"],
        )
        await _migrate_references_to_library(
            session, result,
            WorkspaceReference=m["WorkspaceReference"],
            LibraryItem=m["LibraryItem"],
        )
        await _migrate_artifacts_to_documents(
            session, result,
            Artifact=m["Artifact"],
            DocumentV2=m["DocumentV2"],
        )

        if dry_run:
            await session.rollback()
        else:
            await session.commit()
    except Exception as e:
        await session.rollback()
        result.errors.append(str(e))
        logger.exception("Migration failed")

    return result


def _resolve_models(models: dict[str, type] | None) -> dict[str, type]:
    """Return model classes, falling back to production models."""
    if models is not None:
        return models

    from src.database.models import (
        Artifact,
        DocumentV2,
        LibraryItem,
        Thread,
        Workspace,
        WorkspaceReference,
    )

    return {
        "Thread": Thread,
        "Workspace": Workspace,
        "WorkspaceReference": WorkspaceReference,
        "LibraryItem": LibraryItem,
        "Artifact": Artifact,
        "DocumentV2": DocumentV2,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate workspace data to v2 schema",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Report without committing (default)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually commit changes",
    )
    return parser.parse_args(argv)


async def _run(dry_run: bool) -> MigrationResult:
    """Run migration using production database session."""
    from src.database.session import async_session_factory

    async with async_session_factory() as session:
        result = await migrate(session, dry_run=dry_run)
        prefix = "[DRY RUN] " if dry_run else ""
        print(f"{prefix}Migration result:")
        print(f"  Workspaces:          {result.workspaces_migrated}")
        print(f"  Library items:       {result.library_items_migrated}")
        print(f"  Documents:           {result.documents_migrated}")
        print(f"  Skipped (existing):  {result.skipped_existing}")
        if result.errors:
            print(f"  Errors:              {result.errors}")
        return result


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    dry_run = not args.commit
    result = asyncio.run(_run(dry_run))
    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
