"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, Search, BookMarked } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { executeWorkspaceFeature } from "@/lib/api";
import { pollTaskUntilTerminal } from "@/lib/taskPolling";
import { cn } from "@/lib/utils";

export default function LiteratureSearchPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace, fetchArtifacts } = useWorkspaceStore();

  const [query, setQuery] = useState("");
  const [discipline, setDiscipline] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (workspace && !query) {
      setQuery((workspace.description || workspace.name || "").toString());
    }
    if (workspace?.discipline && !discipline) {
      setDiscipline(workspace.discipline.toString());
    }
  }, [workspace, query, discipline]);

  const handleSearch = async () => {
    if (isRunning) return;
    if (!query.trim()) {
      setError("请输入检索关键词");
      return;
    }

    setError(null);
    setStatus(null);
    setIsRunning(true);

    try {
      const resp = await executeWorkspaceFeature(workspaceId, "literature_search", {
        query: query.trim(),
        discipline: discipline.trim() || undefined,
      });

      if (resp.status === "warning" && !resp.task_id) {
        setError(resp.message || "暂时无法执行文献检索");
        return;
      }
      if (!resp.task_id) {
        setError("任务创建失败，请稍后重试");
        return;
      }

      setStatus("任务已提交，正在进行文献检索...");
      const task = await pollTaskUntilTerminal(resp.task_id, {
        onProgress: (nextTask) => {
          if (nextTask.message) {
            setStatus(nextTask.message);
          }
        },
      });

      if (!task) {
        setError("任务轮询超时，请稍后在工作区查看结果");
        return;
      }

      if (task.status === "success") {
        await fetchArtifacts(workspaceId);
        setStatus(task.message || "文献检索完成");
      } else {
        setError(task.error || task.message || "文献检索失败");
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "文献检索失败，请稍后重试");
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="h-screen flex flex-col bg-[var(--bg-base)]">
      <header className="h-14 flex items-center gap-4 px-4 bg-[var(--glass-bg)] backdrop-blur-xl border-b border-[var(--glass-border)]">
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
            <Search className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-[var(--text-primary)]">文献检索</h1>
            <p className="text-xs text-[var(--text-muted)]">生成结构化检索结果与推荐命中</p>
          </div>
        </div>
      </header>

      <main className="flex-1 flex overflow-hidden">
        <aside className="w-80 border-r border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
          <h2 className="text-sm font-medium text-[var(--text-primary)] mb-4">检索参数</h2>

          <div className="space-y-4">
            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">检索关键词</label>
              <input
                type="text"
                placeholder="如：vision transformer, multimodal learning"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">学科领域（可选）</label>
              <input
                type="text"
                placeholder="如：computer_science"
                value={discipline}
                onChange={(e) => setDiscipline(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              />
            </div>

            <button
              className={cn(
                "w-full py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors",
                isRunning && "opacity-60 cursor-not-allowed"
              )}
              onClick={handleSearch}
              disabled={isRunning}
            >
              {isRunning ? "检索中..." : "开始检索"}
            </button>

            {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
            {status && !error && <p className="text-xs text-[var(--text-secondary)] mt-1">{status}</p>}
          </div>
        </aside>

        <div className="flex-1 p-6 overflow-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="h-full flex items-center justify-center"
          >
            <div className="text-center max-w-xl">
              <BookMarked className="w-16 h-16 text-emerald-500 mx-auto mb-4 opacity-50" />
              <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">SCI 文献检索工作区</h2>
              <p className="text-[var(--text-secondary)]">执行后将生成 `literature_search_results` artifact，并在知识区可见。</p>
              <p className="text-sm text-[var(--text-muted)] mt-2">建议先检索，再进入论文分析模块进行深度结构化解析。</p>
            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
