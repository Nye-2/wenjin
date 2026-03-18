"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, Search, BookMarked } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import { TaskFeedbackBanner } from "@/components/workspace/TaskFeedbackBanner";
import { ModelSelector } from "@/components/workspace/ModelSelector";
import { useModelSelection } from "@/hooks/useModelSelection";
import { cn } from "@/lib/utils";

export default function LiteratureSearchPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace } = useWorkspaceStore();

  const [query, setQuery] = useState("");
  const [discipline, setDiscipline] = useState("");

  useEffect(() => {
    if (workspace && !query) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync from async store
      setQuery((workspace.description || workspace.name || "").toString());
    }
    if (workspace && !discipline && workspace.discipline) {
      setDiscipline(workspace.discipline.toString());
    }
  }, [workspace, query, discipline]);

  const { run, isRunning, status, error } = useFeatureTaskRunner({
    workspaceId,
    featureId: "literature_search",
  });
  const {
    models: availableModels,
    selectedModel,
    setSelectedModel,
    isLoading: isModelLoading,
    loadError: modelLoadError,
  } = useModelSelection({
    purpose: "writing",
    persistenceKey: `workspace:${workspaceId}:model:writing`,
  });

  const handleSearch = async () => {
    if (!query.trim()) return;
    await run({
      query: query.trim(),
      discipline: discipline.trim() || undefined,
      model_id: selectedModel || undefined,
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

            <ModelSelector
              id="literature-search-model"
              label="生成模型"
              models={availableModels}
              selectedModel={selectedModel}
              onChange={setSelectedModel}
              isLoading={isModelLoading}
              loadError={modelLoadError}
              disabled={isRunning}
            />

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

            <TaskFeedbackBanner
              isRunning={isRunning}
              status={status}
              error={error}
              onRetry={handleSearch}
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
