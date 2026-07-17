"""Domain service for hidden workspace memory documents."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.mission.write_authority import assert_active_mission_write
from src.dataservice.domains.workspace_memory.contracts import (
    WorkspaceMemoryDocumentProjection,
    WorkspaceMemoryMergeCommand,
    WorkspaceMemoryRevisionProjection,
    WorkspaceMemoryRewriteCommand,
    WorkspaceMemoryWriteProjection,
)
from src.dataservice.domains.workspace_memory.models import (
    WorkspaceMemoryDocumentRecord,
    WorkspaceMemoryRevisionRecord,
)
from src.dataservice.domains.workspace_memory.projection import (
    document_to_projection,
    revision_to_projection,
)
from src.dataservice.domains.workspace_memory.repository import WorkspaceMemoryRepository

DEFAULT_WORKSPACE_MEMORY_MARKDOWN = """# Workspace Memory

## Project Context

## User Preferences

## Working Constraints

## Decisions To Preserve

## Open Questions
"""

MAX_WORKSPACE_MEMORY_CHARS = 8000
PROMPT_WORKSPACE_MEMORY_CHARS = 3000

_SECTION_BY_CATEGORY = {
    "preference": "User Preferences",
    "behavior": "User Preferences",
    "goal": "Project Context",
    "context": "Project Context",
    "knowledge": "Project Context",
    "constraint": "Working Constraints",
    "decision": "Decisions To Preserve",
}


def workspace_memory_hash(content: str) -> str:
    return hashlib.sha256(str(content or "").encode("utf-8")).hexdigest()


def normalize_workspace_memory_content(content: str, *, max_chars: int = MAX_WORKSPACE_MEMORY_CHARS) -> str:
    normalized = str(content or "").strip()
    if not normalized:
        normalized = DEFAULT_WORKSPACE_MEMORY_MARKDOWN.strip()
    if len(normalized) > max_chars:
        normalized = normalized[: max_chars - 32].rstrip() + "\n\n- ...\n"
    return normalized


def format_workspace_memory_for_prompt(document: WorkspaceMemoryDocumentProjection | None) -> str:
    if document is None:
        return ""
    content = normalize_workspace_memory_content(
        document.content_markdown,
        max_chars=PROMPT_WORKSPACE_MEMORY_CHARS,
    )
    if not content.strip():
        return ""
    return f"<workspace_memory>\n{content}\n</workspace_memory>"


class WorkspaceMemoryDataDomainService:
    """DataService-owned hidden workspace memory operations."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = WorkspaceMemoryRepository(session)

    async def get_document(self, workspace_id: str) -> WorkspaceMemoryDocumentProjection | None:
        record = await self.repository.get_document(workspace_id)
        return document_to_projection(record) if record else None

    async def ensure_document(
        self,
        *,
        workspace_id: str,
        created_by: str = "system",
    ) -> WorkspaceMemoryDocumentProjection:
        await self.repository.lock_workspace_for_update(workspace_id)
        record = await self.repository.get_document(workspace_id)
        if record is None:
            record, _revision = self._create_document_locked(
                WorkspaceMemoryRewriteCommand(
                    workspace_id=workspace_id,
                    content_markdown=DEFAULT_WORKSPACE_MEMORY_MARKDOWN,
                    update_reason="initialize",
                    updated_by=created_by,
                )
            )
        await self._finish()
        return document_to_projection(record)

    async def rewrite_document(self, command: WorkspaceMemoryRewriteCommand) -> WorkspaceMemoryWriteProjection:
        await self.repository.lock_workspace_for_update(command.workspace_id)
        replayed = await self._replayed_write_records(
            workspace_id=command.workspace_id,
            mission_commit_id=command.source_mission_commit_id,
        )
        if replayed is not None:
            record, revision = replayed
            await self._finish()
            return self._write_projection(
                record=record,
                revision=revision,
                changed=False,
                skipped_reason="mission_commit_replayed",
            )

        record = await self.repository.get_document(command.workspace_id)
        record, revision, changed, skipped_reason = self._rewrite_document_locked(
            command,
            record=record,
        )
        await self._finish()
        return self._write_projection(
            record=record,
            revision=revision,
            changed=changed,
            skipped_reason=skipped_reason,
        )

    async def merge_items(self, command: WorkspaceMemoryMergeCommand) -> WorkspaceMemoryWriteProjection:
        await assert_active_mission_write(
            self.session,
            authority=command.mission_write_authority,
            workspace_id=command.workspace_id,
            mission_id=command.source_mission_id,
            mission_commit_id=command.source_mission_commit_id,
            required=command.source_mission_id is not None,
        )
        await self.repository.lock_workspace_for_update(command.workspace_id)
        replayed = await self._replayed_write_records(
            workspace_id=command.workspace_id,
            mission_commit_id=command.source_mission_commit_id,
        )
        if replayed is not None:
            record, revision = replayed
            await self._finish()
            return self._write_projection(
                record=record,
                revision=revision,
                changed=False,
                skipped_reason="mission_commit_replayed",
            )

        record = await self.repository.get_document(command.workspace_id)
        if record is None:
            record, _revision = self._create_document_locked(
                WorkspaceMemoryRewriteCommand(
                    workspace_id=command.workspace_id,
                    content_markdown=DEFAULT_WORKSPACE_MEMORY_MARKDOWN,
                    update_reason="initialize",
                    updated_by=command.updated_by,
                )
            )

        normalized_items = [item for item in command.items if item.content.strip() and item.confidence >= 0.5]
        if not normalized_items:
            await self._finish()
            return self._write_projection(
                record=record,
                revision=None,
                changed=False,
                skipped_reason="no_items",
            )

        content = record.content_markdown
        for item in normalized_items:
            section = _SECTION_BY_CATEGORY.get(item.category.strip().lower(), "Project Context")
            bullet = f"- {item.content.strip()}"
            content = _append_unique_bullet(content, section=section, bullet=bullet)

        rewrite = WorkspaceMemoryRewriteCommand(
            workspace_id=command.workspace_id,
            content_markdown=content,
            update_reason=command.update_reason,
            updated_by=command.updated_by,
            source_mission_id=command.source_mission_id,
            source_mission_commit_id=command.source_mission_commit_id,
            source_thread_id=command.source_thread_id,
            metadata_json=dict(command.metadata_json or {}),
        )
        record, revision, changed, skipped_reason = self._rewrite_document_locked(
            rewrite,
            record=record,
        )
        await self._finish()
        return self._write_projection(
            record=record,
            revision=revision,
            changed=changed,
            skipped_reason=skipped_reason,
        )

    async def list_revisions(
        self,
        *,
        workspace_id: str,
        limit: int = 20,
    ) -> list[WorkspaceMemoryRevisionProjection]:
        return [
            revision_to_projection(record)
            for record in await self.repository.list_revisions(
                workspace_id=workspace_id,
                limit=limit,
            )
        ]

    async def _finish(self) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()

    def _create_document_locked(
        self,
        command: WorkspaceMemoryRewriteCommand,
    ) -> tuple[WorkspaceMemoryDocumentRecord, WorkspaceMemoryRevisionRecord]:
        content = normalize_workspace_memory_content(command.content_markdown)
        content_hash = workspace_memory_hash(content)
        record = self.repository.create_document(
            {
                "workspace_id": command.workspace_id,
                "content_markdown": content,
                "content_hash": content_hash,
                "revision": 1,
                "updated_by": command.updated_by,
                "source_mission_id": command.source_mission_id,
                "source_mission_commit_id": command.source_mission_commit_id,
                "source_thread_id": command.source_thread_id,
                "metadata_json": dict(command.metadata_json or {}),
            }
        )
        revision = self.repository.create_revision(
            {
                "workspace_id": command.workspace_id,
                "document_id": record.id,
                "revision": 1,
                "content_markdown": content,
                "content_hash": content_hash,
                "update_reason": command.update_reason,
                "source_mission_id": command.source_mission_id,
                "source_mission_commit_id": command.source_mission_commit_id,
                "source_thread_id": command.source_thread_id,
                "created_by": command.updated_by,
            }
        )
        return record, revision

    def _rewrite_document_locked(
        self,
        command: WorkspaceMemoryRewriteCommand,
        *,
        record: WorkspaceMemoryDocumentRecord | None,
    ) -> tuple[
        WorkspaceMemoryDocumentRecord,
        WorkspaceMemoryRevisionRecord | None,
        bool,
        str | None,
    ]:
        next_content = normalize_workspace_memory_content(command.content_markdown)
        next_hash = workspace_memory_hash(next_content)
        if record is None:
            record, revision = self._create_document_locked(command)
            return record, revision, True, None

        if record.content_hash == next_hash:
            return record, None, False, "unchanged"

        next_revision = int(record.revision or 1) + 1
        record.content_markdown = next_content
        record.content_hash = next_hash
        record.revision = next_revision
        record.updated_by = command.updated_by
        record.source_mission_id = command.source_mission_id
        record.source_mission_commit_id = command.source_mission_commit_id
        record.source_thread_id = command.source_thread_id
        record.metadata_json = {
            **dict(record.metadata_json or {}),
            **dict(command.metadata_json or {}),
        }
        record.updated_at = datetime.now(UTC)
        revision = self.repository.create_revision(
            {
                "workspace_id": command.workspace_id,
                "document_id": record.id,
                "revision": next_revision,
                "content_markdown": next_content,
                "content_hash": next_hash,
                "update_reason": command.update_reason,
                "source_mission_id": command.source_mission_id,
                "source_mission_commit_id": command.source_mission_commit_id,
                "source_thread_id": command.source_thread_id,
                "created_by": command.updated_by,
            }
        )
        return record, revision, True, None

    async def _replayed_write_records(
        self,
        *,
        workspace_id: str,
        mission_commit_id: str | None,
    ) -> tuple[WorkspaceMemoryDocumentRecord, WorkspaceMemoryRevisionRecord] | None:
        if mission_commit_id is None:
            return None
        revision = await self.repository.get_revision_by_mission_commit(
            workspace_id=workspace_id,
            mission_commit_id=mission_commit_id,
        )
        if revision is None:
            return None
        document = await self.repository.get_document(workspace_id)
        if document is None:
            raise RuntimeError("memory_revision_lost_document")
        return document, revision

    @staticmethod
    def _write_projection(
        *,
        record: WorkspaceMemoryDocumentRecord,
        revision: WorkspaceMemoryRevisionRecord | None,
        changed: bool,
        skipped_reason: str | None,
    ) -> WorkspaceMemoryWriteProjection:
        return WorkspaceMemoryWriteProjection(
            document=document_to_projection(record),
            revision=revision_to_projection(revision) if revision is not None else None,
            changed=changed,
            skipped_reason=skipped_reason,
        )


def _append_unique_bullet(markdown: str, *, section: str, bullet: str) -> str:
    content = normalize_workspace_memory_content(markdown)
    if bullet in content:
        return content
    lines = content.splitlines()
    header = f"## {section}"
    try:
        header_index = lines.index(header)
    except ValueError:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([header, "", bullet])
        return "\n".join(lines).strip() + "\n"

    insert_at = len(lines)
    for index in range(header_index + 1, len(lines)):
        if lines[index].startswith("## "):
            insert_at = index
            break
    while insert_at > header_index + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    prefix = [] if insert_at > header_index + 1 else [""]
    lines[insert_at:insert_at] = [*prefix, bullet]
    return "\n".join(lines).strip() + "\n"
