"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, FlaskConical, FileText } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import { TaskFeedbackBanner } from "@/components/workspace/TaskFeedbackBanner";
import { cn } from "@/lib/utils";

export default function PaperAnalysisPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceId = params.id as string;
  const { workspace } = useWorkspaceStore();

  const [paperId, setPaperId] = useState(
    () => searchParams.get("paper_id") || ""
  );
  const [paperTitle, setPaperTitle] = useState(
    () => searchParams.get("paper_title") || ""
  );
  const [paperAbstract, setPaperAbstract] = useState(
    () => searchParams.get("paper_abstract") || ""
  );

  useEffect(() => {
    if (workspace && !paperTitle) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync from async store
      setPaperTitle((workspace.description || workspace.name || "").toString());
    }
  }, [workspace, paperTitle]);

  const { run, isRunning, status, error } = useFeatureTaskRunner({
    workspaceId,
    featureId: "paper_analysis",
  });

  const handleAnalyze = async () => {
    if (!paperId.trim() && !paperTitle.trim()) return;
    await run({
      paper_id: paperId.trim() || undefined,
      paper_title: paperTitle.trim() || undefined,
      paper_abstract: paperAbstract.trim() || undefined,
    });
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
          <div className="p-2 rounded-lg bg-fuchsia-500/10">
            <FlaskConical className="w-5 h-5 text-fuchsia-600 dark:text-fuchsia-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-[var(--text-primary)]">论文分析</h1>
            <p className="text-xs text-[var(--text-muted)]">生成方法/实验/结论/创新点结构化分析</p>
          </div>
        </div>
      </header>

      <main className="flex-1 flex overflow-hidden">
        <aside className="w-80 border-r border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
          <h2 className="text-sm font-medium text-[var(--text-primary)] mb-4">分析参数</h2>

          <div className="space-y-4">
            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">Paper ID（可选）</label>
              <input
                type="text"
                placeholder="输入已保存论文 ID"
                value={paperId}
                onChange={(e) => setPaperId(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-fuchsia-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">论文标题</label>
              <input
                type="text"
                placeholder="输入论文标题"
                value={paperTitle}
                onChange={(e) => setPaperTitle(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-fuchsia-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">论文摘要（可选）</label>
              <textarea
                placeholder="可粘贴摘要提高分析质量"
                value={paperAbstract}
                onChange={(e) => setPaperAbstract(e.target.value)}
                rows={4}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-fuchsia-500/50"
              />
            </div>

            <button
              className={cn(
                "w-full py-2 bg-fuchsia-600 text-white rounded-lg hover:bg-fuchsia-700 transition-colors",
                isRunning && "opacity-60 cursor-not-allowed"
              )}
              onClick={handleAnalyze}
              disabled={isRunning}
            >
              {isRunning ? "分析中..." : "开始分析"}
            </button>

            <TaskFeedbackBanner
              isRunning={isRunning}
              status={status}
              error={error}
              onRetry={handleAnalyze}
            />
          </div>
        </aside>

        <div className="flex-1 p-6 overflow-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="h-full flex items-center justify-center"
          >
            <div className="text-center max-w-xl">
              <FileText className="w-16 h-16 text-fuchsia-500 mx-auto mb-4 opacity-50" />
              <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">SCI 论文分析工作区</h2>
              <p className="text-[var(--text-secondary)]">执行后将生成 `paper_analysis` artifact，并可在知识区继续迭代。</p>
              <p className="text-sm text-[var(--text-muted)] mt-2">支持从文献列表跳转时通过 URL 参数自动带入论文信息。</p>
            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
