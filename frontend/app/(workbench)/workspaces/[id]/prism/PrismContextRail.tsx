"use client";

import {
  ArrowUpRight,
  Brain,
  CircleCheckBig,
  FileCheck2,
  History,
  Link2,
  ShieldCheck,
} from "lucide-react";

import type {
  WorkspacePrismSourceLink,
  WorkspacePrismSurfaceResponse,
} from "@/lib/api/types";

function count(value: number | null | undefined): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function displayText(value: string | null | undefined, fallback: string): string {
  const text = value?.trim();
  return text ? text : fallback;
}

function sourceLinkRoom(sourceType: string | null | undefined): string | null {
  const normalized = sourceType?.trim();
  if (normalized === "library" || normalized === "library_item") return "library";
  if (normalized === "document" || normalized === "documents") return "documents";
  return null;
}

function sourceLinkHref(
  workspaceId: string,
  link: WorkspacePrismSourceLink,
): string | null {
  const room = sourceLinkRoom(link.source_type);
  if (!room || !link.source_id) return null;
  const params = new URLSearchParams({
    room,
    item_id: link.source_id,
  });
  return `/workspaces/${workspaceId}?${params.toString()}`;
}

export function PrismContextRail({
  surface,
}: {
  surface: WorkspacePrismSurfaceResponse;
}) {
  const sourceLinks = surface.source_links ?? [];
  const protectedSections = surface.protected_sections ?? [];
  const decisions = surface.decisions ?? [];
  const memoryPreferences = surface.memory_preferences ?? [];
  const recentActivity = surface.recent_activity ?? [];
  const summary = surface.review_summary ?? {};
  const contextSummary = surface.context_summary ?? {};
  const hasContext =
    sourceLinks.length > 0 ||
    protectedSections.length > 0 ||
    decisions.length > 0 ||
    memoryPreferences.length > 0 ||
    recentActivity.length > 0;

  return (
    <aside className="min-h-0 border-t border-white/30 bg-white/55 px-4 py-5 backdrop-blur-xl xl:border-l xl:border-t-0">
      <div className="space-y-5 xl:sticky xl:top-4">
        <section>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--v2-text-secondary)]">
            <FileCheck2 className="h-4 w-4" />
            Review
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <div className="rounded-lg border border-white/45 bg-white/70 px-3 py-2">
              <p className="text-lg font-semibold text-[var(--v2-text-primary)]">
                {count(summary.pending_count)}
              </p>
              <p className="text-[11px] text-[var(--v2-text-secondary)]">待确认</p>
            </div>
            <div className="rounded-lg border border-white/45 bg-white/70 px-3 py-2">
              <p className="text-lg font-semibold text-[var(--v2-text-primary)]">
                {count(summary.applied_count)}
              </p>
              <p className="text-[11px] text-[var(--v2-text-secondary)]">已写入</p>
            </div>
          </div>
        </section>

        <section>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--v2-text-secondary)]">
              <CircleCheckBig className="h-4 w-4" />
              Decisions
            </div>
            <span className="text-xs text-[var(--v2-text-secondary)]">
              {decisions.length}
            </span>
          </div>
          {decisions.length > 0 ? (
            <div className="mt-3 space-y-2">
              {decisions.slice(0, 3).map((item) => (
                <div
                  key={item.id}
                  className="rounded-lg border border-white/45 bg-white/70 px-3 py-2"
                >
                  <p className="truncate text-xs font-medium text-[var(--v2-text-primary)]">
                    {item.key}
                  </p>
                  <p className="mt-1 line-clamp-2 text-[11px] leading-5 text-[var(--v2-text-secondary)]">
                    {item.value}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-3 text-xs leading-5 text-[var(--v2-text-secondary)]">
              暂无稿件决策
            </p>
          )}
        </section>

        <section>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--v2-text-secondary)]">
              <Brain className="h-4 w-4" />
              Memory
            </div>
            <span className="text-xs text-[var(--v2-text-secondary)]">
              {memoryPreferences.length}
            </span>
          </div>
          {memoryPreferences.length > 0 ? (
            <div className="mt-3 space-y-2">
              {memoryPreferences.slice(0, 3).map((item) => (
                <div
                  key={item.id}
                  className="rounded-lg border border-white/45 bg-white/70 px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="truncate text-xs font-medium text-[var(--v2-text-primary)]">
                      {item.category}
                    </p>
                    <span className="shrink-0 text-[10px] text-[var(--v2-text-secondary)]">
                      {count(item.reference_count)} refs
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-[11px] leading-5 text-[var(--v2-text-secondary)]">
                    {item.content}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-3 text-xs leading-5 text-[var(--v2-text-secondary)]">
              暂无写作记忆
            </p>
          )}
        </section>

        <section>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--v2-text-secondary)]">
              <History className="h-4 w-4" />
              Activity
            </div>
            <span className="text-xs text-[var(--v2-text-secondary)]">
              {recentActivity.length}
            </span>
          </div>
          {recentActivity.length > 0 ? (
            <div className="mt-3 space-y-2">
              {recentActivity.slice(0, 3).map((item) => (
                <div
                  key={item.id}
                  className="rounded-lg border border-white/45 bg-white/70 px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="truncate text-xs font-medium text-[var(--v2-text-primary)]">
                      {item.title}
                    </p>
                    <span className="shrink-0 rounded-full bg-[var(--v2-accent-purple-100)] px-2 py-0.5 text-[10px] text-[var(--v2-accent-blue-700)]">
                      {item.status}
                    </span>
                  </div>
                  {item.summary ? (
                    <p className="mt-1 line-clamp-2 text-[11px] leading-5 text-[var(--v2-text-secondary)]">
                      {item.summary}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-3 text-xs leading-5 text-[var(--v2-text-secondary)]">
              暂无稿件活动
            </p>
          )}
        </section>

        <section>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--v2-text-secondary)]">
              <Link2 className="h-4 w-4" />
              Sources
            </div>
            <span className="text-xs text-[var(--v2-text-secondary)]">
              {sourceLinks.length}
            </span>
          </div>
          {sourceLinks.length > 0 ? (
            <div className="mt-3 space-y-2">
              {sourceLinks.slice(0, 5).map((link) => {
                const href = sourceLinkHref(surface.workspace_id, link);
                const body = (
                  <>
                    <div className="flex items-center justify-between gap-3">
                      <p className="truncate text-xs font-medium text-[var(--v2-text-primary)]">
                        {displayText(link.citation_key, link.source_id)}
                      </p>
                      <span className="flex shrink-0 items-center gap-1 rounded-full bg-[var(--v2-accent-purple-100)] px-2 py-0.5 text-[10px] text-[var(--v2-accent-blue-700)]">
                        {link.source_type}
                        {href ? <ArrowUpRight className="h-3 w-3" /> : null}
                      </span>
                    </div>
                    <p className="mt-1 truncate text-[11px] text-[var(--v2-text-secondary)]">
                      {link.file_path}
                    </p>
                    {link.quote ? (
                      <p className="mt-2 line-clamp-2 text-[11px] leading-5 text-[var(--v2-text-secondary)]">
                        {link.quote}
                      </p>
                    ) : null}
                  </>
                );
                const className =
                  "block rounded-lg border border-white/45 bg-white/70 px-3 py-2 transition hover:border-[var(--v2-accent-purple-200)] hover:bg-white/85";
                return href ? (
                  <a key={link.id} href={href} className={className}>
                    {body}
                  </a>
                ) : (
                  <div key={link.id} className={className}>
                    {body}
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="mt-3 text-xs leading-5 text-[var(--v2-text-secondary)]">
              暂无来源绑定
            </p>
          )}
        </section>

        <section>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--v2-text-secondary)]">
              <ShieldCheck className="h-4 w-4" />
              Protected
            </div>
            <span className="text-xs text-[var(--v2-text-secondary)]">
              {protectedSections.length}
            </span>
          </div>
          {protectedSections.length > 0 ? (
            <div className="mt-3 space-y-2">
              {protectedSections.slice(0, 5).map((item) => (
                <div
                  key={item.id}
                  className="rounded-lg border border-white/45 bg-white/70 px-3 py-2"
                >
                  <p className="truncate text-xs font-medium text-[var(--v2-text-primary)]">
                    {item.file_path}
                  </p>
                  <p className="mt-1 truncate text-[11px] text-[var(--v2-text-secondary)]">
                    {displayText(item.section_key, item.scope)}
                  </p>
                  {item.reason ? (
                    <p className="mt-1 text-[11px] text-[var(--v2-text-secondary)]">
                      {item.reason}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-3 text-xs leading-5 text-[var(--v2-text-secondary)]">
              暂无保护段落
            </p>
          )}
        </section>

        {!hasContext ? null : (
          <p className="text-[11px] leading-5 text-[var(--v2-text-secondary)]">
            {count(summary.source_link_count)} 个来源绑定，
            {count(contextSummary.decision_count)} 个决策，
            {count(contextSummary.memory_preference_count)} 条记忆，
            {count(contextSummary.recent_activity_count)} 条活动
          </p>
        )}
      </div>
    </aside>
  );
}
