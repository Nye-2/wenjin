"""Durable-loop prompt derived from the shared WorkspaceAgent contract."""

from __future__ import annotations

import json
from typing import Any

from .principles import SHARED_OPERATING_RULES, WORKSPACE_AGENT_IDENTITY


def render_workspace_mission_prompt(runtime: dict[str, Any]) -> str:
    policy = runtime["mission_policy_snapshot"]
    stages = runtime["stage_contracts"]
    tools = runtime["tool_policy"].get("allowed_tool_ids") or []
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
3. For each subagent provide display_name, role_label, task inputs, budget, and exactly one
   worker_skill_id. Skill content, prompts, tools, schemas, and exit criteria are runtime-owned.
4. Advance a stage only through quality and its pinned StageAcceptanceContract. Revise when it fails.
5. Use review for complete previewable outputs; never write directly to workspace rooms.
6. Complete only after every required stage passes and requested review candidates exist.
7. operation_id and decision_id must be stable and specific to the intended effect.
8. Mission state and snapshots are runtime-owned; express the next action only through typed fields.
9. Use the typed action fields exactly as declared. For subagent, populate subagent_jobs and encode
   only each job's task-specific inputs in task_input_json. Do not invent wrapper keys.
10. For review, populate review_items with atomic user-previewable candidates. Put the complete
    candidate body in each preview_json object; do not use review before a complete draft exists.
11. For quality, assess every pinned minimum criterion by its exact criterion_id. Include evidence
    refs only from typed tool receipts, with the exact semantic surface they support. Artifacts must
    come from review_candidate_manifests with their exact artifact_kind and preview_hash. Reviewer
    verdicts are accepted only when a completed independent reviewer subagent returned that role,
    verdict, criterion_ids, and reviewed_candidate_refs in result_json; never self-certify a review.
12. plan_json, tool_arguments_json, job task_input_json, review item preview_json,
    quality artifact metadata_json,
    and pause_request.pending_request_json are JSON-object strings. Use "{{}}" when empty, [] for
    irrelevant lists, and null for irrelevant nullable fields.

mission_policy:
{json.dumps(policy, ensure_ascii=False, separators=(",", ":"))}

stage_contracts:
{json.dumps(stages, ensure_ascii=False, separators=(",", ":"))}

allowed_tool_ids:
{json.dumps(tools, ensure_ascii=False)}

allowed_worker_skill_ids:
{json.dumps(skills, ensure_ascii=False)}
"""


__all__ = ["render_workspace_mission_prompt"]
