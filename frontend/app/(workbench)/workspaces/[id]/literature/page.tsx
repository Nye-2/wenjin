"use client";

import { useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { BookOpen, Plus, Search, Filter, Download, Star, Trash2 } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useLiteratureStore } from "@/stores/literature";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import { useModelSelection } from "@/hooks/useModelSelection";
import {
  FeatureWorkbenchShell,
  TaskFeedbackBanner,
  TaskRuntimePanel,
  WorkspaceResultPanel,
} from "@/components/workspace";
import { ModelSelector } from "@/components/workspace/ModelSelector";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { useEffect } from "react";
import {
  createWorkspaceResultViewModel,
  describeFields,
  describeTaskStatus,
} from "@/lib/workspace-result";

export default function LiteraturePage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceId = params.id as string;
  const { workspace, fetchArtifacts } = useWorkspaceStore();
  const {
    items,
    total,
    coreCount,
    isLoading,
    fetchLiterature,
    importFromDeepResearch,
    addLiterature,
    toggleCore,
    removeLiterature,
  } =
    useLiteratureStore();
  const querySeed = searchParams.get("query");
  const [searchQuery, setSearchQuery] = useState(() => querySeed || "");
  const [sourceFilter, setSourceFilter] = useState<"all" | "manual" | "deep_research">("all");
  const [coreFilter, setCoreFilter] = useState<"all" | "core" | "non_core">("all");
  const [isImporting, setIsImporting] = useState(false);
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [manualTitle, setManualTitle] = useState("");
  const [manualAuthors, setManualAuthors] = useState("");
  const [manualYear, setManualYear] = useState("");
  const [manualVenue, setManualVenue] = useState("");
  const [manualDoi, setManualDoi] = useState("");
  const [manualAbstract, setManualAbstract] = useState("");
  const [manualIsCore, setManualIsCore] = useState(false);
  const [manualError, setManualError] = useState<string | null>(null);
  const [isSubmittingManual, setIsSubmittingManual] = useState(false);

  const {
    run: runOrganize,
    isRunning: isOrganizing,
    status: organizeStatus,
    error: organizeError,
    runtime: organizeRuntime,
  } = useFeatureTaskRunner({
    workspaceId,
    featureId: "literature_management",
  });
  const {
    models: availableModels,
    selectedModel,
    setSelectedModel,
    isLoading: isModelLoading,
    loadError: modelLoadError,
  } = useModelSelection({
    purpose: "chat",
    persistenceKey: `workspace:${workspaceId}:model:chat`,
  });

  useEffect(() => {
    if (workspaceId) {
      fetchLiterature(workspaceId);
    }
  }, [workspaceId, fetchLiterature]);

  useEffect(() => {
    if (querySeed !== null) {
      setSearchQuery(querySeed);
    }
  }, [querySeed]);

  const filteredItems = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();
    return items.filter((item) => {
      if (sourceFilter !== "all" && item.source !== sourceFilter) {
        return false;
      }
      if (coreFilter === "core" && !item.is_core) {
        return false;
      }
      if (coreFilter === "non_core" && item.is_core) {
        return false;
      }
      if (!normalizedQuery) {
        return true;
      }
      const haystack = [
        item.title,
        item.authors.join(" "),
        item.venue || "",
        item.doi || "",
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(normalizedQuery);
    });
  }, [items, searchQuery, sourceFilter, coreFilter]);
  const resultViewModel = useMemo(
    () =>
      createWorkspaceResultViewModel({
        summary:
          total > 0
            ? `当前已沉淀 ${total} 篇文献，其中 ${coreCount} 篇标记为核心文献。`
            : "本工作区用于管理研究参考文献，并承接 Deep Research 导入结果。",
        sections: [
          {
            title: "当前筛选",
            content: describeFields([
              ["搜索关键词", searchQuery],
              ["来源", sourceFilter],
              ["核心筛选", coreFilter],
            ]),
          },
          {
            title: "文献概览",
            content: describeFields([
              ["总量", total],
              ["核心文献", coreCount],
              ["当前列表", filteredItems.length],
            ]),
          },
          {
            title: "任务状态",
            content: describeTaskStatus({
              error: importError ?? organizeError,
              status: importStatus ?? organizeStatus,
              idleMessage: "尚未执行智能盘点或导入。",
              isLoading: isOrganizing || isImporting,
              loadingMessage: isImporting
                ? "正在从 Deep Research 导入文献..."
                : "文献盘点任务执行中...",
            }),
          },
        ],
        nextActions: [
          "先从 Deep Research 导入或手动补录文献。",
          "对关键文献设置核心标记，方便后续写作和分析。",
          "SCI 工作区可直接从列表跳转到论文分析模块。",
        ],
        outputLanguage: "zh",
      }),
    [
      total,
      coreCount,
      filteredItems.length,
      searchQuery,
      sourceFilter,
      coreFilter,
      importError,
      organizeError,
      importStatus,
      organizeStatus,
      isOrganizing,
      isImporting,
    ]
  );

  const handleOrganize = async () => {
    if (isOrganizing) return;
    setImportError(null);
    setImportStatus(null);
    await runOrganize({
      topic: searchQuery.trim() || workspace?.name || "研究主题",
      model_id: selectedModel || undefined,
    });
  };

  const handleImportDeepResearch = async () => {
    if (isImporting) return;
    setImportError(null);
    setImportStatus(null);
    setIsImporting(true);

    try {
      // Refresh artifacts to get latest Deep Research results
      await fetchArtifacts(workspaceId);
      const storeArtifacts = useWorkspaceStore.getState().artifacts;
      const deepResearchIds = storeArtifacts
        .filter(
          (a) =>
            a.type === "deep_research_report"
        )
        .map((a) => a.id);

      if (deepResearchIds.length === 0) {
        setImportStatus("未找到 Deep Research 产物，请先执行 Deep Research 任务");
        return;
      }

      const count = await importFromDeepResearch(workspaceId, deepResearchIds);
      if (count > 0) {
        setImportStatus(`成功导入 ${count} 篇文献`);
        await fetchLiterature(workspaceId);
      } else {
        setImportStatus("未导入新文献（可能已全部导入过）");
      }
    } catch (e: unknown) {
      setImportError(
        e instanceof Error ? e.message : "从 Deep Research 导入失败"
      );
    } finally {
      setIsImporting(false);
    }
  };

  const resetManualForm = () => {
    setManualTitle("");
    setManualAuthors("");
    setManualYear("");
    setManualVenue("");
    setManualDoi("");
    setManualAbstract("");
    setManualIsCore(false);
    setManualError(null);
  };

  const handleCreateManual = async () => {
    if (!manualTitle.trim()) {
      setManualError("标题不能为空");
      return;
    }
    setManualError(null);
    setIsSubmittingManual(true);
    try {
      const yearValue = Number(manualYear);
      const authors = manualAuthors
        .split(/[,，]+/)
        .map((item) => item.trim())
        .filter(Boolean);
      const created = await addLiterature(workspaceId, {
        title: manualTitle.trim(),
        authors,
        year: Number.isFinite(yearValue) && yearValue > 0 ? yearValue : undefined,
        venue: manualVenue.trim() || undefined,
        doi: manualDoi.trim() || undefined,
        abstract: manualAbstract.trim() || undefined,
        source: "manual",
        is_core: manualIsCore,
      });

      if (!created) {
        setManualError("手动添加失败");
        return;
      }
      if (manualIsCore) {
        await toggleCore(workspaceId, created.id, true);
      }
      setIsCreateDialogOpen(false);
      resetManualForm();
    } catch (e: unknown) {
      setManualError(e instanceof Error ? e.message : "手动添加失败");
    } finally {
      setIsSubmittingManual(false);
    }
  };

  return (
    <>
      <FeatureWorkbenchShell
        workspaceId={workspaceId}
        title="文献管理"
        description="管理研究参考文献"
        icon={BookOpen}
        iconBgClass="bg-emerald-500/10"
        iconClass="text-emerald-600 dark:text-emerald-400"
        headerActions={
          <div className="flex flex-wrap items-center justify-end gap-2">
            <button
              onClick={() => setIsCreateDialogOpen(true)}
              className="flex items-center gap-2 rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-2 text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-muted)]"
            >
              <Plus className="h-4 w-4" />
              添加文献
            </button>
            <button
              className={cn(
                "flex items-center gap-2 rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-2 text-[var(--text-secondary)] transition-colors",
                isImporting ? "cursor-not-allowed opacity-60" : "hover:bg-[var(--bg-muted)]"
              )}
              onClick={handleImportDeepResearch}
              disabled={isImporting}
            >
              <Download className="h-4 w-4" />
              {isImporting ? "导入中..." : "从 Deep Research 导入"}
            </button>
            <button
              className={cn(
                "flex items-center gap-2 rounded-lg px-4 py-2 text-white transition-colors",
                isOrganizing
                  ? "cursor-not-allowed bg-emerald-500"
                  : "bg-emerald-600 hover:bg-emerald-700"
              )}
              onClick={handleOrganize}
              disabled={isOrganizing}
            >
              <BookOpen className="h-4 w-4" />
              {isOrganizing ? "盘点中..." : "智能盘点"}
            </button>
          </div>
        }
        sidebarTitle="检索与过滤"
        sidebar={
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
                <p className="text-xs text-[var(--text-muted)]">文献总量</p>
                <p className="mt-1 text-2xl font-semibold text-[var(--text-primary)]">
                  {total}
                </p>
              </div>
              <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
                <p className="text-xs text-[var(--text-muted)]">核心文献</p>
                <p className="mt-1 text-2xl font-semibold text-amber-600">
                  {coreCount}
                </p>
              </div>
            </div>

            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
              <input
                type="text"
                placeholder="搜索文献..."
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] py-2 pl-10 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs text-[var(--text-muted)]">
                来源筛选
              </label>
              <div className="flex items-center gap-2 rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2">
                <Filter className="h-4 w-4 text-[var(--text-muted)]" />
                <select
                  value={sourceFilter}
                  onChange={(event) =>
                    setSourceFilter(event.target.value as typeof sourceFilter)
                  }
                  className="w-full bg-transparent text-sm outline-none"
                >
                  <option value="all">全部来源</option>
                  <option value="manual">手动</option>
                  <option value="deep_research">Deep Research</option>
                </select>
              </div>
            </div>

            <div>
              <label className="mb-1 block text-xs text-[var(--text-muted)]">
                核心筛选
              </label>
              <div className="flex items-center gap-2 rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2">
                <Star className="h-4 w-4 text-[var(--text-muted)]" />
                <select
                  value={coreFilter}
                  onChange={(event) =>
                    setCoreFilter(event.target.value as typeof coreFilter)
                  }
                  className="w-full bg-transparent text-sm outline-none"
                >
                  <option value="all">全部文献</option>
                  <option value="core">仅核心</option>
                  <option value="non_core">非核心</option>
                </select>
              </div>
            </div>

            <ModelSelector
              id="literature-management-model"
              label="盘点模型"
              models={availableModels}
              selectedModel={selectedModel}
              onChange={setSelectedModel}
              isLoading={isModelLoading}
              loadError={modelLoadError}
              disabled={isOrganizing}
            />

            {(organizeStatus ||
              organizeError ||
              isOrganizing ||
              importStatus ||
              importError ||
              isImporting) && (
              <div className="space-y-2">
                <TaskFeedbackBanner
                  isRunning={isOrganizing}
                  status={organizeStatus}
                  error={organizeError}
                  onRetry={handleOrganize}
                  className="mt-0"
                  pendingText="文献盘点任务执行中..."
                />
                <TaskFeedbackBanner
                  isRunning={isImporting}
                  status={importStatus}
                  error={importError}
                  onRetry={handleImportDeepResearch}
                  className="mt-0"
                  pendingText="正在从 Deep Research 导入文献..."
                />
              </div>
            )}
          </div>
        }
      >
        <TaskRuntimePanel
          runtime={organizeRuntime}
          isRunning={isOrganizing}
          status={organizeStatus}
          error={organizeError}
          title="文献盘点运行面板"
          emptyDescription="执行后，这里会显示文献加载、智能盘点和建议动作。"
        />
        <WorkspaceResultPanel viewModel={resultViewModel} />

        <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-[var(--text-primary)]">
                文献列表
              </h2>
              <p className="text-sm text-[var(--text-muted)]">
                当前筛选下共 {filteredItems.length} 篇文献
              </p>
            </div>
          </div>

          {isLoading ? (
            <div className="flex items-center justify-center py-16">
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                className="h-8 w-8 rounded-full border-2 border-emerald-500 border-t-transparent"
              />
            </div>
          ) : filteredItems.length === 0 ? (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="py-16 text-center"
            >
              <BookOpen className="mx-auto mb-4 h-16 w-16 text-emerald-500 opacity-50" />
              <h2 className="mb-2 text-xl font-semibold text-[var(--text-primary)]">
                暂无文献
              </h2>
              <p className="text-[var(--text-secondary)]">
                添加文献或从 Deep Research 导入
              </p>
            </motion.div>
          ) : (
            <div className="space-y-3">
              {filteredItems.map((lit, idx) => (
                <motion.div
                  key={lit.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: idx * 0.05 }}
                  className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-4 transition-colors hover:border-emerald-500/30"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <h3 className="mb-1 font-medium text-[var(--text-primary)]">
                        {lit.title}
                      </h3>
                      <p className="text-sm text-[var(--text-muted)]">
                        {lit.authors.join(", ")} · {lit.year || "未知年份"}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {workspace?.type === "sci" && (
                        <button
                          onClick={() => {
                            const query = new URLSearchParams({
                              paper_id: lit.id,
                              paper_title: lit.title || "",
                              paper_abstract: lit.abstract || "",
                            });
                            router.push(
                              `/workspaces/${workspaceId}/paper-analysis?${query.toString()}`
                            );
                          }}
                          className="rounded bg-fuchsia-500/10 px-2 py-1 text-xs text-fuchsia-600 hover:bg-fuchsia-500/20"
                        >
                          分析
                        </button>
                      )}
                      <button
                        onClick={() =>
                          void toggleCore(workspaceId, lit.id, !lit.is_core)
                        }
                        className={cn(
                          "rounded px-2 py-1 text-xs",
                          lit.is_core
                            ? "bg-amber-500/10 text-amber-600"
                            : "bg-[var(--bg-surface)] text-[var(--text-muted)]"
                        )}
                      >
                        {lit.is_core ? "取消核心" : "设为核心"}
                      </button>
                      <button
                        onClick={() => void removeLiterature(workspaceId, lit.id)}
                        className="rounded bg-red-500/10 px-2 py-1 text-xs text-red-600"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                      {lit.is_core && (
                        <span className="rounded bg-amber-500/10 px-2 py-1 text-xs text-amber-600">
                          核心
                        </span>
                      )}
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          )}
        </div>
      </FeatureWorkbenchShell>

      <Dialog
        open={isCreateDialogOpen}
        onOpenChange={(open) => {
          setIsCreateDialogOpen(open);
          if (!open) {
            resetManualForm();
          }
        }}
      >
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>手动添加文献</DialogTitle>
            <DialogDescription>
              补录未通过 Deep Research 导入的论文、报告或专利文献。
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="md:col-span-2">
              <label className="mb-1 block text-xs text-[var(--text-muted)]">
                标题
              </label>
              <input
                value={manualTitle}
                onChange={(event) => setManualTitle(event.target.value)}
                className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm"
              />
            </div>
            <div className="md:col-span-2">
              <label className="mb-1 block text-xs text-[var(--text-muted)]">
                作者（逗号分隔）
              </label>
              <input
                value={manualAuthors}
                onChange={(event) => setManualAuthors(event.target.value)}
                className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-[var(--text-muted)]">
                年份
              </label>
              <input
                value={manualYear}
                onChange={(event) => setManualYear(event.target.value)}
                className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-[var(--text-muted)]">
                期刊 / 会议
              </label>
              <input
                value={manualVenue}
                onChange={(event) => setManualVenue(event.target.value)}
                className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm"
              />
            </div>
            <div className="md:col-span-2">
              <label className="mb-1 block text-xs text-[var(--text-muted)]">
                DOI
              </label>
              <input
                value={manualDoi}
                onChange={(event) => setManualDoi(event.target.value)}
                className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm"
              />
            </div>
            <div className="md:col-span-2">
              <label className="mb-1 block text-xs text-[var(--text-muted)]">
                摘要
              </label>
              <textarea
                rows={4}
                value={manualAbstract}
                onChange={(event) => setManualAbstract(event.target.value)}
                className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm"
              />
            </div>
            <label className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
              <input
                type="checkbox"
                checked={manualIsCore}
                onChange={(event) => setManualIsCore(event.target.checked)}
              />
              标记为核心文献
            </label>
          </div>

          {manualError && (
            <p className="text-sm text-red-600">{manualError}</p>
          )}

          <div className="flex justify-end gap-3">
            <button
              onClick={() => setIsCreateDialogOpen(false)}
              className="rounded-lg border border-[var(--border-default)] px-4 py-2 text-sm text-[var(--text-secondary)]"
            >
              取消
            </button>
            <button
              onClick={() => void handleCreateManual()}
              disabled={isSubmittingManual}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm text-white disabled:opacity-60"
            >
              {isSubmittingManual ? "添加中..." : "确认添加"}
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
