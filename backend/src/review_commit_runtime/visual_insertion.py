"""Stage reviewed Prism insertions for committed academic visual assets."""

from __future__ import annotations

import hashlib
from difflib import unified_diff
from pathlib import PurePosixPath
from uuid import NAMESPACE_URL, uuid5

from src.contracts.prism_context import (
    PrismContextRef,
    prism_selection_hash,
    split_utf8_selection,
)
from src.contracts.prism_visual_insertion import (
    canonical_visual_asset_path,
    canonical_workspace_asset_url,
    insert_after_prism_selection,
)
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.mission import (
    MissionDerivedReviewItemCreatePayload,
    MissionReviewItemDraftPayload,
    MissionReviewItemPayload,
)

from .membership import MembershipAuthorizer, require_owned_mission

_MAX_INSERTION_FILE_BYTES = 64 * 1024


class PrismVisualInsertionService:
    """Build one hash-bound Prism diff without owning durable state."""

    def __init__(
        self,
        *,
        dataservice: AsyncDataServiceClient,
        membership: MembershipAuthorizer,
    ) -> None:
        self._dataservice = dataservice
        self._missions = dataservice.missions
        self._membership = membership

    async def stage(
        self,
        mission_id: str,
        *,
        actor_user_id: str,
        source_review_item_id: str,
        prism_context_ref: PrismContextRef,
    ) -> MissionReviewItemPayload:
        run = await require_owned_mission(
            self._missions,
            self._membership,
            mission_id=mission_id,
            actor_user_id=actor_user_id,
        )
        if prism_context_ref.workspace_id != run.workspace_id:
            raise PermissionError("Prism selection belongs to a different workspace")
        review_items = await self._missions.list_review_items(mission_id)
        source_item = next(
            (
                item
                for item in review_items
                if item.review_item_id == source_review_item_id
            ),
            None,
        )
        if (
            source_item is None
            or source_item.status.value != "committed"
            or source_item.target_kind != "workspace_asset"
        ):
            raise ValueError("Only a saved academic visual can be inserted into Prism")
        source_commit_result = await self._missions.get_commit_for_review_item(
            mission_id,
            source_review_item_id,
        )
        source_commit = (
            source_commit_result.commit
            if source_commit_result is not None
            and source_commit_result.commit.status.value == "committed"
            else None
        )
        asset_id = str((source_commit.targets_json if source_commit else {}).get("target_ref") or "")
        if source_commit is None or not asset_id:
            raise ValueError("Academic visual has no committed asset receipt")
        asset = await self._dataservice.get_asset(asset_id)
        if (
            asset is None
            or asset.workspace_id != run.workspace_id
            or asset.deleted_at is not None
            or asset.source_kind != "mission_review_item"
            or asset.source_id != source_review_item_id
            or not asset.content_hash
            or not asset.mime_type
        ):
            raise ValueError("Academic visual asset is unavailable or has invalid provenance")

        surface = await self._dataservice.get_prism_surface(run.workspace_id)
        if surface is None or surface.project.id != prism_context_ref.prism_project_id:
            raise ValueError("Prism project is unavailable")
        target = await self._dataservice.get_prism_workspace_file(
            run.workspace_id,
            prism_context_ref.file_id,
        )
        if target is None or target.current_version is None:
            raise ValueError("Prism file is unavailable")
        version = target.current_version
        if (
            version.id != prism_context_ref.base_revision_ref
            or version.content_inline is None
            or not target.file.content_hash
        ):
            raise ValueError("Prism selection is stale; select the placement again")
        content = version.content_inline
        if len(content.encode("utf-8")) > _MAX_INSERTION_FILE_BYTES:
            raise ValueError("Prism file is too large for an inline reviewed insertion")
        start, end = prism_context_ref.selection_byte_range
        _, selection, _ = split_utf8_selection(
            content,
            prism_context_ref.selection_byte_range,
        )
        selection_hash = prism_selection_hash(selection)
        if selection_hash != prism_context_ref.selection_hash:
            raise ValueError("Prism selection changed; select the placement again")

        asset_path = canonical_visual_asset_path(
            content_hash=asset.content_hash,
            mime_type=asset.mime_type,
        )
        asset_url = canonical_workspace_asset_url(
            workspace_id=run.workspace_id,
            storage_path=asset.storage_path,
        )
        caption = _metadata_text(asset.metadata_json, "caption") or asset.title or asset.name
        alt_text = _metadata_text(asset.metadata_json, "alt_text") or caption
        insertion = _build_insertion(
            file_path=target.file.path,
            asset_path=asset_path,
            asset_url=asset_url,
            mime_type=asset.mime_type,
            caption=caption,
            alt_text=alt_text,
            content_hash=asset.content_hash,
        )
        next_content = insert_after_prism_selection(
            content=content,
            selection_byte_range=prism_context_ref.selection_byte_range,
            selection_hash=selection_hash,
            insertion=insertion,
        )
        next_hash = f"sha256:{hashlib.sha256(next_content.encode()).hexdigest()}"
        review_item_id = str(
            uuid5(
                NAMESPACE_URL,
                ":".join(
                    (
                        "wenjin-prism-visual-insertion-v1",
                        mission_id,
                        source_review_item_id,
                        version.id,
                        str(start),
                        str(end),
                    )
                ),
            )
        )
        output_digest = hashlib.sha256(
            f"{source_review_item_id}:{target.file.id}:{start}:{end}".encode()
        ).hexdigest()[:32]
        diff = "\n".join(
            unified_diff(
                content.splitlines(),
                next_content.splitlines(),
                fromfile=target.file.path,
                tofile=target.file.path,
                lineterm="",
                n=3,
            )
        )
        preview_body = (
            f"**将在 `{target.file.path}` 的所选段落后插入学术图：**\n\n"
            f"```diff\n{diff[:16_000]}\n```"
        )
        result = await self._missions.create_derived_review_item(
            mission_id,
            MissionDerivedReviewItemCreatePayload(
                expected_state_version=run.state_version,
                actor_user_id=actor_user_id,
                source_review_item_id=source_review_item_id,
                item=MissionReviewItemDraftPayload(
                    review_item_id=review_item_id,
                    output_key=f"visual-insertion:{output_digest}",
                    target_kind="prism_visual_insertion",
                    target_room="documents",
                    target_ref=f"prism-file:{target.file.id}",
                    base_revision_ref=version.id,
                    base_hash=target.file.content_hash,
                    title=f"插入学术图：{caption}",
                    summary=f"在 {target.file.path} 的所选段落后插入已保存的学术图。",
                    risk_level="medium",
                    review_required_reason="写作台内容变更需要你确认",
                    preview_json={
                        "body": preview_body,
                        "artifact_kind": "prism_visual_insertion",
                        "asset_id": asset.id,
                        "asset_path": asset_path,
                        "caption": caption,
                        "alt_text": alt_text,
                        "selection_byte_range": [start, end],
                        "materialization": {
                            "operation": "documents.insert_visual_asset",
                            "payload": {
                                "prism_project_id": prism_context_ref.prism_project_id,
                                "selection_byte_range": [start, end],
                                "selection_hash": selection_hash,
                                "insertion": insertion,
                                "expected_content_hash": next_hash,
                                "asset_id": asset.id,
                                "source_mission_commit_id": source_commit.commit_id,
                                "metadata_json": {
                                    "asset_path": asset_path,
                                    "caption": caption,
                                    "alt_text": alt_text,
                                    "selection_hash": selection_hash,
                                },
                            },
                        },
                    },
                ),
            ),
        )
        return result.items[0]


def _build_insertion(
    *,
    file_path: str,
    asset_path: str,
    asset_url: str,
    mime_type: str,
    caption: str,
    alt_text: str,
    content_hash: str,
) -> str:
    suffix = PurePosixPath(file_path).suffix.lower()
    if suffix in {".md", ".markdown"}:
        safe_caption = _escape_markdown(caption)
        if mime_type == "application/pdf":
            return f"[{safe_caption}]({asset_url})"
        return f"![{_escape_markdown(alt_text)}]({asset_url})\n\n*{safe_caption}*"
    if suffix == ".tex":
        digest = content_hash.removeprefix("sha256:")[:12]
        return (
            "\\begin{figure}[htbp]\n"
            "  \\centering\n"
            f"  \\includegraphics[width=\\linewidth]{{{asset_path}}}\n"
            f"  \\caption{{{_escape_latex(caption)}}}\n"
            f"  \\label{{fig:wenjin-{digest}}}\n"
            "\\end{figure}"
        )
    raise ValueError("Academic visuals can only be inserted into Markdown or TeX files")


def _metadata_text(metadata: dict, key: str) -> str | None:
    value = metadata.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _escape_markdown(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _escape_latex(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in str(value))


__all__ = ["PrismVisualInsertionService"]
