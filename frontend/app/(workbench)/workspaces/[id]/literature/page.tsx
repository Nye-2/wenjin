"use client";

import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, BookOpen, Plus, Search, Filter } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useLiteratureStore } from "@/stores/literature";
import { executeWorkspaceFeature } from "@/lib/api";
import { pollTaskUntilTerminal } from "@/lib/taskPolling";
import { cn } from "@/lib/utils";
import { useEffect, useState } from "react";

export default function LiteraturePage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace, fetchArtifacts } = useWorkspaceStore();
  const { items, total, coreCount, isLoading, fetchLiterature } = useLiteratureStore();
  const [searchQuery, setSearchQuery] = useState("");
  const [isOrganizing, setIsOrganizing] = useState(false);
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (workspaceId) {
      fetchLiterature(workspaceId);
    }
  }, [workspaceId, fetchLiterature]);

  const handleOrganize = async () => {
    if (isOrganizing) return;
    setActionError(null);
    setActionStatus(null);
    setIsOrganizing(true);

    try {
      const resp = await executeWorkspaceFeature(workspaceId, "literature_management", {
        topic: searchQuery.trim() || workspace?.name || "研究主题",
      });

      if (resp.status === "warning" && !resp.task_id) {
        setActionError(resp.message || "暂时无法执行文献管理盘点");
        return;
      }
      if (!resp.task_id) {
        setActionError("任务创建失败，请稍后重试");
        return;
      }

      setActionStatus("文献盘点任务已提交，正在处理中...");
      const task = await pollTaskUntilTerminal(resp.task_id, {
        onProgress: (nextTask) => {
          if (nextTask.message) {
            setActionStatus(nextTask.message);
          }
        },
      });

      if (!task) {
        setActionError("任务轮询超时，请稍后在工作区查看结果");
        return;
      }

      if (task.status === "success") {
        await Promise.all([fetchLiterature(workspaceId), fetchArtifacts(workspaceId)]);
        setActionStatus(task.message || "文献盘点完成，已同步到成果区");
      } else {
        setActionError(task.error || task.message || "文献盘点任务失败");
      }
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : "文献盘点任务失败");
    } finally {
      setIsOrganizing(false);
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

      {(actionStatus || actionError) && (
        <div className="px-6 py-2 bg-[var(--bg-elevated)] border-b border-[var(--border-default)]">
          {actionError ? (
            <p className="text-sm text-red-600">{actionError}</p>
          ) : (
            <p className="text-sm text-[var(--text-secondary)]">{actionStatus}</p>
          )}
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
