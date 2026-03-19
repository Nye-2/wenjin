"use client";

import { useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, BookOpen, Plus, Search, Filter, Download, Star, Trash2 } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useLiteratureStore } from "@/stores/literature";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import { useModelSelection } from "@/hooks/useModelSelection";
import { TaskFeedbackBanner } from "@/components/workspace/TaskFeedbackBanner";
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

export default function LiteraturePage() {
  const params = useParams();
  const router = useRouter();
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
  const [searchQuery, setSearchQuery] = useState("");
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
            a.type === "literature_review" ||
            a.type === "deep_research" ||
            a.type === "deep_research_result"
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
    <div className="h-screen flex flex-col bg-[var(--bg-base)]">
      {/* Header */}
      <header className="h-14 flex items-center justify-between px-4 bg-[var(--glass-bg)] backdrop-blur-xl border-b border-[var(--glass-border)]">
        <div className="flex items-center gap-4">
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => router.push(`/workspaces/${workspaceId}`)}
            className={cn(
              "p-2 rounded-lg",
              "bg-[var(--bg-surface)]",
              "hover:bg-[var(--bg-muted)]",
              "text-[var(--text-secondary)]",
              "transition-colors"
            )}
          >
            <ArrowLeft className="w-5 h-5" />
          </motion.button>

          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-emerald-500/10">
              <BookOpen className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-[var(--text-primary)]">
                文献管理
              </h1>
              <p className="text-xs text-[var(--text-muted)]">
                管理研究参考文献
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsCreateDialogOpen(true)}
            className="flex items-center gap-2 px-4 py-2 bg-[var(--bg-surface)] border border-[var(--border-default)] text-[var(--text-secondary)] rounded-lg hover:bg-[var(--bg-muted)] transition-colors"
          >
            <Plus className="w-4 h-4" />
            添加文献
          </button>
          <button
            className={cn(
              "flex items-center gap-2 px-4 py-2 rounded-lg transition-colors",
              "bg-[var(--bg-surface)] border border-[var(--border-default)] text-[var(--text-secondary)]",
              isImporting ? "opacity-60 cursor-not-allowed" : "hover:bg-[var(--bg-muted)]"
            )}
            onClick={handleImportDeepResearch}
            disabled={isImporting}
          >
            <Download className="w-4 h-4" />
            {isImporting ? "导入中..." : "从 Deep Research 导入"}
          </button>
          <button
            className={cn(
              "flex items-center gap-2 px-4 py-2 rounded-lg text-white transition-colors",
              isOrganizing ? "bg-emerald-500 cursor-not-allowed" : "bg-emerald-600 hover:bg-emerald-700"
            )}
            onClick={handleOrganize}
            disabled={isOrganizing}
          >
            <BookOpen className="w-4 h-4" />
            {isOrganizing ? "盘点中..." : "智能盘点"}
          </button>
        </div>
      </header>

      {/* Stats Bar */}
      <div className="flex items-center gap-6 px-6 py-3 bg-[var(--bg-surface)] border-b border-[var(--border-default)]">
        <div className="flex items-center gap-2">
          <span className="text-2xl font-bold text-[var(--text-primary)]">{total}</span>
          <span className="text-sm text-[var(--text-muted)]">篇文献</span>
        </div>
        <div className="w-px h-6 bg-[var(--border-default)]" />
        <div className="flex items-center gap-2">
          <span className="text-2xl font-bold text-amber-600">{coreCount}</span>
          <span className="text-sm text-[var(--text-muted)]">篇核心文献</span>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="flex items-center gap-3 px-6 py-3 bg-[var(--bg-elevated)] border-b border-[var(--border-default)]">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-muted)]" />
          <input
            type="text"
            placeholder="搜索文献..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-[var(--bg-surface)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
          />
        </div>
        <button
          className="flex items-center gap-2 px-3 py-2 bg-[var(--bg-surface)] border border-[var(--border-default)] rounded-lg text-sm text-[var(--text-muted)]"
        >
          <Filter className="w-4 h-4" />
          <select
            value={sourceFilter}
            onChange={(event) => setSourceFilter(event.target.value as typeof sourceFilter)}
            className="bg-transparent outline-none"
          >
            <option value="all">全部来源</option>
            <option value="manual">手动</option>
            <option value="deep_research">Deep Research</option>
          </select>
        </button>
        <button
          className="flex items-center gap-2 px-3 py-2 bg-[var(--bg-surface)] border border-[var(--border-default)] rounded-lg text-sm text-[var(--text-muted)]"
        >
          <Star className="w-4 h-4" />
          <select
            value={coreFilter}
            onChange={(event) => setCoreFilter(event.target.value as typeof coreFilter)}
            className="bg-transparent outline-none"
          >
            <option value="all">全部文献</option>
            <option value="core">仅核心</option>
            <option value="non_core">非核心</option>
          </select>
        </button>
        <ModelSelector
          id="literature-management-model"
          label="盘点模型"
          className="w-64"
          models={availableModels}
          selectedModel={selectedModel}
          onChange={setSelectedModel}
          isLoading={isModelLoading}
          loadError={modelLoadError}
          disabled={isOrganizing}
        />
      </div>

      {(organizeStatus || organizeError || isOrganizing || importStatus || importError || isImporting) && (
        <div className="px-6 py-2 bg-[var(--bg-elevated)] border-b border-[var(--border-default)]">
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
            className="mt-2"
            pendingText="正在从 Deep Research 导入文献..."
          />
        </div>
      )}

      {/* Main Content */}
      <main className="flex-1 overflow-auto p-6">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
              className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full"
            />
          </div>
        ) : filteredItems.length === 0 ? (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center py-16"
          >
            <BookOpen className="w-16 h-16 text-emerald-500 mx-auto mb-4 opacity-50" />
            <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
              暂无文献
            </h2>
            <p className="text-[var(--text-secondary)] mb-6">
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
                className="p-4 bg-[var(--bg-surface)] border border-[var(--border-default)] rounded-xl hover:border-emerald-500/30 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="font-medium text-[var(--text-primary)] mb-1">
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
                          router.push(`/workspaces/${workspaceId}/paper-analysis?${query.toString()}`);
                        }}
                        className="px-2 py-1 text-xs bg-fuchsia-500/10 text-fuchsia-600 rounded hover:bg-fuchsia-500/20"
                      >
                        分析
                      </button>
                    )}
                    <button
                      onClick={() => void toggleCore(workspaceId, lit.id, !lit.is_core)}
                      className={cn(
                        "rounded px-2 py-1 text-xs",
                        lit.is_core
                          ? "bg-amber-500/10 text-amber-600"
                          : "bg-[var(--bg-elevated)] text-[var(--text-muted)]"
                      )}
                    >
                      {lit.is_core ? "取消核心" : "设为核心"}
                    </button>
                    <button
                      onClick={() => void removeLiterature(workspaceId, lit.id)}
                      className="rounded px-2 py-1 text-xs bg-red-500/10 text-red-600"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                    {lit.is_core && (
                      <span className="px-2 py-1 text-xs bg-amber-500/10 text-amber-600 rounded">
                        核心
                      </span>
                    )}
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </main>

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
    </div>
  );
}
