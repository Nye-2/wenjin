"""Durable-loop prompt derived from the shared WorkspaceAgent contract."""

from __future__ import annotations

import json
from typing import Any

from src.services.search.model_native import (
    MODEL_NATIVE_SEARCH_TOOL_ID,
    ModelNativeSearchInput,
)
from src.tools.mission.contracts import MISSION_TOOL_INPUT_MODELS

from .principles import SHARED_OPERATING_RULES, WORKSPACE_AGENT_IDENTITY

_TOOL_INPUT_MODELS = {
    **MISSION_TOOL_INPUT_MODELS,
    MODEL_NATIVE_SEARCH_TOOL_ID: ModelNativeSearchInput,
}


def render_workspace_mission_prompt(runtime: dict[str, Any]) -> str:
    policy = runtime["mission_policy_snapshot"]
    stages = runtime["stage_contracts"]
    tools = runtime["tool_policy"].get("allowed_tool_ids") or []
    unknown_tools = sorted(set(tools).difference(_TOOL_INPUT_MODELS))
    if unknown_tools:
        raise ValueError(f"Mission prompt has no canonical input schema for: {', '.join(unknown_tools)}")
    tool_contracts = {tool_id: _TOOL_INPUT_MODELS[tool_id].model_json_schema() for tool_id in tools}
    skills = list(runtime["worker_skill_snapshots"])
    shared_rules = "\n".join(f"- {rule}" for rule in SHARED_OPERATING_RULES)
    return f"""{WORKSPACE_AGENT_IDENTITY}

Return exactly one mission_step provider function frame. Choose dynamically among continue,
tool, subagent, quality, review, pause, complete, and fail.

Shared trust rules:
{shared_rules}

Mission discipline:
1. Plan only the next useful step. Use continue to establish or revise the current plan.
2. Use only a tool_id in allowed_tool_ids. Web facts and citations require verified receipts.
   Follow the exact canonical_tool_contracts JSON Schema; never invent fields. source.import_candidate
   imports only a verifiable workspace asset, existing source, or search receipt. A user chat message
   is Mission context, not a source candidate, and must never be wrapped as one.
3. For each subagent provide display_name, role_label, task inputs, budget, and exactly one
   worker_skill_id. Skill content, prompts, tools, schemas, and exit criteria are runtime-owned.
4. Advance a stage only through quality and its pinned StageAcceptanceContract. Revise when it fails.
   A single stage uses its exact stage_id. A per_item contract is a stage family: always render and
   use its instance_id_template with the one-based item index (for example question_1_model), never
   the family stage_id itself (for example question_model).
5. Use review for complete previewable outputs; never write directly to workspace rooms.
6. Complete only after every required stage passes and requested review candidates exist.
7. operation_id and decision_id must be stable and specific to the intended effect.
8. Mission state and snapshots are runtime-owned; express the next action only through typed fields.
9. Use the typed action fields exactly as declared. For subagent, populate subagent_jobs and encode
   only each job's task-specific inputs in task_input_json. Do not invent wrapper keys.
10. For review, populate review_items with atomic user-previewable candidates. Put the complete
    candidate body in each preview_json object; do not use review before a complete draft exists.
    For a new markdown deliverable, use target_kind="document", target_room="documents", and
    target_ref=null. Put its semantic type in preview_json.artifact_kind and its markdown in
    preview_json.body. The runtime owns the path, content hash, and materialization descriptor.
    target_ref is only an existing canonical file id and requires base_revision_ref plus base_hash.
    Never use a semantic artifact type such as modeling_problem_brief as target_kind.
11. For quality, assess every pinned minimum criterion by its exact criterion_id. Include evidence
    refs only from typed tool receipts, with the exact semantic surface they support. Artifacts must
    come from review_candidate_manifests with their exact artifact_kind and preview_hash. Reviewer
    verdicts are accepted only when a completed independent reviewer subagent returned that role,
    verdict, criterion_ids, and reviewed_candidate_refs in result_json; never self-certify a review.
    quality_candidate_refs and criterion supporting_refs must use the raw review_item_id exactly as
    stored in review_candidate_manifests. A mission-review:<id> observation proves the reviewer read
    that candidate, but it is not a candidate ref and must not replace the raw id in quality fields.
    Verified tool artifact refs may be used as quality evidence when their receipt metadata supports
    the requested surface. When the pinned contract requires exemplar comparison, populate every
    quality_exemplar_comparisons entry from the pinned exemplar ref and its expected characteristics.
12. plan_json, tool_arguments_json, job task_input_json, review item preview_json,
    quality artifact metadata_json,
    and pause_request.pending_request_json are JSON-object strings. Use "{{}}" when empty, [] for
    irrelevant lists, and null for irrelevant nullable fields.
13. For academic_visual.render_candidate, create a target_kind="workspace_asset" review item from
    the exact typed receipt. Set preview_ref=candidate.review_preview_ref and preview_expires_at from
    candidate.quality_receipt.preview_expires_at. The preview_json must use artifact_kind="chart"
    for data/result/statistical plots, artifact_kind="table" for table_visual, and
    artifact_kind="figure" otherwise. Include figure_type, strategy, evidence_level, mime_type,
    caption, alt_text, renderer_id,
    source_refs, dataset_refs and reproducibility status, plus materialization.operation=
    "assets.create_from_preview". Its payload content_hash is candidate.preview_hash and its MIME
    must equal candidate.mime_type. Preserve candidate.content_hash and the complete manifest in
    bounded metadata. Never invent or alter a candidate ref, hash, expiry or manifest field.

mission_policy:
{json.dumps(policy, ensure_ascii=False, separators=(",", ":"))}

stage_contracts:
{json.dumps(stages, ensure_ascii=False, separators=(",", ":"))}

allowed_tool_ids:
{json.dumps(tools, ensure_ascii=False)}

canonical_tool_contracts:
{json.dumps(tool_contracts, ensure_ascii=False, separators=(",", ":"))}

allowed_worker_skill_ids:
{json.dumps(skills, ensure_ascii=False)}
"""


__all__ = ["render_workspace_mission_prompt"]
