"use client";

import { CheckCircle2, FileText, BookOpen, Shield } from "lucide-react";
import {
  BlockActionButtons,
  readArray,
  readNumberValue,
  readStringValue,
  type BlockActionType,
} from "./shared";
import type { ThreadMessageBlock } from "@/lib/api";
import type { BlockActionItem } from "./shared";

export function TaskResultBlock({
  block,
  onAction,
}: {
  block: ThreadMessageBlock;
  onAction?: (
    action: BlockActionType,
    featureId: string | null,
    routeParams?: Record<string, unknown> | null
  ) => void;
}) {
  const data = block.data ?? {};
  const featureId =
    typeof data.feature_id === "string" ? data.feature_id : null;
  const summary = typeof data.summary === "string" ? data.summary : null;
  const destinations = readArray(data.destinations);
  const prism =
    data.prism && typeof data.prism === "object"
      ? (data.prism as Record<string, unknown>)
      : null;
  const trust =
    data.trust && typeof data.trust === "object"
      ? (data.trust as Record<string, unknown>)
      : null;
  const referenceImport =
    data.reference_import && typeof data.reference_import === "object"
      ? (data.reference_import as Record<string, unknown>)
      : null;

  const projectId = readStringValue(prism?.project_id);
  const prismUrl = readStringValue(prism?.url);
  const pendingFileChanges =
    typeof prism?.pending_file_changes === "number"
      ? prism.pending_file_changes
      : 0;
  const appliedFileChanges =
    typeof prism?.applied_file_changes === "number"
      ? prism.applied_file_changes
      : 0;
  const compileStatus = readStringValue(prism?.compile_status);
  const verifiedPapersCount = readNumberValue(trust?.verified_papers_count);
  const unverifiedLeadsCount = readNumberValue(trust?.unverified_leads_count);
  const evidenceSource = readStringValue(trust?.evidence_source);
  const retrievalStatus = readStringValue(trust?.retrieval_status);
  const verifiedAt = readStringValue(trust?.verified_at);
  const verifiedPreview = readArray(trust?.verified_papers_preview).filter(
    (item): item is Record<string, unknown> =>
      Boolean(item) && typeof item === "object" && !Array.isArray(item)
  );
  const importArtifactIds = readArray(referenceImport?.artifact_ids).filter(
    (item): item is string => typeof item === "string" && item.trim().length > 0
  );
  const importSource =
    readStringValue(referenceImport?.source) || "literature_search";

  const actions: BlockActionItem[] = [];

  if (importArtifactIds.length > 0) {
    actions.push({
      label:
        verifiedPapersCount && verifiedPapersCount > 0
          ? `同步 ${verifiedPapersCount} 篇到参考库`
          : "同步到参考库",
      action: "import_references",
      featureId,
      routeParams: {
        source: importSource,
        artifact_ids: importArtifactIds,
      },
    });
  }

  if (projectId || prismUrl) {
    if (pendingFileChanges > 0) {
      actions.push({
        label: `预览待确认修改（${pendingFileChanges}）`,
        action: "preview_prism_changes",
        featureId,
        routeParams: {
          project_id: projectId,
          url: prismUrl,
        },
      });
    }
    actions.push({
      label:
        pendingFileChanges > 0
          ? "打开主稿"
          : "打开主稿",
      action: "open_prism",
      featureId,
      routeParams: {
        project_id: projectId,
        url: prismUrl,
      },
    });
  }

  if (featureId) {
    actions.push({
      label: "继续追问结果",
      action: "continue_thread",
      featureId,
    });
  }

  return (
    <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/8 px-3 py-3">
      <div className="flex items-start gap-2">
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600">
          <CheckCircle2 className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-[var(--text-primary)]">
            {block.title || "任务已完成"}
          </p>
          {summary ? (
            <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
              {summary}
            </p>
          ) : null}
        </div>
      </div>

      {destinations.length > 0 ? (
        <div className="mt-3 space-y-1.5">
          {destinations.map((dest, i) => {
            const kind = readStringValue(
              (dest as Record<string, unknown>)?.kind
            );
            const label = readStringValue(
              (dest as Record<string, unknown>)?.label
            );
            if (!label) return null;
            return (
              <div
                key={i}
                className="flex items-center gap-2 rounded-lg bg-white/60 px-2.5 py-1.5"
              >
                {kind === "prism_file_change" || kind === "prism" ? (
                  <BookOpen className="h-3.5 w-3.5 text-compute-cyan" />
                ) : (
                  <FileText className="h-3.5 w-3.5 text-[var(--text-muted)]" />
                )}
                <span className="text-xs text-[var(--text-secondary)]">
                  {label}
                </span>
              </div>
            );
          })}
        </div>
      ) : null}

      {pendingFileChanges > 0 ? (
        <div className="mt-2 rounded-lg border border-compute-gold/20 bg-compute-gold/8 px-2.5 py-1.5">
          <p className="text-xs font-medium text-compute-gold">
            主稿有待确认写入 {pendingFileChanges} 处
          </p>
          <p className="mt-0.5 text-[11px] text-compute-gold/80">
            进入 WenjinPrism 预览后再决定是否应用到主稿。
          </p>
        </div>
      ) : null}

      {compileStatus ? (
        <div className="mt-2 rounded-lg bg-white/60 px-2.5 py-1.5">
          <p className="text-xs text-[var(--text-secondary)]">
            编译状态：
            <span className="font-medium text-[var(--text-primary)]">
              {compileStatus === "blocked_by_review"
                ? "待审核"
                : compileStatus === "compile_failed"
                  ? "失败"
                  : compileStatus === "ready"
                    ? "就绪"
                    : compileStatus}
            </span>
            {appliedFileChanges > 0 ? ` · 已写入 ${appliedFileChanges} 处` : ""}
          </p>
        </div>
      ) : null}

      {evidenceSource || verifiedPapersCount !== null ? (
        <div className="mt-2 rounded-lg border border-sky-500/15 bg-sky-500/8 px-2.5 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-full bg-white/70 px-2 py-0.5 text-[10px] font-medium text-sky-700">
              <Shield className="h-3 w-3" />
              {evidenceSource || "证据源"} verified
            </span>
            {verifiedPapersCount !== null ? (
              <span className="rounded-full bg-white/70 px-2 py-0.5 text-[10px] text-sky-700">
                已验证论文 {verifiedPapersCount}
              </span>
            ) : null}
            {unverifiedLeadsCount !== null && unverifiedLeadsCount > 0 ? (
              <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-700">
                未验证线索 {unverifiedLeadsCount}
              </span>
            ) : null}
            {retrievalStatus ? (
              <span className="rounded-full bg-white/70 px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
                检索状态 {retrievalStatus}
              </span>
            ) : null}
          </div>
          {verifiedAt ? (
            <p className="mt-1 text-[10px] text-sky-700/70">
              核验时间：{verifiedAt}
            </p>
          ) : null}
          {verifiedPreview.length > 0 ? (
            <div className="mt-2 space-y-1.5">
              {verifiedPreview.slice(0, 3).map((paper, i) => {
                const title = readStringValue(paper.title) || `论文 ${i + 1}`;
                const year = readNumberValue(paper.year);
                const venue = readStringValue(paper.venue);
                const doi = readStringValue(paper.doi);
                const externalId = readStringValue(paper.external_id);
                const citations = readNumberValue(paper.citations_count);
                return (
                  <div key={`${title}-${i}`} className="rounded-md bg-white/60 px-2 py-1.5">
                    <p className="line-clamp-1 text-[11px] font-medium text-[var(--text-primary)]">
                      {title}
                    </p>
                    <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                      {[year, venue, doi ? `DOI ${doi}` : null, externalId ? `S2 ${externalId}` : null, citations !== null ? `引用 ${citations}` : null]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>
      ) : null}

      {trust ? (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {trust.will_not_overwrite_prism ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-white/60 px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
              <Shield className="h-3 w-3" />
              未自动覆盖主稿
            </span>
          ) : null}
          {typeof trust.unverified_items === "number" &&
          trust.unverified_items > 0 ? (
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-600">
              有待核验内容 {String(trust.unverified_items)}
            </span>
          ) : null}
        </div>
      ) : null}

      <BlockActionButtons
        actions={actions}
        onAction={onAction as unknown as Parameters<typeof BlockActionButtons>[0]['onAction']}
      />
    </div>
  );
}
