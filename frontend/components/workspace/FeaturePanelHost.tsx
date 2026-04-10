"use client";

import { type ReactNode, useEffect, useMemo, useState } from "react";
import {
  BookOpen,
  Bot,
  CheckCircle2,
  FileText,
  Layers3,
  Search,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  CompileFeatureButton,
  ImportLiteratureButton,
  PanelActionBar,
  PanelSection,
  PanelTabBar,
  SaveArtifactButton,
  TaskRuntimePanel,
} from "@/components/workspace";
import { deleteLatexProject } from "@/lib/api";
import { type Artifact, useWorkspaceStore } from "@/stores/workspace";
import { type FeaturePanelSession, useFeaturePanelStore } from "@/stores/panels";
import { cn } from "@/lib/utils";

interface FeaturePanelHostProps {
  workspaceId: string;
}

interface FeaturePanelRendererProps {
  workspaceId: string;
  session: FeaturePanelSession;
}

function findLatestArtifact(
  artifacts: Artifact[],
  predicate: (artifact: Artifact) => boolean
): Artifact | null {
  const matches = artifacts.filter(predicate);
  matches.sort((left, right) =>
    new Date(right.updated_at || right.created_at).getTime() -
    new Date(left.updated_at || left.created_at).getTime()
  );
  return matches[0] ?? null;
}

function readCompileSourceArtifacts(artifacts: Artifact[]) {
  const compileDraft = findLatestArtifact(
    artifacts,
    (artifact) =>
      artifact.type === "paper_draft" &&
      typeof artifact.content.latex_content === "string"
  );

  if (!compileDraft) {
    return {
      artifact: null,
      latexProjectId: null,
      syncConflicts: [],
      title: "",
      version: 0,
    };
  }

  return {
    artifact: compileDraft,
    kind: "compile_result" as const,
    title: compileDraft.title || "编译结果快照",
    latexProjectId:
      typeof compileDraft.content.latex_project_id === "string"
        ? compileDraft.content.latex_project_id
        : null,
    syncConflicts: Array.isArray(compileDraft.content.sync_conflicts)
      ? compileDraft.content.sync_conflicts
      : [],
    version: Number(compileDraft.version || 1),
  };
}

function readLatestCompileResult(artifacts: Artifact[]) {
  const compileArtifact = findLatestArtifact(
    artifacts,
    (artifact) =>
      artifact.type === "paper_draft" &&
      (typeof artifact.content.compile_status === "string" ||
        typeof artifact.content.pdf_url === "string" ||
        typeof artifact.content.latex_content === "string")
  );

  if (!compileArtifact) {
    return null;
  }

  return {
    artifact: compileArtifact,
    pdfUrl:
      typeof compileArtifact.content.pdf_url === "string"
        ? compileArtifact.content.pdf_url
        : null,
    latexProjectId:
      typeof compileArtifact.content.latex_project_id === "string"
        ? compileArtifact.content.latex_project_id
        : null,
    syncConflicts: Array.isArray(compileArtifact.content.sync_conflicts)
      ? compileArtifact.content.sync_conflicts
      : [],
    compileLogs:
      typeof compileArtifact.content.compile_logs === "string"
        ? compileArtifact.content.compile_logs
        : "",
    pageCount:
      typeof compileArtifact.content.page_count === "number"
        ? compileArtifact.content.page_count
        : null,
    sourceSummary:
      compileArtifact.content.source_summary &&
      typeof compileArtifact.content.source_summary === "object"
        ? (compileArtifact.content.source_summary as Record<string, unknown>)
        : null,
  };
}

function readSyncConflicts(resultData: Record<string, unknown>) {
  return Array.isArray(resultData.sync_conflicts)
    ? resultData.sync_conflicts.filter((item) => typeof item === "object" && item)
    : [];
}

function readLinkedLatexProjectId(resultData: Record<string, unknown>) {
  return typeof resultData.latex_project_id === "string"
    ? resultData.latex_project_id
    : null;
}

function LinkedLatexProjectCard({ projectId }: { projectId: string }) {
  return (
    <PanelSection title="关联 LaTeX 项目" icon={FileText}>
      <div className="flex items-center justify-between rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
        <div>
          <p className="text-xs font-medium text-[var(--text-primary)]">
            已生成可编辑的 LaTeX 项目
          </p>
          <p className="mt-1 text-[11px] text-[var(--text-muted)]">
            项目 ID {projectId.slice(0, 8)}
          </p>
        </div>
        <Link
          href={`/latex/${projectId}`}
          className="rounded-xl border border-[var(--border-default)] bg-white px-3 py-2 text-xs font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-muted)]"
        >
          打开项目
        </Link>
      </div>
    </PanelSection>
  );
}

function SyncConflictNotice({
  conflicts,
}: {
  conflicts: Array<Record<string, unknown>>;
}) {
  if (!conflicts.length) {
    return null;
  }

  return (
    <PanelSection title="同步冲突" icon={X}>
      <div className="space-y-2">
        {conflicts.slice(0, 6).map((item, index) => (
          <div
            key={`sync-conflict-${index}`}
            className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-3 py-3"
          >
            <p className="text-xs font-medium text-amber-800">
              {String(item.path || item.logical_key || "未命名文件")}
            </p>
            <p className="mt-1 text-[11px] leading-5 text-amber-900/80">
              {String(item.reason || "文件已被用户修改，本次同步已跳过覆盖。")}
            </p>
          </div>
        ))}
      </div>
    </PanelSection>
  );
}

function readDeepResearchArtifact(artifacts: Artifact[]) {
  return findLatestArtifact(
    artifacts,
    (artifact) => artifact.type === "deep_research_report"
  );
}

function groupLatestChapterArtifacts(artifacts: Artifact[]) {
  const chapterMap = new Map<string, Artifact>();
  const sorted = [...artifacts]
    .filter((artifact) => artifact.type === "thesis_chapter")
    .sort(
      (left, right) =>
        new Date(right.updated_at || right.created_at).getTime() -
        new Date(left.updated_at || left.created_at).getTime()
    );

  for (const artifact of sorted) {
    const key = String(
      artifact.content.chapter_index ??
      artifact.content.chapter_title ??
      artifact.title ??
      artifact.id
    );
    if (!chapterMap.has(key)) {
      chapterMap.set(key, artifact);
    }
  }

  return Array.from(chapterMap.values()).sort((left, right) => {
    const leftIndex = Number(left.content.chapter_index ?? Number.MAX_SAFE_INTEGER);
    const rightIndex = Number(right.content.chapter_index ?? Number.MAX_SAFE_INTEGER);
    return leftIndex - rightIndex;
  });
}

function PanelStatusBadge({ status }: { status: string }) {
  const tone =
    status === "success"
      ? "bg-emerald-500/12 text-emerald-700"
      : status === "failed"
        ? "bg-red-500/12 text-red-700"
        : "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]";
  return (
    <span className={cn("rounded-full px-2.5 py-1 text-[11px] font-medium", tone)}>
      {status}
    </span>
  );
}

function SessionSwitcher({
  sessions,
  activeSessionId,
  onSelect,
}: {
  sessions: Array<{
    taskId: string;
    title: string;
    status: string;
    updatedAt: string;
  }>;
  activeSessionId: string | null;
  onSelect: (taskId: string) => void;
}) {
  if (sessions.length <= 1) {
    return null;
  }

  return (
    <div className="border-b border-[var(--border-default)] px-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
        近期工作会话
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {sessions.map((session) => (
          <button
            key={session.taskId}
            type="button"
            onClick={() => onSelect(session.taskId)}
            className={cn(
              "rounded-full border px-3 py-1.5 text-left text-[11px] transition-colors",
              activeSessionId === session.taskId
                ? "border-[var(--accent-primary)]/30 bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]"
                : "border-[var(--border-default)] bg-white/78 text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]"
            )}
          >
            <span className="block font-medium">{session.title}</span>
            <span className="block text-[10px] opacity-75">
              {session.status} · {new Date(session.updatedAt).toLocaleTimeString("zh-CN", {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

function EmptyWorkPanel() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-5 text-center">
      <div className="rounded-2xl bg-[var(--bg-surface)] p-3 text-[var(--brand-navy)]">
        <Sparkles className="h-5 w-5" />
      </div>
      <h3 className="mt-4 text-sm font-semibold text-[var(--text-primary)]">
        当前没有进行中的工作面板
      </h3>
      <p className="mt-2 max-w-sm text-xs leading-6 text-[var(--text-secondary)]">
        在 chat 中描述你要推进的任务，问津会先确认需求，再为你启动对应模块。
      </p>
    </div>
  );
}

function SubagentTimeline({
  items,
}: {
  items: Array<{
    id: string;
    subagentType: string | null;
    status: string;
    outputPreview: string | null;
    error: string | null;
    updatedAt: string;
  }>;
}) {
  if (items.length === 0) {
    return null;
  }

  return (
    <section className="rounded-2xl border border-[var(--border-default)] bg-white/76 p-4">
      <div className="mb-3 flex items-center gap-2">
        <Bot className="h-4 w-4 text-[var(--brand-teal)]" />
        <h4 className="text-sm font-medium text-[var(--text-primary)]">子代理协作</h4>
      </div>
      <div className="space-y-2">
        {items.map((item) => (
          <div
            key={item.id}
            className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3"
          >
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs font-medium text-[var(--text-primary)]">
                {item.subagentType?.replace(/_/g, " ") || "subagent"}
              </p>
              <PanelStatusBadge status={item.status} />
            </div>
            <p className="mt-2 text-xs leading-6 text-[var(--text-secondary)]">
              {item.error || item.outputPreview || "正在处理上下文并返回摘要。"}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

function DeepResearchPanel({
  workspaceId,
  session,
}: FeaturePanelRendererProps) {
  const artifacts = useWorkspaceStore((state) => state.artifacts);
  const fetchPapers = useWorkspaceStore((state) => state.fetchPapers);
  const [importMessage, setImportMessage] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"overview" | "papers" | "gaps" | "ideas" | "timeline">("overview");
  const resultData =
    session.result && typeof session.result.data === "object" && session.result.data
      ? (session.result.data as Record<string, unknown>)
      : session.result ?? {};
  const ideas = Array.isArray(resultData.ideas) ? resultData.ideas : [];
  const gaps = Array.isArray(resultData.gaps) ? resultData.gaps : [];
  const recommendedActions = Array.isArray(resultData.recommended_actions)
    ? resultData.recommended_actions
    : [];
  const queryData =
    resultData.query && typeof resultData.query === "object"
      ? (resultData.query as Record<string, unknown>)
      : null;
  const papers =
    resultData.corpus &&
    typeof resultData.corpus === "object" &&
    Array.isArray((resultData.corpus as Record<string, unknown>).top_papers)
      ? ((resultData.corpus as Record<string, unknown>).top_papers as Array<Record<string, unknown>>)
      : [];
  const reportArtifact = useMemo(() => readDeepResearchArtifact(artifacts), [artifacts]);

  return (
    <div className="space-y-4">
      <TaskRuntimePanel
        runtime={session.runtime}
        isRunning={session.status === "running" || session.status === "pending"}
        status={session.message}
        error={session.error}
        title="深度调研工作流"
      />

      <PanelActionBar>
        <ImportLiteratureButton
          workspaceId={workspaceId}
          artifactIds={reportArtifact ? [reportArtifact.id] : []}
          source="deep_research"
          disabled={!reportArtifact}
          onImported={async () => {
            await fetchPapers(workspaceId);
          }}
          onError={setImportMessage}
          onSuccess={setImportMessage}
        />
      </PanelActionBar>

      <PanelTabBar
        tabs={[
          { id: "overview", label: "概览" },
          { id: "papers", label: "文献", count: papers.length },
          { id: "gaps", label: "空白", count: gaps.length },
          { id: "ideas", label: "创意", count: ideas.length },
          { id: "timeline", label: "协作", count: session.subagents.length },
        ]}
        activeTab={activeTab}
        onSelect={(tabId) => setActiveTab(tabId as typeof activeTab)}
      />

      {activeTab === "overview" ? (
        <>
          <PanelSection title="调研概览" icon={Layers3}>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
                <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">主题</p>
                <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">
                  {String(resultData.topic || session.description || "未命名主题")}
                </p>
              </div>
              <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
                <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">检索关键词</p>
                <p className="mt-1 text-sm text-[var(--text-primary)]">
                  {Array.isArray(queryData?.keywords)
                    ? (queryData?.keywords as Array<unknown>).map((item) => String(item)).join("、")
                    : "由问津根据当前上下文自动生成"}
                </p>
              </div>
            </div>
            {reportArtifact ? (
              <p className="mt-3 text-[11px] leading-5 text-[var(--text-muted)]">
                当前工作面基于调研报告「{reportArtifact.title || reportArtifact.id}」。
              </p>
            ) : null}
            {importMessage ? (
              <p className="mt-3 rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-xs text-[var(--text-secondary)]">
                {importMessage}
              </p>
            ) : null}
          </PanelSection>
          {recommendedActions.length > 0 ? (
            <PanelSection title="建议下一步" icon={CheckCircle2}>
              <div className="space-y-2">
                {recommendedActions.slice(0, 4).map((item, index) => {
                  const data = typeof item === "object" && item ? (item as Record<string, unknown>) : null;
                  return (
                    <div
                      key={`recommended-action-${index}`}
                      className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3"
                    >
                      <p className="text-xs font-medium text-[var(--text-primary)]">
                        {String(data?.action || `建议 ${index + 1}`)}
                      </p>
                      <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
                        {String(data?.reason || "")}
                      </p>
                    </div>
                  );
                })}
              </div>
            </PanelSection>
          ) : null}
        </>
      ) : null}

      {activeTab === "papers" ? (
        papers.length > 0 ? (
          <PanelSection title="重点文献" icon={BookOpen}>
            <div className="space-y-2">
              {papers.slice(0, 6).map((paper, index) => (
                <div
                  key={`${paper.title || "paper"}-${index}`}
                  className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3"
                >
                  <p className="text-xs font-medium text-[var(--text-primary)]">
                    {String(paper.title || "Untitled")}
                  </p>
                  <p className="mt-1 text-[10px] text-[var(--text-muted)]">
                    {[paper.year, paper.venue].filter(Boolean).map((item) => String(item)).join(" · ") || "来源元数据待补充"}
                  </p>
                  <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
                    {String(paper.significance || paper.relevance || "")}
                  </p>
                </div>
              ))}
            </div>
          </PanelSection>
        ) : (
          <PanelSection title="重点文献" icon={BookOpen}>
            <p className="text-xs leading-6 text-[var(--text-secondary)]">
              当前还没有重点文献结果。
            </p>
          </PanelSection>
        )
      ) : null}

      {activeTab === "gaps" ? (
        gaps.length > 0 ? (
          <PanelSection title="研究空白" icon={Search}>
            <div className="space-y-2">
              {gaps.slice(0, 5).map((gap, index) => (
                <div
                  key={`gap-${index}`}
                  className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3"
                >
                  <p className="text-xs leading-6 text-[var(--text-secondary)]">
                    {typeof gap === "object" && gap
                      ? String((gap as Record<string, unknown>).description || "未命名空白")
                      : String(gap)}
                  </p>
                </div>
              ))}
            </div>
          </PanelSection>
        ) : (
          <PanelSection title="研究空白" icon={Search}>
            <p className="text-xs leading-6 text-[var(--text-secondary)]">
              当前还没有研究空白结果。
            </p>
          </PanelSection>
        )
      ) : null}

      {activeTab === "ideas" ? (
        ideas.length > 0 ? (
          <PanelSection title="候选创意" icon={Sparkles}>
            <div className="space-y-2">
              {ideas.slice(0, 4).map((idea, index) => {
                const data = typeof idea === "object" && idea ? (idea as Record<string, unknown>) : null;
                return (
                  <div
                    key={`idea-${index}`}
                    className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3"
                  >
                    <p className="text-xs font-medium text-[var(--text-primary)]">
                      {String(data?.title || `研究创意 ${index + 1}`)}
                    </p>
                    <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
                      {String(data?.description || "")}
                    </p>
                  </div>
                );
              })}
            </div>
          </PanelSection>
        ) : (
          <PanelSection title="候选创意" icon={Sparkles}>
            <p className="text-xs leading-6 text-[var(--text-secondary)]">
              当前还没有候选创意结果。
            </p>
          </PanelSection>
        )
      ) : null}

      {activeTab === "timeline" ? <SubagentTimeline items={session.subagents} /> : null}
    </div>
  );
}

function LiteratureSearchPanel({
  workspaceId,
  session,
}: FeaturePanelRendererProps) {
  const artifacts = useWorkspaceStore((state) => state.artifacts);
  const fetchPapers = useWorkspaceStore((state) => state.fetchPapers);
  const [importMessage, setImportMessage] = useState<string | null>(null);
  const resultData =
    session.result && typeof session.result.data === "object" && session.result.data
      ? (session.result.data as Record<string, unknown>)
      : session.result ?? {};
  const topHits = Array.isArray(resultData.top_hits) ? resultData.top_hits : [];
  const searchArtifact = useMemo(
    () =>
      findLatestArtifact(
        artifacts,
        (artifact) => artifact.type === "literature_search_results"
      ),
    [artifacts]
  );

  return (
    <div className="space-y-4">
      <TaskRuntimePanel
        runtime={session.runtime}
        isRunning={session.status === "running" || session.status === "pending"}
        status={session.message}
        error={session.error}
        title="文献检索工作流"
      />

      <PanelActionBar>
        <ImportLiteratureButton
          workspaceId={workspaceId}
          artifactIds={searchArtifact ? [searchArtifact.id] : []}
          source="literature_search"
          disabled={!searchArtifact}
          onImported={async () => {
            await fetchPapers(workspaceId);
          }}
          onError={setImportMessage}
          onSuccess={setImportMessage}
        />
      </PanelActionBar>

      <PanelSection title="检索结果" icon={BookOpen}>
        {importMessage ? (
          <p className="mb-3 rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-xs text-[var(--text-secondary)]">
            {importMessage}
          </p>
        ) : null}
        <div className="space-y-2">
          {topHits.length > 0 ? (
            topHits.slice(0, 8).map((item, index) => {
              const hit = typeof item === "object" && item ? (item as Record<string, unknown>) : null;
              return (
                <div
                  key={`literature-hit-${index}`}
                  className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3"
                >
                  <p className="text-xs font-medium text-[var(--text-primary)]">
                    {String(hit?.title || "Untitled")}
                  </p>
                  <p className="mt-1 text-[10px] text-[var(--text-muted)]">
                    {[hit?.year, hit?.venue].filter(Boolean).map((value) => String(value)).join(" · ") || "来源元数据待补充"}
                  </p>
                  <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
                    {String(hit?.summary || "")}
                  </p>
                </div>
              );
            })
          ) : (
            <p className="text-xs leading-6 text-[var(--text-secondary)]">
              当前还没有可展示的命中文献，问津会在检索完成后把高相关候选整理到这里。
            </p>
          )}
        </div>
      </PanelSection>

      <SubagentTimeline items={session.subagents} />
    </div>
  );
}

function OpeningResearchPanel({
  session,
}: FeaturePanelRendererProps) {
  const resultData =
    session.result && typeof session.result.data === "object" && session.result.data
      ? (session.result.data as Record<string, unknown>)
      : session.result ?? {};
  const sections = Array.isArray(resultData.sections) ? resultData.sections : [];
  const references = Array.isArray(resultData.reference_clues) ? resultData.reference_clues : [];

  return (
    <div className="space-y-4">
      <TaskRuntimePanel
        runtime={session.runtime}
        isRunning={session.status === "running" || session.status === "pending"}
        status={session.message}
        error={session.error}
        title="开题调研工作流"
      />
      <PanelSection title="研究报告概览" icon={Layers3}>
        <div className="grid gap-3 md:grid-cols-3">
          <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
            <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">主题</p>
            <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">
              {String(resultData.topic || "未命名主题")}
            </p>
          </div>
          <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
            <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">报告类型</p>
            <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">
              {String(resultData.report_type || "opening_report")}
            </p>
          </div>
          <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
            <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">文献数量</p>
            <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">
              {String(resultData.literature_count || 0)}
            </p>
          </div>
        </div>
      </PanelSection>
      {sections.length > 0 ? (
        <PanelSection title="章节结构" icon={FileText}>
          <div className="space-y-2">
            {sections.slice(0, 8).map((section, index) => {
              const data = typeof section === "object" && section ? (section as Record<string, unknown>) : null;
              return (
                <div key={`opening-section-${index}`} className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
                  <p className="text-xs font-medium text-[var(--text-primary)]">
                    {String(data?.title || `章节 ${index + 1}`)}
                  </p>
                  <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
                    {String(data?.content || "").slice(0, 260)}
                  </p>
                </div>
              );
            })}
          </div>
        </PanelSection>
      ) : null}
      {references.length > 0 ? (
        <PanelSection title="参考线索" icon={BookOpen}>
          <div className="space-y-2">
            {references.slice(0, 6).map((item, index) => (
              <div key={`opening-reference-${index}`} className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3 text-xs text-[var(--text-secondary)]">
                {String(item)}
              </div>
            ))}
          </div>
        </PanelSection>
      ) : null}
      <SubagentTimeline items={session.subagents} />
    </div>
  );
}

function LiteratureReviewPanel({
  session,
}: FeaturePanelRendererProps) {
  const resultData =
    session.result && typeof session.result.data === "object" && session.result.data
      ? (session.result.data as Record<string, unknown>)
      : session.result ?? {};
  const sections = Array.isArray(resultData.sections) ? resultData.sections : [];
  const keyPapers = Array.isArray(resultData.key_papers) ? resultData.key_papers : [];
  const researchGaps = Array.isArray(resultData.research_gaps) ? resultData.research_gaps : [];
  const nextActions = Array.isArray(resultData.next_actions) ? resultData.next_actions : [];

  return (
    <div className="space-y-4">
      <TaskRuntimePanel
        runtime={session.runtime}
        isRunning={session.status === "running" || session.status === "pending"}
        status={session.message}
        error={session.error}
        title="文献综述工作流"
      />
      <PanelSection title="综述摘要" icon={Layers3}>
        <p className="text-sm leading-7 text-[var(--text-secondary)]">
          {String(resultData.summary || "当前还没有综述摘要，问津会在综述生成后回填到这里。")}
        </p>
      </PanelSection>
      {sections.length > 0 ? (
        <PanelSection title="综述结构" icon={FileText}>
          <div className="space-y-2">
            {sections.slice(0, 8).map((section, index) => {
              const data = typeof section === "object" && section ? (section as Record<string, unknown>) : null;
              return (
                <div key={`review-section-${index}`} className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
                  <p className="text-xs font-medium text-[var(--text-primary)]">
                    {String(data?.title || `章节 ${index + 1}`)}
                  </p>
                  <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
                    {String(data?.content || "").slice(0, 260)}
                  </p>
                </div>
              );
            })}
          </div>
        </PanelSection>
      ) : null}
      {keyPapers.length > 0 ? (
        <PanelSection title="核心文献" icon={BookOpen}>
          <div className="space-y-2">
            {keyPapers.slice(0, 6).map((paper, index) => {
              const data = typeof paper === "object" && paper ? (paper as Record<string, unknown>) : null;
              return (
                <div key={`key-paper-${index}`} className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
                  <p className="text-xs font-medium text-[var(--text-primary)]">
                    {String(data?.title || `核心文献 ${index + 1}`)}
                  </p>
                  <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
                    {String(data?.reason || "")}
                  </p>
                </div>
              );
            })}
          </div>
        </PanelSection>
      ) : null}
      {researchGaps.length > 0 ? (
        <PanelSection title="研究空白" icon={Search}>
          <div className="space-y-2">
            {researchGaps.slice(0, 5).map((gap, index) => (
              <div key={`review-gap-${index}`} className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3 text-xs text-[var(--text-secondary)]">
                {String(gap)}
              </div>
            ))}
          </div>
        </PanelSection>
      ) : null}
      {nextActions.length > 0 ? (
        <PanelSection title="后续动作" icon={CheckCircle2}>
          <div className="space-y-2">
            {nextActions.slice(0, 5).map((item, index) => (
              <div key={`review-next-${index}`} className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3 text-xs text-[var(--text-secondary)]">
                {String(item)}
              </div>
            ))}
          </div>
        </PanelSection>
      ) : null}
      <SubagentTimeline items={session.subagents} />
    </div>
  );
}

function FrameworkOutlinePanel({
  session,
}: FeaturePanelRendererProps) {
  const resultData =
    session.result && typeof session.result.data === "object" && session.result.data
      ? (session.result.data as Record<string, unknown>)
      : session.result ?? {};
  const sections = Array.isArray(resultData.sections) ? resultData.sections : [];
  const keywords = Array.isArray(resultData.keywords) ? resultData.keywords : [];
  const contributions = Array.isArray(resultData.contributions) ? resultData.contributions : [];
  const latexProjectId = readLinkedLatexProjectId(resultData);
  const syncConflicts = readSyncConflicts(resultData);

  return (
    <div className="space-y-4">
      <TaskRuntimePanel
        runtime={session.runtime}
        isRunning={session.status === "running" || session.status === "pending"}
        status={session.message}
        error={session.error}
        title="框架与摘要工作流"
      />
      <PanelSection title="摘要草案" icon={FileText}>
        <p className="text-sm leading-7 text-[var(--text-secondary)]">
          {String(resultData.abstract || "当前还没有摘要草案，问津会在框架生成后回填到这里。")}
        </p>
      </PanelSection>
      {latexProjectId ? <LinkedLatexProjectCard projectId={latexProjectId} /> : null}
      {syncConflicts.length > 0 ? <SyncConflictNotice conflicts={syncConflicts as Array<Record<string, unknown>>} /> : null}
      {keywords.length > 0 ? (
        <PanelSection title="关键词" icon={CheckCircle2}>
          <div className="flex flex-wrap gap-2">
            {keywords.slice(0, 8).map((item, index) => (
              <span key={`keyword-${index}`} className="rounded-full border border-[var(--border-default)] bg-[var(--bg-elevated)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">
                {String(item)}
              </span>
            ))}
          </div>
        </PanelSection>
      ) : null}
      {sections.length > 0 ? (
        <PanelSection title="章节框架" icon={Layers3}>
          <div className="space-y-2">
            {sections.slice(0, 8).map((section, index) => {
              const data = typeof section === "object" && section ? (section as Record<string, unknown>) : null;
              return (
                <div key={`outline-section-${index}`} className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
                  <p className="text-xs font-medium text-[var(--text-primary)]">
                    {String(data?.title || `Section ${index + 1}`)}
                  </p>
                  <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
                    {String(data?.focus || "")}
                  </p>
                </div>
              );
            })}
          </div>
        </PanelSection>
      ) : null}
      {contributions.length > 0 ? (
        <PanelSection title="预期贡献" icon={Sparkles}>
          <div className="space-y-2">
            {contributions.slice(0, 5).map((item, index) => (
              <div key={`contribution-${index}`} className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3 text-xs text-[var(--text-secondary)]">
                {String(item)}
              </div>
            ))}
          </div>
        </PanelSection>
      ) : null}
      <SubagentTimeline items={session.subagents} />
    </div>
  );
}

function ProposalOutlinePanel({
  session,
}: FeaturePanelRendererProps) {
  const resultData =
    session.result && typeof session.result.data === "object" && session.result.data
      ? (session.result.data as Record<string, unknown>)
      : session.result ?? {};
  const sections = Array.isArray(resultData.sections) ? resultData.sections : [];
  const milestones = Array.isArray(resultData.milestones) ? resultData.milestones : [];
  const risks = Array.isArray(resultData.risks) ? resultData.risks : [];
  const latexProjectId = readLinkedLatexProjectId(resultData);
  const syncConflicts = readSyncConflicts(resultData);

  return (
    <div className="space-y-4">
      <TaskRuntimePanel
        runtime={session.runtime}
        isRunning={session.status === "running" || session.status === "pending"}
        status={session.message}
        error={session.error}
        title="申报书大纲工作流"
      />
      <PanelSection title="项目概览" icon={Layers3}>
        <div className="grid gap-3 md:grid-cols-3">
          <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
            <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">主题</p>
            <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">{String(resultData.topic || "未命名项目")}</p>
          </div>
          <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
            <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">类型</p>
            <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">
              {String(resultData.proposal_type_label || resultData.proposal_type || "科研项目")}
            </p>
          </div>
          <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
            <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">周期</p>
            <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">
              {String(resultData.period_months || 24)} 个月
            </p>
          </div>
        </div>
      </PanelSection>
      {latexProjectId ? <LinkedLatexProjectCard projectId={latexProjectId} /> : null}
      {syncConflicts.length > 0 ? <SyncConflictNotice conflicts={syncConflicts as Array<Record<string, unknown>>} /> : null}
      {sections.length > 0 ? (
        <PanelSection title="大纲章节" icon={FileText}>
          <div className="space-y-2">
            {sections.slice(0, 8).map((section, index) => {
              const data = typeof section === "object" && section ? (section as Record<string, unknown>) : null;
              return (
                <div key={`proposal-section-${index}`} className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
                  <p className="text-xs font-medium text-[var(--text-primary)]">{String(data?.title || `章节 ${index + 1}`)}</p>
                  <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
                    {String(data?.content || "").slice(0, 260)}
                  </p>
                </div>
              );
            })}
          </div>
        </PanelSection>
      ) : null}
      {milestones.length > 0 ? (
        <PanelSection title="里程碑" icon={CheckCircle2}>
          <div className="space-y-2">
            {milestones.slice(0, 5).map((milestone, index) => {
              const data = typeof milestone === "object" && milestone ? (milestone as Record<string, unknown>) : null;
              return (
                <div key={`proposal-milestone-${index}`} className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
                  <p className="text-xs font-medium text-[var(--text-primary)]">
                    {String(data?.name || data?.title || `里程碑 ${index + 1}`)}
                  </p>
                  <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
                    {String(data?.description || "")}
                  </p>
                </div>
              );
            })}
          </div>
        </PanelSection>
      ) : null}
      {risks.length > 0 ? (
        <PanelSection title="风险提示" icon={Search}>
          <div className="space-y-2">
            {risks.slice(0, 5).map((risk, index) => (
              <div key={`proposal-risk-${index}`} className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3 text-xs text-[var(--text-secondary)]">
                {typeof risk === "object" && risk ? String((risk as Record<string, unknown>).description || "") : String(risk)}
              </div>
            ))}
          </div>
        </PanelSection>
      ) : null}
      <SubagentTimeline items={session.subagents} />
    </div>
  );
}

function BackgroundResearchPanel({
  session,
}: FeaturePanelRendererProps) {
  const resultData =
    session.result && typeof session.result.data === "object" && session.result.data
      ? (session.result.data as Record<string, unknown>)
      : session.result ?? {};
  const sections = Array.isArray(resultData.sections) ? resultData.sections : [];
  const references = Array.isArray(resultData.references) ? resultData.references : [];
  const latexProjectId = readLinkedLatexProjectId(resultData);
  const syncConflicts = readSyncConflicts(resultData);

  return (
    <div className="space-y-4">
      <TaskRuntimePanel
        runtime={session.runtime}
        isRunning={session.status === "running" || session.status === "pending"}
        status={session.message}
        error={session.error}
        title="背景调研工作流"
      />
      <PanelSection title="调研范围" icon={Layers3}>
        <div className="grid gap-3 md:grid-cols-3">
          <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
            <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">关键词</p>
            <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">{String(resultData.keywords || "未指定主题")}</p>
          </div>
          <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
            <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">行业范围</p>
            <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">{String(resultData.industry_scope || "相关领域")}</p>
          </div>
          <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
            <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">时间范围</p>
            <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">{String(resultData.time_range || "近5年")}</p>
          </div>
        </div>
      </PanelSection>
      {latexProjectId ? <LinkedLatexProjectCard projectId={latexProjectId} /> : null}
      {syncConflicts.length > 0 ? <SyncConflictNotice conflicts={syncConflicts as Array<Record<string, unknown>>} /> : null}
      {sections.length > 0 ? (
        <PanelSection title="调研章节" icon={FileText}>
          <div className="space-y-2">
            {sections.slice(0, 8).map((section, index) => {
              const data = typeof section === "object" && section ? (section as Record<string, unknown>) : null;
              return (
                <div key={`background-section-${index}`} className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
                  <p className="text-xs font-medium text-[var(--text-primary)]">{String(data?.title || `章节 ${index + 1}`)}</p>
                  <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
                    {String(data?.content || "").slice(0, 260)}
                  </p>
                </div>
              );
            })}
          </div>
        </PanelSection>
      ) : null}
      {references.length > 0 ? (
        <PanelSection title="参考文献线索" icon={BookOpen}>
          <div className="space-y-2">
            {references.slice(0, 6).map((reference, index) => {
              const data = typeof reference === "object" && reference ? (reference as Record<string, unknown>) : null;
              return (
                <div key={`background-reference-${index}`} className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
                  <p className="text-xs font-medium text-[var(--text-primary)]">{String(data?.title || `参考 ${index + 1}`)}</p>
                  <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
                    {[data?.authors, data?.year, data?.venue].filter(Boolean).map((value) => String(value)).join(" · ")}
                  </p>
                </div>
              );
            })}
          </div>
        </PanelSection>
      ) : null}
      <SubagentTimeline items={session.subagents} />
    </div>
  );
}

function PaperAnalysisPanel({
  session,
}: FeaturePanelRendererProps) {
  const resultData =
    session.result && typeof session.result.data === "object" && session.result.data
      ? (session.result.data as Record<string, unknown>)
      : session.result ?? {};
  const sections =
    resultData.sections && typeof resultData.sections === "object"
      ? (resultData.sections as Record<string, unknown>)
      : {};
  const qualityAssessment =
    resultData.quality_assessment && typeof resultData.quality_assessment === "object"
      ? (resultData.quality_assessment as Record<string, unknown>)
      : {};
  const recommendations = Array.isArray(resultData.recommendations) ? resultData.recommendations : [];

  return (
    <div className="space-y-4">
      <TaskRuntimePanel
        runtime={session.runtime}
        isRunning={session.status === "running" || session.status === "pending"}
        status={session.message}
        error={session.error}
        title="论文分析工作流"
      />
      <PanelSection title="整体摘要" icon={Layers3}>
        <p className="text-sm leading-7 text-[var(--text-secondary)]">
          {String(resultData.summary || "当前还没有分析摘要，问津会在结构化分析完成后回填到这里。")}
        </p>
      </PanelSection>
      {Object.keys(qualityAssessment).length > 0 ? (
        <PanelSection title="质量评估" icon={CheckCircle2}>
          <div className="grid gap-3 md:grid-cols-3">
            {Object.entries(qualityAssessment).map(([key, value]) => (
              <div key={key} className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
                <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">{key}</p>
                <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">{String(value)}</p>
              </div>
            ))}
          </div>
        </PanelSection>
      ) : null}
      {Object.keys(sections).length > 0 ? (
        <PanelSection title="分析分区" icon={FileText}>
          <div className="space-y-2">
            {Object.entries(sections).map(([key, rawSection]) => {
              const section = rawSection && typeof rawSection === "object" ? (rawSection as Record<string, unknown>) : null;
              return (
                <div key={key} className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
                  <p className="text-xs font-medium text-[var(--text-primary)]">
                    {String(section?.title || key)}
                  </p>
                  <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
                    {String(section?.content || "").slice(0, 260)}
                  </p>
                </div>
              );
            })}
          </div>
        </PanelSection>
      ) : null}
      {recommendations.length > 0 ? (
        <PanelSection title="后续建议" icon={Sparkles}>
          <div className="space-y-2">
            {recommendations.slice(0, 6).map((item, index) => (
              <div key={`analysis-recommendation-${index}`} className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3 text-xs text-[var(--text-secondary)]">
                {String(item)}
              </div>
            ))}
          </div>
        </PanelSection>
      ) : null}
      <SubagentTimeline items={session.subagents} />
    </div>
  );
}

function ThesisWritingPanel({
  workspaceId,
  session,
}: FeaturePanelRendererProps) {
  const artifacts = useWorkspaceStore((state) => state.artifacts);
  const createArtifact = useWorkspaceStore((state) => state.createArtifact);
  const [actionError, setActionError] = useState<string | null>(null);
  const [selectedChapterId, setSelectedChapterId] = useState<string | null>(null);
  const [chapterDraft, setChapterDraft] = useState("");
  const [isSavingChapter, setIsSavingChapter] = useState(false);
  const [activeTab, setActiveTab] = useState<"overview" | "chapters" | "latex" | "preview">("overview");
  const [isCompileLogDialogOpen, setIsCompileLogDialogOpen] = useState(false);
  const [isDeletingLinkedProject, setIsDeletingLinkedProject] = useState(false);
  const [deletedLinkedProjectId, setDeletedLinkedProjectId] = useState<string | null>(null);
  const source = useMemo(() => readCompileSourceArtifacts(artifacts), [artifacts]);
  const latestCompile = useMemo(() => readLatestCompileResult(artifacts), [artifacts]);
  const linkedLatexProjectId =
    source.latexProjectId && source.latexProjectId !== deletedLinkedProjectId
      ? source.latexProjectId
      : null;

  const outlineArtifact = useMemo(
    () => findLatestArtifact(artifacts, (artifact) => artifact.type === "framework_outline"),
    [artifacts]
  );
  const chapterArtifacts = useMemo(() => groupLatestChapterArtifacts(artifacts), [artifacts]);

  useEffect(() => {
    const fallback = chapterArtifacts[0]?.id ?? null;
    setSelectedChapterId((current) =>
      current && chapterArtifacts.some((artifact) => artifact.id === current)
        ? current
        : fallback
    );
  }, [chapterArtifacts]);

  const selectedChapter = useMemo(
    () =>
      selectedChapterId
        ? chapterArtifacts.find((artifact) => artifact.id === selectedChapterId) ?? null
        : null,
    [chapterArtifacts, selectedChapterId]
  );

  useEffect(() => {
    if (!selectedChapter) {
      setChapterDraft((current) => (current === "" ? current : ""));
      return;
    }
    const nextDraft = String(selectedChapter.content.markdown || selectedChapter.content.content || "");
    setChapterDraft((current) => (current === nextDraft ? current : nextDraft));
  }, [selectedChapter]);

  const handleSaveChapter = async () => {
    if (!selectedChapter) {
      setActionError("当前没有可保存的章节草稿。");
      return;
    }
    setActionError(null);
    setIsSavingChapter(true);
    try {
      await createArtifact({
        workspace_id: workspaceId,
        type: "thesis_chapter",
        title:
          selectedChapter.title ||
          String(selectedChapter.content.chapter_title || "章节草稿"),
        content: {
          ...selectedChapter.content,
          markdown: chapterDraft,
        },
        created_by_skill: selectedChapter.created_by_skill ?? undefined,
        parent_artifact_id: selectedChapter.id,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "章节保存失败";
      setActionError(message);
      throw error instanceof Error ? error : new Error(message);
    } finally {
      setIsSavingChapter(false);
    }
  };

  const outline =
    outlineArtifact?.content.outline &&
    typeof outlineArtifact.content.outline === "object"
      ? (outlineArtifact.content.outline as Record<string, unknown>)
      : null;
  const chapters = Array.isArray(outline?.chapters) ? outline.chapters : [];
  const totalDraftChars = chapterArtifacts.reduce(
    (sum, artifact) =>
      sum + String(artifact.content.markdown || artifact.content.content || "").length,
    0
  );

  return (
    <div className="space-y-4">
      <TaskRuntimePanel
        runtime={session.runtime}
        isRunning={session.status === "running" || session.status === "pending"}
        status={session.message}
        error={session.error}
        title="论文写作工作流"
      />
      <PanelTabBar
        tabs={[
          { id: "overview", label: "概览" },
          { id: "chapters", label: "章节", count: chapterArtifacts.length },
          { id: "latex", label: "主稿" },
          { id: "preview", label: "预览" },
        ]}
        activeTab={activeTab}
        onSelect={(tabId) => setActiveTab(tabId as typeof activeTab)}
      />

      {activeTab === "overview" ? (
        <>
          {linkedLatexProjectId ? <LinkedLatexProjectCard projectId={linkedLatexProjectId} /> : null}
          {source.syncConflicts.length > 0 ? (
            <SyncConflictNotice conflicts={source.syncConflicts as Array<Record<string, unknown>>} />
          ) : latestCompile?.syncConflicts && latestCompile.syncConflicts.length > 0 ? (
            <SyncConflictNotice conflicts={latestCompile.syncConflicts as Array<Record<string, unknown>>} />
          ) : null}
          <PanelSection title="主稿概览" icon={Layers3}>
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
                <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">大纲章节</p>
                <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">{chapters.length}</p>
              </div>
              <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
                <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">章节草稿</p>
                <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">{chapterArtifacts.length}</p>
              </div>
              <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
                <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">正文字符</p>
                <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">
                  {totalDraftChars}
                </p>
              </div>
            </div>
            <p className="mt-3 text-[11px] leading-5 text-[var(--text-muted)]">
              {source.artifact
                ? `当前已有 LaTeX 主稿来源：${source.title} · v${source.version}`
                : "当前还没有独立 LaTeX 主稿，编译时会基于现有章节和大纲生成。"}
            </p>
          </PanelSection>

          <PanelSection
            title="论文主稿结构"
            icon={FileText}
            description="章节结构与章节草稿会在这里持续累积，完成后可直接进入编译。"
            actions={
              <CompileFeatureButton
                workspaceId={workspaceId}
                label="编译当前主稿"
                className="border border-[var(--border-default)] bg-[var(--bg-surface)] !text-[var(--text-primary)] hover:bg-[var(--bg-muted)]"
                onError={setActionError}
              />
            }
          >
            {actionError ? (
              <p className="mb-3 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-600">
                {actionError}
              </p>
            ) : null}
            {chapters.length > 0 ? (
              <div className="space-y-2">
                {chapters.slice(0, 8).map((chapter, index) => {
                  const data =
                    typeof chapter === "object" && chapter ? (chapter as Record<string, unknown>) : null;
                  return (
                    <div
                      key={`outline-${index}`}
                      className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3"
                    >
                      <p className="text-xs font-medium text-[var(--text-primary)]">
                        {String(data?.title || `章节 ${index + 1}`)}
                      </p>
                      <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
                        {Array.isArray(data?.keyPoints)
                          ? (data?.keyPoints as Array<unknown>).slice(0, 3).map((item) => String(item)).join("、")
                          : "待补充关键论点"}
                      </p>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-xs leading-6 text-[var(--text-secondary)]">
                当前还没有稳定大纲，问津会先帮助你收敛结构，再进入章节撰写。
              </p>
            )}
          </PanelSection>
        </>
      ) : null}

      {activeTab === "chapters" ? (
        chapterArtifacts.length > 0 ? (
          <PanelSection
            title="章节编辑区"
            icon={FileText}
            actions={
              <SaveArtifactButton
                label="保存章节"
                disabled={!selectedChapter || isSavingChapter}
                onSave={handleSaveChapter}
                onError={setActionError}
              />
            }
          >
            <div className="mb-3 flex flex-wrap gap-2">
              {chapterArtifacts.map((artifact) => (
                <button
                  key={artifact.id}
                  type="button"
                  onClick={() => setSelectedChapterId(artifact.id)}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-[11px] transition-colors",
                    selectedChapterId === artifact.id
                      ? "border-[var(--accent-primary)]/30 bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]"
                      : "border-[var(--border-default)] bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:bg-[var(--bg-muted)]"
                  )}
                >
                  {artifact.title || "章节草稿"}
                </button>
              ))}
            </div>
            {selectedChapter ? (
              <div className="space-y-3">
                <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
                  <p className="text-xs font-medium text-[var(--text-primary)]">
                    {selectedChapter.title || "章节草稿"}
                  </p>
                  <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                    版本 {selectedChapter.version ?? 1} · 保存时会生成新的 artifact 版本，不覆盖历史内容。
                  </p>
                </div>
                <textarea
                  value={chapterDraft}
                  onChange={(event) => setChapterDraft(event.target.value)}
                  className="h-72 w-full rounded-2xl border border-[var(--border-default)] bg-[var(--bg-base)] px-4 py-3 text-sm leading-7 text-[var(--text-primary)] focus:border-[var(--accent-primary)] focus:outline-none"
                  spellCheck={false}
                />
              </div>
            ) : null}
          </PanelSection>
        ) : (
          <PanelSection title="章节编辑区" icon={FileText}>
            <p className="text-xs leading-6 text-[var(--text-secondary)]">
              当前还没有章节草稿可编辑。
            </p>
          </PanelSection>
        )
      ) : null}

      {activeTab === "latex" ? (
        <>
          <PanelActionBar>
            <CompileFeatureButton
              workspaceId={workspaceId}
              label="一键编译"
              onError={setActionError}
            />
          </PanelActionBar>
          <PanelSection title="LaTeX 主稿与编译" icon={Layers3}>
            {actionError ? (
              <p className="mb-3 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-600">
                {actionError}
              </p>
            ) : null}
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
                <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">主稿来源</p>
                <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">
                  {source.artifact ? `${source.title} · v${source.version}` : "尚无可用编译快照"}
                </p>
              </div>
              <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
                <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">最近编译</p>
                <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">
                  {latestCompile?.artifact
                    ? `${latestCompile.artifact.title || "编译结果"} · ${latestCompile.pageCount ?? "?"} 页`
                    : "尚未编译"}
                </p>
              </div>
            </div>
            {linkedLatexProjectId ? (
              <div className="mt-4 rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-4 py-4">
                <p className="text-xs leading-6 text-[var(--text-secondary)]">
                  主稿已统一收敛到独立 LaTeX 项目。请在编辑器中修改源码，工作区只保留编译与结果追踪。
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Link
                    href={`/latex/${linkedLatexProjectId}`}
                    className="inline-flex items-center gap-2 rounded-xl border border-[var(--border-default)] bg-white px-3 py-2 text-xs font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-muted)]"
                  >
                    <FileText className="h-3.5 w-3.5" />
                    打开 LaTeX 项目编辑器
                  </Link>
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={isDeletingLinkedProject}
                    onClick={async () => {
                      if (!linkedLatexProjectId) {
                        return;
                      }
                      const confirmed = window.confirm(
                        `确定删除 LaTeX 项目（${linkedLatexProjectId.slice(0, 8)}）吗？`,
                      );
                      if (!confirmed) {
                        return;
                      }
                      setActionError(null);
                      setIsDeletingLinkedProject(true);
                      try {
                        await deleteLatexProject(linkedLatexProjectId);
                        setDeletedLinkedProjectId(linkedLatexProjectId);
                      } catch (error) {
                        setActionError(
                          error instanceof Error ? error.message : "删除 LaTeX 项目失败",
                        );
                      } finally {
                        setIsDeletingLinkedProject(false);
                      }
                    }}
                  >
                    <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                    {isDeletingLinkedProject ? "删除中..." : "删除 LaTeX 项目"}
                  </Button>
                </div>
              </div>
            ) : (
              <p className="mt-4 text-xs leading-6 text-[var(--text-secondary)]">
                当前任务尚未绑定 LaTeX 项目。请先执行一次编译，系统会自动创建并绑定主稿项目。
              </p>
            )}
            <div className="mt-4 rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-4 py-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
                  最近编译日志
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setIsCompileLogDialogOpen(true)}
                  disabled={!latestCompile?.compileLogs}
                >
                  查看后台详情
                </Button>
              </div>
              <p className="mt-2 text-xs leading-6 text-[var(--text-secondary)]">
                {latestCompile?.compileLogs
                  ? "日志已生成，点击按钮查看完整输出。"
                  : "当前还没有编译日志。"}
              </p>
            </div>
          </PanelSection>
        </>
      ) : null}

      {activeTab === "preview" ? (
        latestCompile?.pdfUrl ? (
          <PanelSection title="PDF 预览" icon={FileText}>
            <a
              href={latestCompile.pdfUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-xl border border-[var(--border-default)] bg-white px-3 py-2 text-xs font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-muted)]"
            >
              <FileText className="h-3.5 w-3.5" />
              打开已编译 PDF
            </a>
            <div className="mt-4 overflow-hidden rounded-2xl border border-[var(--border-default)] bg-white">
              <iframe
                src={`${latestCompile.pdfUrl}#toolbar=0&navpanes=0`}
                title="已编译 PDF 预览"
                className="h-[76vh] min-h-[700px] w-full"
              />
            </div>
          </PanelSection>
        ) : (
          <PanelSection title="PDF 预览" icon={FileText}>
            <p className="text-xs leading-6 text-[var(--text-secondary)]">
              当前还没有可预览的 PDF，请先执行编译。
            </p>
          </PanelSection>
        )
      ) : null}

      <Dialog open={isCompileLogDialogOpen} onOpenChange={setIsCompileLogDialogOpen}>
        <DialogContent className="max-h-[85vh] max-w-4xl overflow-hidden">
          <DialogHeader>
            <DialogTitle>编译后台详情</DialogTitle>
            <DialogDescription>
              {latestCompile?.artifact
                ? `Artifact ID：${latestCompile.artifact.id}`
                : "暂无编译 Artifact"}
            </DialogDescription>
          </DialogHeader>
          <pre className="max-h-[60vh] overflow-auto rounded-2xl bg-[var(--bg-base)] px-4 py-3 text-[11px] leading-6 text-[var(--text-secondary)]">
            {latestCompile?.compileLogs || "暂无日志"}
          </pre>
        </DialogContent>
      </Dialog>

      <SubagentTimeline items={session.subagents} />
    </div>
  );
}

function CompilePanel({
  workspaceId,
  session,
}: FeaturePanelRendererProps) {
  return <ThesisWritingPanel workspaceId={workspaceId} session={session} />;
}

function GenericFeaturePanel({
  session,
}: FeaturePanelRendererProps) {
  const resultData =
    session.result && typeof session.result.data === "object" && session.result.data
      ? (session.result.data as Record<string, unknown>)
      : session.result ?? {};
  const latexProjectId = readLinkedLatexProjectId(resultData);
  const syncConflicts = readSyncConflicts(resultData);

  return (
    <div className="space-y-4">
      <TaskRuntimePanel
        runtime={session.runtime}
        isRunning={session.status === "running" || session.status === "pending"}
        status={session.message}
        error={session.error}
        title={session.title}
      />
      {latexProjectId ? <LinkedLatexProjectCard projectId={latexProjectId} /> : null}
      {syncConflicts.length > 0 ? (
        <SyncConflictNotice conflicts={syncConflicts as Array<Record<string, unknown>>} />
      ) : null}
      <SubagentTimeline items={session.subagents} />
    </div>
  );
}

const FEATURE_PANEL_RENDERERS: Record<
  string,
  (props: FeaturePanelRendererProps) => ReactNode
> = {
  deep_research: (props) => <DeepResearchPanel {...props} />,
  literature_search: (props) => <LiteratureSearchPanel {...props} />,
  opening_research: (props) => <OpeningResearchPanel {...props} />,
  literature_review: (props) => <LiteratureReviewPanel {...props} />,
  framework_outline: (props) => <FrameworkOutlinePanel {...props} />,
  paper_analysis: (props) => <PaperAnalysisPanel {...props} />,
  proposal_outline: (props) => <ProposalOutlinePanel {...props} />,
  background_research: (props) => <BackgroundResearchPanel {...props} />,
  thesis_writing: (props) => <ThesisWritingPanel {...props} />,
  compile_export: (props) => <CompilePanel {...props} />,
};

const PANEL_KEY_RENDERERS: Record<
  string,
  (props: FeaturePanelRendererProps) => ReactNode
> = {
  deep_research_panel: (props) => <DeepResearchPanel {...props} />,
  literature_panel: (props) => <LiteratureSearchPanel {...props} />,
  opening_research_panel: (props) => <OpeningResearchPanel {...props} />,
  thesis_editor: (props) => <ThesisWritingPanel {...props} />,
  compile_panel: (props) => <CompilePanel {...props} />,
  analysis_panel: (props) => <PaperAnalysisPanel {...props} />,
  editor_panel: (props) => <FrameworkOutlinePanel {...props} />,
  outline_editor: (props) => <ProposalOutlinePanel {...props} />,
};

function resolvePanelRenderer(
  session: FeaturePanelSession
): ((props: FeaturePanelRendererProps) => ReactNode) {
  const featureRenderer = FEATURE_PANEL_RENDERERS[session.featureId];
  if (featureRenderer) {
    return featureRenderer;
  }

  if (session.panelKey) {
    const panelRenderer = PANEL_KEY_RENDERERS[session.panelKey];
    if (panelRenderer) {
      return panelRenderer;
    }
  }

  return GenericFeaturePanel;
}

export function FeaturePanelHost({ workspaceId }: FeaturePanelHostProps) {
  const workspacePanel = useFeaturePanelStore(
    (state) => state.byWorkspace[workspaceId] ?? { activeSessionId: null, sessions: [] }
  );
  const setActiveSession = useFeaturePanelStore((state) => state.setActiveSession);
  const dismissSession = useFeaturePanelStore((state) => state.dismissSession);
  const session = workspacePanel.activeSessionId
    ? workspacePanel.sessions.find((candidate) => candidate.taskId === workspacePanel.activeSessionId) ?? null
    : workspacePanel.sessions[0] ?? null;

  if (!session) {
    return <EmptyWorkPanel />;
  }

  const renderPanel = resolvePanelRenderer(session);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-[var(--border-default)] px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="section-accent text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
              Active Work
            </p>
            <h3 className="mt-2 text-base font-semibold text-[var(--text-primary)]">
              {session.title}
            </h3>
            <p className="mt-1 text-xs leading-6 text-[var(--text-secondary)]">
              {session.description}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <span className="rounded-full border border-[var(--border-default)] bg-white/80 px-2.5 py-1 text-[10px] text-[var(--text-muted)]">
                任务 {session.taskId.slice(0, 8)}
              </span>
              {session.currentStep ? (
                <span className="rounded-full border border-[var(--border-default)] bg-white/80 px-2.5 py-1 text-[10px] text-[var(--text-muted)]">
                  阶段 {session.currentStep}
                </span>
              ) : null}
              <span className="rounded-full border border-[var(--border-default)] bg-white/80 px-2.5 py-1 text-[10px] text-[var(--text-muted)]">
                最近更新 {new Date(session.updatedAt).toLocaleString("zh-CN", {
                  month: "2-digit",
                  day: "2-digit",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <PanelStatusBadge status={session.status} />
            <button
              type="button"
              onClick={() => dismissSession(workspaceId, session.taskId)}
              className="rounded-full border border-[var(--border-default)] p-1.5 text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-surface)]"
              aria-label="关闭当前工作面板"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>

      <SessionSwitcher
        sessions={workspacePanel.sessions.map((item) => ({
          taskId: item.taskId,
          title: item.title,
          status: item.status,
          updatedAt: item.updatedAt,
        }))}
        activeSessionId={workspacePanel.activeSessionId}
        onSelect={(taskId) => setActiveSession(workspaceId, taskId)}
      />

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {renderPanel({ workspaceId, session })}
      </div>
    </div>
  );
}
