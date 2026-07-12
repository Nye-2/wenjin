"""replace model flags with probe-backed capability profiles

Revision ID: 087_model_capability_profile
Revises: 086_mission_runtime_cutover
Create Date: 2026-07-10
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "087_model_capability_profile"
down_revision: str | None = "086_mission_runtime_cutover"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROFILE_VERSION = "wenjin.model-capability-profile.v1"
_PROBE_VERSION = "wenjin.model-capability-probe.v1"
_OBSERVED_AT = datetime(2026, 7, 10, tzinfo=UTC)
_OBSERVED_AT_JSON = "2026-07-10T00:00:00Z"


def upgrade() -> None:
    generation_api = postgresql.ENUM(
        "chat_completions",
        "responses",
        name="model_generation_api",
    )
    generation_api.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "model_catalog_entries",
        sa.Column(
            "generation_api",
            generation_api,
            nullable=True,
        ),
    )
    op.add_column(
        "model_catalog_entries",
        sa.Column(
            "capability_profile_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "model_catalog_entries",
        sa.Column(
            "capability_probe_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "model_catalog_entries",
        sa.Column("capability_probe_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "model_catalog_entries",
        sa.Column("capability_observed_at", sa.DateTime(timezone=True), nullable=True),
    )

    model_catalog = sa.table(
        "model_catalog_entries",
        sa.column("model_id", sa.String()),
        sa.column("model_name", sa.String()),
        sa.column("base_url", sa.Text()),
        sa.column("category", sa.String()),
        sa.column("generation_api", generation_api),
        sa.column("capability_profile_json", postgresql.JSONB()),
        sa.column("capability_probe_json", postgresql.JSONB()),
        sa.column("capability_probe_hash", sa.String()),
        sa.column("capability_observed_at", sa.DateTime(timezone=True)),
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(
            model_catalog.c.model_id,
            model_catalog.c.model_name,
            model_catalog.c.base_url,
            model_catalog.c.category,
        )
    ).mappings()
    for row in rows:
        selected_api = "chat_completions" if row["category"] == "llm" else None
        profile, evidence = _assessment(
            model_id=row["model_id"],
            model_name=row["model_name"],
            base_url=row["base_url"],
            generation_api=selected_api,
        )
        bind.execute(
            model_catalog.update()
            .where(model_catalog.c.model_id == row["model_id"])
            .values(
                generation_api=selected_api,
                capability_profile_json=profile,
                capability_probe_json=evidence,
                capability_probe_hash=profile["probe_hash"],
                capability_observed_at=_OBSERVED_AT,
            )
        )

    op.alter_column(
        "model_catalog_entries",
        "capability_probe_hash",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.alter_column(
        "model_catalog_entries",
        "capability_observed_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )

    op.create_check_constraint(
        "ck_model_catalog_generation_api_category",
        "model_catalog_entries",
        "(category = 'image' AND generation_api IS NULL) OR "
        "(category = 'llm' AND generation_api IS NOT NULL)",
    )

    for column_name in (
        "supports_streaming",
        "supports_tools",
        "supports_json_mode",
        "supports_json_schema",
        "supports_vision",
        "supports_reasoning_effort",
        "provider_protocol",
    ):
        op.drop_column("model_catalog_entries", column_name)
    op.execute("DROP TYPE IF EXISTS model_provider_protocol")


def downgrade() -> None:
    raise RuntimeError(
        "087_model_capability_profile is an irreversible development cutover; "
        "reseed the model catalog instead of recreating removed capability flags"
    )


def _assessment(
    *,
    model_id: str,
    model_name: str,
    base_url: str,
    generation_api: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    fingerprint = _endpoint_fingerprint(
        model_name=model_name,
        base_url=base_url,
        generation_api=generation_api,
    )
    is_release_gpt55 = (
        model_id == "gpt-5.5"
        and model_name == "gpt-5.5"
        and base_url.rstrip("/") == "https://api.nainai.love/v1"
        and generation_api == "chat_completions"
    )
    if is_release_gpt55:
        checks = [
            {"name": "structured_tool_calls", "status": "passed", "detail_code": None},
            {"name": "strict_tool_arguments", "status": "passed", "detail_code": None},
            {"name": "streaming_termination", "status": "passed", "detail_code": None},
            {"name": "response_storage_disabled", "status": "passed", "detail_code": None},
            {"name": "reasoning_effort:low", "status": "passed", "detail_code": None},
            {"name": "reasoning_effort:medium", "status": "passed", "detail_code": None},
            {"name": "reasoning_effort:high", "status": "passed", "detail_code": None},
            {"name": "reasoning_effort:xhigh", "status": "passed", "detail_code": None},
            {"name": "native_web_search_call", "status": "passed", "detail_code": None},
            {"name": "search_source_citations", "status": "passed", "detail_code": None},
            {
                "name": "native_web_search_completed_event_boundary",
                "status": "failed",
                "detail_code": _native_search_endpoint_fingerprint(base_url),
            },
        ]
        web_search_api = "responses_web_search"
        search_receipts = ["web_search_call", "annotations_sources"]
        transport = [
            {
                "generation_api": "chat_completions",
                "protocol_conformance": True,
                "detail_code": "clean_done_and_close",
            },
            {
                "generation_api": "responses",
                "protocol_conformance": False,
                "detail_code": "abnormal_close_after_response_completed",
            },
        ]
    else:
        checks = [
            {
                "name": "capability_probe",
                "status": "failed",
                "detail_code": "not_probed",
            }
        ]
        web_search_api = "none"
        search_receipts = []
        transport = []

    evidence = {
        "probe_version": _PROBE_VERSION,
        "model_id": model_id,
        "model_name": model_name,
        "generation_api": generation_api,
        "endpoint_fingerprint": fingerprint,
        "observed_at": _OBSERVED_AT_JSON,
        "checks": checks,
        "web_search_api": web_search_api,
        "search_receipts": search_receipts,
        "transport_observations": transport,
    }
    probe_hash = _canonical_hash(evidence)
    profile = {
        "profile_version": _PROFILE_VERSION,
        "model_id": model_id,
        "generation_api": generation_api,
        "structured_tool_calls": is_release_gpt55,
        "strict_tool_arguments": is_release_gpt55,
        "streaming": is_release_gpt55,
        "reasoning_efforts": ["low", "medium", "high", "xhigh"] if is_release_gpt55 else [],
        "native_web_search": False,
        "web_search_api": "none",
        "search_receipts": [],
        "structured_outputs": False,
        "vision": False,
        "response_storage_disabled": is_release_gpt55,
        "protocol_conformance": is_release_gpt55,
        "transport_observations": transport,
        "observed_at": _OBSERVED_AT_JSON,
        "probe_hash": probe_hash,
        "endpoint_fingerprint": fingerprint,
    }
    return profile, evidence


def _endpoint_fingerprint(
    *,
    model_name: str,
    base_url: str,
    generation_api: str | None,
) -> str:
    return _canonical_hash(
        {
            "base_url": base_url.strip().rstrip("/"),
            "generation_api": generation_api or "none",
            "model_name": model_name.strip(),
        }
    )


def _native_search_endpoint_fingerprint(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return _canonical_hash(
        {
            "completion_boundary": "response.completed",
            "endpoint": f"{normalized}/responses",
            "transport": "sse",
        }
    )


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
