"use client";

import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, BookOpen, Plus, Search, Filter, Download } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useLiteratureStore } from "@/stores/literature";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import { TaskFeedbackBanner } from "@/components/workspace/TaskFeedbackBanner";
import { cn } from "@/lib/utils";
import { useEffect, useState } from "react";

export default function LiteraturePage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace, fetchArtifacts } = useWorkspaceStore();
  const { items, total, coreCount, isLoading, fetchLiterature, importFromDeepResearch } =
    useLiteratureStore();
  const [searchQuery, setSearchQuery] = useState("");
  const [isImporting, setIsImporting] = useState(false);
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  const {
    run: runOrganize,
    isRunning: isOrganizing,
    status: organizeStatus,
    error: organizeError,
  } = useFeatureTaskRunner({
    workspaceId,
    featureId: "literature_management",
  });

  useEffect(() => {
    if (workspaceId) {
      fetchLiterature(workspaceId);
    }
  }, [workspaceId, fetchLiterature]);

  const handleOrganize = async () => {
    if (isOrganizing) return;
    setImportError(null);
    setImportStatus(null);
    await runOrganize({
      topic: searchQuery.trim() || workspace?.name || "研究主题",
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
        .filter((a) => a.type === "deep_research" || a.type === "deep_research_result")
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
          <button className="flex items-center gap-2 px-4 py-2 bg-[var(--bg-surface)] border border-[var(--border-default)] text-[var(--text-secondary)] rounded-lg hover:bg-[var(--bg-muted)] transition-colors">
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
            {isOrganizing ? "盘点中..." : "智能盘点（20积分）"}
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
        <button className="flex items-center gap-2 px-3 py-2 bg-[var(--bg-surface)] border border-[var(--border-default)] rounded-lg text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-muted)]">
          <Filter className="w-4 h-4" />
          筛选
        </button>
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
        ) : items.length === 0 ? (
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
            {items.map((lit, idx) => (
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
    </div>
  );
}
