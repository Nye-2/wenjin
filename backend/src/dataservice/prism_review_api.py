"""Public DataService API for Prism review items."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.provenance.contracts import ProvenanceLinkCreateCommand
from src.dataservice.domains.review.contracts import (
    ReviewItemPatchCommand,
    ReviewItemProjection,
    ReviewItemTransitionCommand,
)
from src.dataservice.provenance_api import ProvenanceDataService
from src.dataservice.review_api import ReviewDataService
from src.dataservice.source_api import SourceDataService

PRISM_REVIEW_TARGET_DOMAIN = "prism"
PRISM_FILE_CHANGE_TARGET_KIND = "prism_file_change"
PENDING_PRISM_FILE_CHANGE_STATUSES = ("pending", "accepted")
APPLIED_PRISM_FILE_CHANGE_STATUSES = ("applied",)
_SAFE_CITATION_KEY_RE = re.compile(r"^[A-Za-z0-9_:-]+$")
_LATEX_CITE_RE = re.compile(
    r"\\(?:cite|citep|citet|citealp|citealt|parencite|textcite|autocite|supercite)"
    r"(?:\[[^\]]*\])*\{([^}]+)\}"
)


def _json_object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _file_change_target_ref(
    *,
    latex_project_id: str,
    logical_key: str,
    path: str,
) -> dict[str, Any]:
    return {
        "latex_project_id": latex_project_id,
        "logical_key": logical_key,
        "file_path": path,
    }


def _matches_prism_file_change(
    item: ReviewItemProjection,
    *,
    latex_project_id: str,
    logical_key: str,
) -> bool:
    target_ref = _json_object(item.target_ref_json)
    item_logical_key = str(
        target_ref.get("logical_key") or item.source_item_id or item.id
    )
    return (
        str(target_ref.get("latex_project_id") or "") == latex_project_id
        and item_logical_key == logical_key
    )


def _extract_citation_keys_from_text(text: str) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for match in _LATEX_CITE_RE.finditer(str(text or "")):
        for raw_key in match.group(1).split(","):
            key = raw_key.strip()
            if not key or key == "*" or not _SAFE_CITATION_KEY_RE.fullmatch(key):
                continue
            if key in seen:
                continue
            seen.add(key)
            keys.append(key)
    return keys


class PrismReviewDataService:
    """Prism-targeted review operations backed by canonical review_items."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self._session = session
        self._autocommit = autocommit
        self._review = ReviewDataService(session, autocommit=autocommit)

    async def find_file_change(
        self,
        *,
        workspace_id: str,
        latex_project_id: str,
        logical_key: str,
        statuses: tuple[str, ...] | None = None,
        limit: int = 1000,
    ) -> ReviewItemProjection | None:
        items = await self._review.list_items(
            workspace_id=workspace_id,
            target_domain=PRISM_REVIEW_TARGET_DOMAIN,
            target_kind=PRISM_FILE_CHANGE_TARGET_KIND,
            status=list(statuses) if statuses is not None else None,
            limit=limit,
        )
        for item in items:
            if _matches_prism_file_change(
                item,
                latex_project_id=latex_project_id,
                logical_key=logical_key,
            ):
                return item
        return None

    async def upsert_pending_file_change(
        self,
        *,
        workspace_id: str,
        latex_project_id: str,
        logical_key: str,
        path: str,
        reason: str,
        pending_content: str,
        pending_hash: str,
        current_hash: str | None,
        source_execution_id: str | None = None,
        source_task_id: str | None = None,
    ) -> ReviewItemProjection:
        payload_json: dict[str, Any] = {
            "logical_key": logical_key,
            "path": path,
            "reason": reason,
            "pending_content": pending_content,
            "pending_hash": pending_hash,
        }
        if current_hash is not None:
            payload_json["current_hash"] = current_hash
        if source_execution_id:
            payload_json["source_execution_id"] = source_execution_id
        if source_task_id:
            payload_json["source_task_id"] = source_task_id
        preview_json = {"mode": "diff", **payload_json}
        target_ref_json = _file_change_target_ref(
            latex_project_id=latex_project_id,
            logical_key=logical_key,
            path=path,
        )
        existing = await self.find_file_change(
            workspace_id=workspace_id,
            latex_project_id=latex_project_id,
            logical_key=logical_key,
            statuses=PENDING_PRISM_FILE_CHANGE_STATUSES,
        )
        if existing is not None:
            patched = await self._review.patch_item(
                existing.id,
                ReviewItemPatchCommand(
                    source_item_id=logical_key,
                    item_kind="file_change",
                    target_domain=PRISM_REVIEW_TARGET_DOMAIN,
                    target_kind=PRISM_FILE_CHANGE_TARGET_KIND,
                    target_ref_json=target_ref_json,
                    title=path,
                    summary=reason,
                    payload_json=payload_json,
                    preview_json=preview_json,
                    provenance_json={
                        "source_execution_id": source_execution_id,
                        "source_task_id": source_task_id,
                    },
                ),
            )
            if patched is None:
                raise RuntimeError("Canonical Prism review item disappeared during patch")
            await self._sync_citation_provenance_links(
                item_id=patched.id,
                workspace_id=workspace_id,
                latex_project_id=latex_project_id,
                logical_key=logical_key,
                path=path,
                pending_content=pending_content,
                source_execution_id=source_execution_id,
            )
            return patched

        detail = await self._review.create_batch_record(
            workspace_id=workspace_id,
            execution_id=source_execution_id,
            source_type="execution" if source_execution_id else "prism",
            source_id=source_task_id or source_execution_id or logical_key,
            review_kind=PRISM_FILE_CHANGE_TARGET_KIND,
            title="Prism file changes",
            summary="Pending manuscript updates staged for review",
            payload_json={
                "latex_project_id": latex_project_id,
                "target_domain": PRISM_REVIEW_TARGET_DOMAIN,
                "target_kind": PRISM_FILE_CHANGE_TARGET_KIND,
            },
            items=[
                {
                    "source_item_id": logical_key,
                    "item_kind": "file_change",
                    "target_domain": PRISM_REVIEW_TARGET_DOMAIN,
                    "target_kind": PRISM_FILE_CHANGE_TARGET_KIND,
                    "target_ref_json": target_ref_json,
                    "title": path,
                    "summary": reason,
                    "payload_json": payload_json,
                    "preview_json": preview_json,
                    "provenance_json": {
                        "source_execution_id": source_execution_id,
                        "source_task_id": source_task_id,
                    },
                    "sort_order": 0,
                }
            ],
        )
        created = detail.items[0]
        await self._sync_citation_provenance_links(
            item_id=created.id,
            workspace_id=workspace_id,
            latex_project_id=latex_project_id,
            logical_key=logical_key,
            path=path,
            pending_content=pending_content,
            source_execution_id=source_execution_id,
        )
        return created

    async def clear_pending_file_change(
        self,
        *,
        workspace_id: str,
        latex_project_id: str,
        logical_key: str,
    ) -> bool:
        deleted = False
        while True:
            item = await self.find_file_change(
                workspace_id=workspace_id,
                latex_project_id=latex_project_id,
                logical_key=logical_key,
                statuses=PENDING_PRISM_FILE_CHANGE_STATUSES,
            )
            if item is None:
                return deleted
            await self._delete_citation_provenance_links(
                workspace_id=workspace_id,
                review_item_id=item.id,
            )
            deleted = await self._review.delete_item(
                item.id,
                reason="content_already_materialized",
                payload_json={
                    "latex_project_id": latex_project_id,
                    "logical_key": logical_key,
                },
            ) or deleted

    async def _sync_citation_provenance_links(
        self,
        *,
        item_id: str,
        workspace_id: str,
        latex_project_id: str,
        logical_key: str,
        path: str,
        pending_content: str,
        source_execution_id: str | None,
    ) -> None:
        await self._delete_citation_provenance_links(
            workspace_id=workspace_id,
            review_item_id=item_id,
        )
        citation_keys = [
            key
            for key in dict.fromkeys(_extract_citation_keys_from_text(pending_content))
            if key
        ]
        if not citation_keys:
            return

        sources = await SourceDataService(
            self._session,
            autocommit=False,
        ).list_sources_by_citation_keys(
            workspace_id=workspace_id,
            citation_keys=citation_keys,
            include_deleted=False,
            include_excluded=False,
        )
        source_by_key = {
            source.citation_key: source
            for source in sources
            if source.citation_key in citation_keys
        }
        provenance = ProvenanceDataService(self._session, autocommit=self._autocommit)
        for citation_key in citation_keys:
            source = source_by_key.get(citation_key)
            if source is None:
                continue
            await provenance.create_link(
                ProvenanceLinkCreateCommand(
                    workspace_id=workspace_id,
                    source_id=source.id,
                    target_domain=PRISM_REVIEW_TARGET_DOMAIN,
                    target_kind=PRISM_FILE_CHANGE_TARGET_KIND,
                    target_id=item_id,
                    target_ref_json={
                        "latex_project_id": latex_project_id,
                        "logical_key": logical_key,
                        "file_path": path,
                    },
                    relation_kind="cited",
                    citation_key=citation_key,
                    generated_text=pending_content,
                    review_item_id=item_id,
                    execution_id=source_execution_id,
                    metadata_json={
                        "usage": "cited",
                        "section_key": logical_key,
                    },
                )
            )

    async def _delete_citation_provenance_links(
        self,
        *,
        workspace_id: str,
        review_item_id: str,
    ) -> int:
        return await ProvenanceDataService(
            self._session,
            autocommit=self._autocommit,
        ).delete_links(
            workspace_id=workspace_id,
            target_domain=PRISM_REVIEW_TARGET_DOMAIN,
            target_kind=PRISM_FILE_CHANGE_TARGET_KIND,
            review_item_id=review_item_id,
            relation_kind="cited",
        )

    async def mark_applied_file_change(
        self,
        item_id: str,
        *,
        previous_content: str,
        previous_hash: str,
        applied_hash: str,
        revert_signature: str,
    ) -> ReviewItemProjection | None:
        return await self._review.transition_item(
            item_id,
            ReviewItemTransitionCommand(
                status="applied",
                result_json={
                    "previous_content": previous_content,
                    "previous_hash": previous_hash,
                    "applied_hash": applied_hash,
                    "revert_signature": revert_signature,
                },
                payload_json={"action": "apply_prism_file_change"},
            ),
        )

    async def mark_rejected_file_change(
        self,
        item_id: str,
        *,
        reason: str | None = None,
    ) -> ReviewItemProjection | None:
        return await self._review.decide_item(
            item_id,
            status="rejected",
            payload_json={"reason": reason} if reason else {},
        )

    async def mark_reverted_file_change(
        self,
        item_id: str,
    ) -> ReviewItemProjection | None:
        return await self._review.transition_item(
            item_id,
            ReviewItemTransitionCommand(
                status="reverted",
                payload_json={"action": "revert_prism_file_change"},
            ),
        )


__all__ = [
    "APPLIED_PRISM_FILE_CHANGE_STATUSES",
    "PENDING_PRISM_FILE_CHANGE_STATUSES",
    "PRISM_FILE_CHANGE_TARGET_KIND",
    "PRISM_REVIEW_TARGET_DOMAIN",
    "PrismReviewDataService",
]
