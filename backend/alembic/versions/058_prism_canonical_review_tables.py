"""create canonical Prism review and provenance tables

Revision ID: 058_prism_canonical_review_tables
Revises: 057_workspace_prism_primary_unique
Create Date: 2026-05-20 00:00:00.000000
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "058_prism_canonical_review_tables"
down_revision: str | None = "057_workspace_prism_primary_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _metadata_from_llm_config(llm_config: object) -> dict:
    if not isinstance(llm_config, dict):
        return {}
    metadata = llm_config.get("metadata")
    return deepcopy(metadata) if isinstance(metadata, dict) else {}


def _review_item_from_change(
    *,
    workspace_id: str,
    latex_project_id: str,
    logical_key: str,
    change: dict,
    status: str,
    now: datetime,
) -> dict:
    path = str(change.get("path") or "").strip()
    reason = str(change.get("reason") or "feature_proposal").strip()
    resolved_status = "rejected" if status == "pending" and reason == "user_protected" else status
    preview_payload = dict(change)
    preview_payload.setdefault("mode", "diff")
    return {
        "id": str(uuid4()),
        "workspace_id": workspace_id,
        "latex_project_id": latex_project_id,
        "logical_key": logical_key,
        "source_type": str(change.get("source_type") or "execution"),
        "source_execution_id": change.get("source_execution_id"),
        "source_task_id": change.get("source_task_id"),
        "target_kind": "prism_file_change",
        "target_file_path": path or None,
        "target_room": None,
        "target_item_id": None,
        "title": path or logical_key,
        "summary": reason,
        "status": resolved_status,
        "preview_payload": preview_payload,
        "applied_at": now if resolved_status == "applied" else None,
        "created_at": now,
        "updated_at": now,
    }


def _strip_review_metadata(llm_config: object) -> dict | None:
    if not isinstance(llm_config, dict):
        return None
    next_config = deepcopy(llm_config)
    metadata = next_config.get("metadata")
    if isinstance(metadata, dict):
        metadata.pop("file_changes", None)
        metadata.pop("applied_file_changes", None)
        next_config["metadata"] = metadata
    return next_config


def upgrade() -> None:
    op.create_table(
        "prism_review_items",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("latex_project_id", sa.String(length=36), nullable=False),
        sa.Column("logical_key", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_execution_id", sa.String(length=36), nullable=True),
        sa.Column("source_task_id", sa.String(length=36), nullable=True),
        sa.Column("target_kind", sa.String(length=64), nullable=False),
        sa.Column("target_file_path", sa.String(length=1024), nullable=True),
        sa.Column("target_room", sa.String(length=64), nullable=True),
        sa.Column("target_item_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("preview_payload", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["latex_project_id"], ["latex_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("latex_project_id", "logical_key", name="uq_prism_review_items_project_logical_key"),
    )
    op.create_index("ix_prism_review_items_workspace_status", "prism_review_items", ["workspace_id", "status"], unique=False)
    op.create_index("ix_prism_review_items_project_status", "prism_review_items", ["latex_project_id", "status"], unique=False)
    op.create_index("ix_prism_review_items_source_execution", "prism_review_items", ["source_execution_id"], unique=False)

    op.create_table(
        "prism_source_links",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("latex_project_id", sa.String(length=36), nullable=False),
        sa.Column("review_item_id", sa.String(length=36), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("section_key", sa.String(length=255), server_default="", nullable=False),
        sa.Column("quote", sa.String(length=4000), nullable=True),
        sa.Column("citation_key", sa.String(length=255), nullable=True),
        sa.Column("usage", sa.String(length=64), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["latex_project_id"], ["latex_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_item_id"], ["prism_review_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prism_source_links_workspace", "prism_source_links", ["workspace_id"], unique=False)
    op.create_index("ix_prism_source_links_review_item", "prism_source_links", ["review_item_id"], unique=False)
    op.create_index("ix_prism_source_links_source", "prism_source_links", ["source_type", "source_id"], unique=False)
    op.create_index("ix_prism_source_links_project_file", "prism_source_links", ["latex_project_id", "file_path"], unique=False)

    op.create_table(
        "prism_protected_sections",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("latex_project_id", sa.String(length=36), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("section_key", sa.String(length=255), server_default="", nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["latex_project_id"], ["latex_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("latex_project_id", "file_path", "section_key", "scope", name="uq_prism_protected_sections_scope"),
    )
    op.create_index("ix_prism_protected_sections_workspace", "prism_protected_sections", ["workspace_id"], unique=False)
    op.create_index("ix_prism_protected_sections_project", "prism_protected_sections", ["latex_project_id"], unique=False)

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            select id, workspace_id, llm_config
            from latex_projects
            where workspace_id is not null
              and surface_role = 'primary_manuscript'
              and llm_config is not null
            """
        )
    ).mappings()

    review_items: list[dict] = []
    config_updates: list[dict] = []
    now = _utcnow()
    for row in rows:
        workspace_id = str(row["workspace_id"])
        latex_project_id = str(row["id"])
        llm_config = row["llm_config"]
        metadata = _metadata_from_llm_config(llm_config)

        file_changes = metadata.get("file_changes")
        if isinstance(file_changes, list):
            for index, item in enumerate(file_changes):
                if not isinstance(item, dict):
                    continue
                logical_key = str(item.get("logical_key") or f"change:{index}").strip()
                if not logical_key:
                    continue
                review_items.append(
                    _review_item_from_change(
                        workspace_id=workspace_id,
                        latex_project_id=latex_project_id,
                        logical_key=logical_key,
                        change=item,
                        status="pending",
                        now=now,
                    )
                )

        applied_changes = metadata.get("applied_file_changes")
        if isinstance(applied_changes, dict):
            for logical_key, item in applied_changes.items():
                if not isinstance(item, dict):
                    continue
                review_items.append(
                    _review_item_from_change(
                        workspace_id=workspace_id,
                        latex_project_id=latex_project_id,
                        logical_key=str(logical_key),
                        change={"logical_key": str(logical_key), **item},
                        status="applied",
                        now=now,
                    )
                )

        next_config = _strip_review_metadata(llm_config)
        if next_config is not None:
            config_updates.append(
                {
                    "id": latex_project_id,
                    "llm_config": json.dumps(next_config),
                }
            )

    protected_items = [
        item
        for item in review_items
        if item["status"] == "rejected"
        and isinstance(item.get("preview_payload"), dict)
        and item["preview_payload"].get("reason") == "user_protected"
        and item.get("target_file_path")
    ]

    if review_items:
        insert_items = [
            {
                **item,
                "preview_payload": json.dumps(item["preview_payload"]),
            }
            for item in review_items
        ]
        bind.execute(
            sa.text(
                """
                insert into prism_review_items (
                    id, workspace_id, latex_project_id, logical_key, source_type,
                    source_execution_id, source_task_id, target_kind, target_file_path,
                    target_room, target_item_id, title, summary, status,
                    preview_payload, applied_at, created_at, updated_at
                )
                values (
                    :id, :workspace_id, :latex_project_id, :logical_key, :source_type,
                    :source_execution_id, :source_task_id, :target_kind, :target_file_path,
                    :target_room, :target_item_id, :title, :summary, :status,
                    cast(:preview_payload as jsonb), :applied_at, :created_at, :updated_at
                )
                on conflict (latex_project_id, logical_key) do nothing
                """
            ),
            insert_items,
        )

    for item in protected_items:
        bind.execute(
            sa.text(
                """
                insert into prism_protected_sections (
                    id, workspace_id, latex_project_id, file_path, section_key,
                    scope, reason, source, created_at, updated_at
                )
                values (
                    :id, :workspace_id, :latex_project_id, :file_path, :section_key,
                    :scope, :reason, :source, :created_at, :updated_at
                )
                on conflict (latex_project_id, file_path, section_key, scope) do nothing
                """
            ),
            {
                "id": str(uuid4()),
                "workspace_id": item["workspace_id"],
                "latex_project_id": item["latex_project_id"],
                "file_path": item["target_file_path"],
                "section_key": item["logical_key"],
                "scope": "section",
                "reason": item["summary"],
                "source": "migration",
                "created_at": now,
                "updated_at": now,
            },
        )

    for update in config_updates:
        bind.execute(
            sa.text(
                """
                update latex_projects
                set llm_config = cast(:llm_config as jsonb)
                where id = :id
                """
            ),
            update,
        )


def downgrade() -> None:
    op.drop_index("ix_prism_protected_sections_project", table_name="prism_protected_sections")
    op.drop_index("ix_prism_protected_sections_workspace", table_name="prism_protected_sections")
    op.drop_table("prism_protected_sections")
    op.drop_index("ix_prism_source_links_project_file", table_name="prism_source_links")
    op.drop_index("ix_prism_source_links_source", table_name="prism_source_links")
    op.drop_index("ix_prism_source_links_review_item", table_name="prism_source_links")
    op.drop_index("ix_prism_source_links_workspace", table_name="prism_source_links")
    op.drop_table("prism_source_links")
    op.drop_index("ix_prism_review_items_source_execution", table_name="prism_review_items")
    op.drop_index("ix_prism_review_items_project_status", table_name="prism_review_items")
    op.drop_index("ix_prism_review_items_workspace_status", table_name="prism_review_items")
    op.drop_table("prism_review_items")
