import { authorizedFetch, readErrorMessage } from "@/lib/api/client";
import type {
  MissionCommitStatus,
  MissionArtifactView,
  MissionEventHint,
  MissionEvidenceView,
  MissionItem,
  MissionPage,
  MissionProjectionPage,
  PrismContextRef,
  MissionReviewDecision,
  MissionReviewItemView,
  MissionReviewPreviewFile,
  MissionReviewMode,
  MissionStageView,
  MissionSubagentView,
  MissionSummary,
  MissionWorkspaceSummary,
  MissionView,
  MissionVisualReviewMetadata,
} from "./mission-types";

const API = "/api";
type Json = Record<string, unknown>;

export interface MissionMutationResult {
  targetMissionId: string;
  issueCodes: string[];
}

export interface MissionVisualInsertionResult {
  targetMissionId: string;
  reviewItemId: string;
}

interface MissionRunWire {
  mission_id: string;
  workspace_id: string;
  thread_id?: string | null;
  title: string;
  objective?: string | null;
  status: MissionView["executionStatus"];
  review_mode: MissionReviewMode;
  active_stage_id?: string | null;
  pending_review_count: number;
  evidence_count: number;
  artifact_count: number;
  active_subagent_count: number;
  state_version: number;
  last_item_seq: number;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  completed_at?: string | null;
}

interface MissionItemWire {
  id: string;
  mission_id: string;
  seq: number;
  item_type: string;
  phase: MissionItem["phase"];
  stage_id?: string | null;
  producer?: string | null;
  summary?: string | null;
  payload_ref?: string | null;
  created_at: string;
}

interface MissionReviewWire {
  review_item_id: string;
  mission_id: string;
  target_kind: string;
  title: string;
  summary?: string | null;
  risk_level: MissionReviewItemView["riskLevel"];
  status: MissionReviewItemView["status"];
  review_required_reason?: string | null;
  preview_json?: Json;
  preview_url?: string | null;
  preview_expires_at?: string | null;
  requires_explicit_review: boolean;
  batch_acceptable: boolean;
  suggested_selected: boolean;
  commit_status?: MissionCommitStatus | null;
  commit_eligible: boolean;
  commit_block_reason?: string | null;
  commit_error_code?: string | null;
  committed_target_ref?: string | null;
}

interface MissionViewWire {
  mission: MissionRunWire;
  activity: {
    state: MissionView["activity"]["state"];
    title: string;
    summary?: string | null;
    attempt?: number | null;
    retry_at?: string | null;
  };
  attention_request: {
    request_id: string;
    reason: string;
    title: string;
    summary: string;
    impact: string;
    required_inputs: Array<{ input_id: string; label: string; description?: string | null; input_type: "text" | "file" | "confirmation" | "credits"; required: boolean }>;
    actions: Array<{
      action_id: string;
      label: string;
      action_type:
        | "reply_in_chat"
        | "upload_file"
        | "open_review"
        | "permission_allow_once"
        | "permission_allow_mission"
        | "permission_reject";
      primary: boolean;
    }>;
  } | null;
  review_summary: {
    pending: number;
    accepted: number;
    needs_more_evidence: number;
    committed: number;
  };
  commit_summary: {
    pending: number;
    applying: number;
    committed: number;
    failed: number;
  };
  review_items: MissionReviewWire[];
  required_stage_ids: string[];
  stage_summaries: Array<{ stage_id: string; title: string; status: MissionStageView["status"]; summary?: string | null }>;
  team_summary?: string | null;
  subagents: Array<{ subagent_id: string; display_name: string; role_label: string; status: MissionSubagentView["status"]; summary?: string | null }>;
  evidence_items: Array<{ item_id: string; seq: number; title: string; source_type: MissionEvidenceView["sourceType"]; source_label?: string | null; summary?: string | null; citation?: string | null; verified: boolean }>;
  evidence_page: { total: number; returned: number; next_cursor?: number | null };
  artifact_items: Array<{ item_id: string; seq: number; title: string; kind: string; summary?: string | null; preview_available: boolean; committed: boolean }>;
  artifact_page: { total: number; returned: number; next_cursor?: number | null };
  review_policy: { mode: MissionReviewMode; protected_outputs_require_confirmation: boolean; draft_outputs_may_be_automatic: boolean };
  review_selection_revision: string;
  quality_highlights: string[];
  refresh_token: string;
}

interface MissionMutationWire {
  outcomes: Array<{
    review_item_id: string;
    applied?: boolean;
    committed?: boolean;
    reason_code?: string | null;
  }>;
  continuation_mission_id?: string | null;
  continuation_error_code?: string | null;
}

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) throw new Error(await readErrorMessage(response, fallback));
  return (await response.json()) as T;
}

function statusLabel(status: MissionRunWire["status"]): string {
  return { created: "准备中", planning: "正在规划", running: "正在研究", waiting: "等待你的回应", completed: "研究已完成", failed: "任务未完整完成", cancelled: "任务已停止" }[status];
}

function durationSeconds(run: MissionRunWire): number | null {
  const start = Date.parse(run.started_at ?? run.created_at);
  const end = Date.parse(run.completed_at ?? run.updated_at);
  return Number.isFinite(start) && Number.isFinite(end) ? Math.max(0, (end - start) / 1000) : null;
}

function missionItem(wire: MissionItemWire): MissionItem {
  return { id: wire.id, missionId: wire.mission_id, seq: wire.seq, itemType: wire.item_type, phase: wire.phase, stageId: wire.stage_id, producer: wire.producer, summary: wire.summary, createdAt: wire.created_at, detailAvailable: Boolean(wire.payload_ref) };
}

function nonemptyString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const label = nonemptyString(item);
    return label ? [label] : [];
  });
}

export function projectMissionVisualReviewMetadata(
  preview: Json | null | undefined,
): MissionVisualReviewMetadata | null {
  if (!preview) return null;
  const artifactKind = nonemptyString(preview.artifact_kind);
  if (artifactKind !== "figure" && artifactKind !== "chart" && artifactKind !== "table") {
    return null;
  }
  const mimeType = nonemptyString(preview.mime_type);
  if (!mimeType || !["image/png", "image/webp", "image/svg+xml", "application/pdf"].includes(mimeType)) {
    return null;
  }

  const reproducibility =
    preview.reproducibility && typeof preview.reproducibility === "object" && !Array.isArray(preview.reproducibility)
      ? preview.reproducibility as Json
      : null;
  const sourceLabels = [
    ...stringList(preview.source_refs),
    ...stringList(preview.dataset_refs),
  ];
  for (const value of [preview.source_label, preview.source, preview.provider_model]) {
    const label = nonemptyString(value);
    if (label) sourceLabels.push(label);
  }

  return {
    artifactKind,
    mimeType,
    figureType: nonemptyString(preview.figure_type),
    strategy: nonemptyString(preview.strategy),
    evidenceLevel: nonemptyString(preview.evidence_level),
    caption: nonemptyString(preview.caption),
    altText: nonemptyString(preview.alt_text),
    rendererId: nonemptyString(preview.renderer_id),
    reproducibilityStatus:
      nonemptyString(preview.reproducibility_status)
      ?? nonemptyString(reproducibility?.status)
      ?? (reproducibility?.reproducible === true
        ? "reproducible"
        : reproducibility?.reproducible === false
          ? "not_reproducible"
          : null),
    sourceLabels: [...new Set(sourceLabels)],
  };
}

function projectView(wire: MissionViewWire): MissionView {
  const run = wire.mission;
  const stages = wire.stage_summaries.map((stage) => ({ id: stage.stage_id, title: stage.title, status: stage.status, summary: stage.summary }));
  const reviewItems = wire.review_items.map((item) => ({
    id: item.review_item_id,
    title: item.title,
    summary: item.summary,
    targetKind: item.target_kind,
    riskLevel: item.risk_level,
    status: item.status,
    suggestedSelected: item.suggested_selected,
    batchAcceptable: item.batch_acceptable,
    requiresExplicitReview: item.requires_explicit_review,
    reasonLabel: item.review_required_reason,
    preview: item.preview_json,
    previewAvailable: Boolean(item.preview_url),
    previewUrl: item.preview_url,
    visual: projectMissionVisualReviewMetadata(item.preview_json),
    commitStatus: item.commit_status ?? null,
    commitEligible: item.commit_eligible,
    commitBlockReason: item.commit_block_reason ?? null,
    commitErrorCode: item.commit_error_code ?? null,
    committedTargetRef: nonemptyString(item.committed_target_ref),
  }));
  const evidenceItems = wire.evidence_items.map((item) => ({ id: item.item_id, title: item.title, sourceType: item.source_type, sourceLabel: item.source_label, summary: item.summary, citation: item.citation, verified: item.verified }));
  const artifactItems = wire.artifact_items.map((item) => ({ id: item.item_id, title: item.title, kind: item.kind, summary: item.summary, previewAvailable: item.preview_available, committed: item.committed }));
  return {
    missionId: run.mission_id,
    workspaceId: run.workspace_id,
    threadId: run.thread_id,
    title: run.title,
    objective: run.objective,
    executionStatus: run.status,
    statusLabel: statusLabel(run.status),
    activity: {
      state: wire.activity.state,
      title: wire.activity.title,
      summary: wire.activity.summary,
      attempt: wire.activity.attempt,
      retryAt: wire.activity.retry_at,
    },
    attentionRequest: wire.attention_request
      ? {
          requestId: wire.attention_request.request_id,
          reason: wire.attention_request.reason,
          title: wire.attention_request.title,
          summary: wire.attention_request.summary,
          impact: wire.attention_request.impact,
          requiredInputs: wire.attention_request.required_inputs.map((item) => ({
            id: item.input_id,
            label: item.label,
            description: item.description,
            inputType: item.input_type,
            required: item.required,
          })),
          actions: wire.attention_request.actions.map((item) => ({
            id: item.action_id,
            label: item.label,
            actionType: item.action_type,
            primary: item.primary,
          })),
        }
      : null,
    createdAt: run.created_at,
    updatedAt: run.updated_at,
    startedAt: run.started_at,
    completedAt: run.completed_at,
    durationSeconds: durationSeconds(run),
    activeStage: stages.find((stage) => stage.id === run.active_stage_id) ?? null,
    stages,
    requiredStageIds: wire.required_stage_ids,
    teamSummary: wire.team_summary,
    subagents: wire.subagents.map((item) => ({ id: item.subagent_id, name: item.display_name, role: item.role_label, status: item.status, summary: item.summary })),
    evidenceItems,
    artifactItems,
    evidenceNextCursor: wire.evidence_page.next_cursor,
    artifactNextCursor: wire.artifact_page.next_cursor,
    evidenceCount: run.evidence_count,
    artifactCount: wire.artifact_page.total,
    reviewItems,
    reviewSummary: { pending: wire.review_summary.pending, needsMoreEvidence: wire.review_summary.needs_more_evidence, accepted: wire.review_summary.accepted, committed: wire.review_summary.committed },
    reviewMode: run.review_mode,
    reviewPolicy: { protectedOutputsRequireConfirmation: wire.review_policy.protected_outputs_require_confirmation, draftOutputsMayBeAutomatic: wire.review_policy.draft_outputs_may_be_automatic },
    reviewSelectionRevision: wire.review_selection_revision,
    commitSummary: wire.commit_summary,
    qualityHighlights: wire.quality_highlights,
    lastItemSeq: run.last_item_seq,
    stateVersion: run.state_version,
    isStale: false,
    loadError: null,
  };
}

export async function listWorkspaceMissions(workspaceId: string, query?: string): Promise<MissionSummary[]> {
  const params = new URLSearchParams({ limit: "100" });
  const response = await authorizedFetch(`${API}/workspaces/${encodeURIComponent(workspaceId)}/missions?${params}`);
  const page = await readJson<{ items: MissionRunWire[]; next_cursor: string | null }>(
    response,
    "研究任务记录加载失败",
  );
  const runs = page.items;
  const needle = query?.trim().toLowerCase();
  return runs
    .filter((run) => !needle || run.title.toLowerCase().includes(needle))
    .map(missionSummary);
}

function missionSummary(run: MissionRunWire): MissionSummary {
  return {
    missionId: run.mission_id,
    title: run.title,
    executionStatus: run.status,
    statusLabel: statusLabel(run.status),
    updatedAt: run.updated_at,
    durationSeconds: durationSeconds(run),
    activeStage: run.active_stage_id,
    pendingReviewCount: run.pending_review_count,
    evidenceCount: run.evidence_count,
    artifactCount: run.artifact_count,
  };
}

export async function getWorkspaceMissionSummary(workspaceId: string): Promise<MissionWorkspaceSummary> {
  const response = await authorizedFetch(
    `${API}/workspaces/${encodeURIComponent(workspaceId)}/missions/summary`,
  );
  const payload = await readJson<{
    total: number;
    status_counts: Record<string, number>;
    pending_review_count: number;
    evidence_count: number;
    artifact_count: number;
    latest: MissionRunWire | null;
    active: MissionRunWire | null;
  }>(response, "研究任务概览加载失败");
  return {
    total: payload.total,
    statusCounts: payload.status_counts,
    pendingReviewCount: payload.pending_review_count,
    evidenceCount: payload.evidence_count,
    artifactCount: payload.artifact_count,
    latest: payload.latest ? missionSummary(payload.latest) : null,
    active: payload.active ? missionSummary(payload.active) : null,
  };
}

export async function getMissionView(missionId: string): Promise<MissionView> {
  const response = await authorizedFetch(`${API}/missions/${encodeURIComponent(missionId)}`);
  return projectView(await readJson<MissionViewWire>(response, "研究任务加载失败"));
}

export async function getMissionReviewPreview(options: {
  missionId: string;
  reviewItemId: string;
}): Promise<MissionReviewPreviewFile> {
  const response = await authorizedFetch(
    `${API}/missions/${encodeURIComponent(options.missionId)}/review-items/${encodeURIComponent(options.reviewItemId)}/preview`,
    { headers: { Accept: "image/png, image/webp, image/svg+xml, application/pdf" } },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "视觉预览加载失败"));
  }
  const blob = await response.blob();
  const mimeType = (response.headers.get("Content-Type") ?? blob.type)
    .split(";", 1)[0]
    .trim()
    .toLowerCase();
  return { blob, mimeType };
}

export async function listMissionItems(options: { missionId: string; cursor?: string | null; limit?: number }): Promise<MissionPage<MissionItem>> {
  const params = new URLSearchParams({ limit: String(options.limit ?? 40) });
  if (options.cursor) params.set("cursor", options.cursor);
  const response = await authorizedFetch(`${API}/missions/${encodeURIComponent(options.missionId)}/items?${params}`);
  const payload = await readJson<{ items: MissionItemWire[]; next_cursor: number | null }>(response, "任务轨迹加载失败");
  return { items: payload.items.map(missionItem), nextCursor: payload.next_cursor == null ? null : String(payload.next_cursor) };
}

export async function listMissionEvidence(options: {
  missionId: string;
  cursor: number;
  limit?: number;
}): Promise<MissionProjectionPage<MissionEvidenceView>> {
  const params = new URLSearchParams({ cursor: String(options.cursor), limit: String(options.limit ?? 50) });
  const response = await authorizedFetch(`${API}/missions/${encodeURIComponent(options.missionId)}/evidence?${params}`);
  const payload = await readJson<{
    items: MissionViewWire["evidence_items"];
    page: MissionViewWire["evidence_page"];
  }>(response, "证据加载失败");
  return {
    items: payload.items.map((item) => ({ id: item.item_id, title: item.title, sourceType: item.source_type, sourceLabel: item.source_label, summary: item.summary, citation: item.citation, verified: item.verified })),
    nextCursor: payload.page.next_cursor ?? null,
    total: payload.page.total,
  };
}

export async function listMissionArtifacts(options: {
  missionId: string;
  cursor: number;
  limit?: number;
}): Promise<MissionProjectionPage<MissionArtifactView>> {
  const params = new URLSearchParams({ cursor: String(options.cursor), limit: String(options.limit ?? 50) });
  const response = await authorizedFetch(`${API}/missions/${encodeURIComponent(options.missionId)}/artifacts?${params}`);
  const payload = await readJson<{
    items: MissionViewWire["artifact_items"];
    page: MissionViewWire["artifact_page"];
  }>(response, "成果加载失败");
  return {
    items: payload.items.map((item) => ({ id: item.item_id, title: item.title, kind: item.kind, summary: item.summary, previewAvailable: item.preview_available, committed: item.committed })),
    nextCursor: payload.page.next_cursor ?? null,
    total: payload.page.total,
  };
}

export async function decideMissionReviews(options: { missionId: string; decisions: MissionReviewDecision[] }): Promise<MissionMutationResult> {
  const decisions = options.decisions.map((item) => ({ review_item_id: item.reviewItemId, action: item.decision === "accepted" ? "accept" : item.decision === "rejected" ? "reject" : "needs_more_evidence" }));
  const response = await authorizedFetch(`${API}/missions/${encodeURIComponent(options.missionId)}/review-decisions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      decision_id: await missionMutationId("review", options.missionId, decisions),
      decisions,
    }),
  });
  const result = await readJson<MissionMutationWire>(response, "确认结果失败");
  return {
    targetMissionId: result.continuation_mission_id ?? options.missionId,
    issueCodes: [
      ...result.outcomes.flatMap((item) =>
        !item.applied && item.reason_code ? [item.reason_code] : []
      ),
      ...(result.continuation_error_code ? [result.continuation_error_code] : []),
    ],
  };
}

export async function commitMissionReviews(options: { missionId: string; reviewItemIds: string[] }): Promise<MissionMutationResult> {
  const reviewItemIds = [...options.reviewItemIds].sort();
  const response = await authorizedFetch(`${API}/missions/${encodeURIComponent(options.missionId)}/commits`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      request_id: await missionMutationId("commit", options.missionId, reviewItemIds),
      review_item_ids: reviewItemIds,
    }),
  });
  const result = await readJson<MissionMutationWire>(response, "保存结果失败");
  return {
    targetMissionId: result.continuation_mission_id ?? options.missionId,
    issueCodes: [
      ...result.outcomes.flatMap((item) =>
        !item.committed && item.reason_code ? [item.reason_code] : []
      ),
      ...(result.continuation_error_code ? [result.continuation_error_code] : []),
    ],
  };
}

async function missionMutationId(
  kind: "review" | "commit",
  missionId: string,
  payload: unknown,
): Promise<string> {
  const canonical = JSON.stringify({ kind, missionId, payload });
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(canonical),
  );
  const hex = Array.from(new Uint8Array(digest), (value) =>
    value.toString(16).padStart(2, "0")
  ).join("");
  return `${kind}-${hex.slice(0, 40)}`;
}

export async function stageMissionVisualInsertion(options: {
  missionId: string;
  sourceReviewItemId: string;
  prismContextRef: PrismContextRef;
}): Promise<MissionVisualInsertionResult> {
  const response = await authorizedFetch(
    `${API}/missions/${encodeURIComponent(options.missionId)}/visual-insertions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_review_item_id: options.sourceReviewItemId,
        prism_context_ref: options.prismContextRef,
      }),
    },
  );
  const result = await readJson<{ review_item_id: string }>(
    response,
    "学术图插入预览生成失败",
  );
  return { targetMissionId: options.missionId, reviewItemId: result.review_item_id };
}

export async function updateMissionReviewMode(missionId: string, reviewMode: MissionReviewMode): Promise<MissionMutationResult> {
  const response = await authorizedFetch(`${API}/missions/${encodeURIComponent(missionId)}/actions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "set_review_mode", review_mode: reviewMode }) });
  await readJson<MissionRunWire>(response, "确认方式更新失败");
  return { targetMissionId: missionId, issueCodes: [] };
}

export async function resolveMissionPermission(options: {
  missionId: string;
  requestId: string;
  decision: "allow_once" | "allow_for_mission" | "reject";
}): Promise<void> {
  const response = await authorizedFetch(
    `${API}/missions/${encodeURIComponent(options.missionId)}/permissions/${encodeURIComponent(options.requestId)}/resolve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision: options.decision, input_json: {} }),
    },
  );
  await readJson(response, "权限确认失败");
}

export function subscribeMissionEvents(options: { workspaceId: string; cursor?: string; onEvent(event: MissionEventHint): void; onReconnect(): void; onError?(message: string): void }): () => void {
  const controller = new AbortController();
  let cursor = options.cursor;
  const wait = (milliseconds: number) => new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, milliseconds);
    controller.signal.addEventListener("abort", () => { clearTimeout(timer); resolve(); }, { once: true });
  });
  void (async () => {
    let attempt = 0;
    while (!controller.signal.aborted) {
      try {
        const params = new URLSearchParams();
        if (cursor) params.set("cursor", cursor);
        const suffix = params.size ? `?${params}` : "";
        const response = await authorizedFetch(`${API}/workspaces/${encodeURIComponent(options.workspaceId)}/missions/events${suffix}`, { signal: controller.signal });
        if (response.status === 401) {
          options.onError?.("登录状态已失效，请重新登录后刷新任务。");
          break;
        }
        if (!response.ok || !response.body) throw new Error("mission stream unavailable");
        attempt = 0;
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!controller.signal.aborted) {
          const { value, done } = await reader.read();
          if (done) throw new Error("mission stream closed");
          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split("\n\n");
          buffer = frames.pop() ?? "";
          for (const frame of frames) {
            const data = frame.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
            if (!data) continue;
            const event = JSON.parse(data) as MissionEventHint;
            cursor = event.cursor;
            options.onEvent(event);
          }
        }
      } catch {
        if (controller.signal.aborted) break;
        options.onReconnect();
        const backoff = Math.min(30_000, 500 * 2 ** attempt);
        attempt += 1;
        await wait(backoff + Math.floor(Math.random() * Math.max(1, backoff / 4)));
      }
    }
  })();
  return () => controller.abort();
}
