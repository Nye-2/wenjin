"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, Search } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import { TaskFeedbackBanner } from "@/components/workspace/TaskFeedbackBanner";
import { ModelSelector } from "@/components/workspace/ModelSelector";
import { useModelSelection } from "@/hooks/useModelSelection";
import {
  WorkspaceResultPanel,
  type WorkspaceResultViewModel,
} from "@/components/workspace/WorkspaceResultPanel";
import { createWorkspaceResultViewModel, describeFields, describeTaskStatus } from "@/lib/workspace-result";
import {
  findLatestArtifact,
  getArtifactContentRecord,
  readString,
  readStringList,
} from "@/lib/artifact-utils";
import { cn } from "@/lib/utils";

export default function LiteratureSearchPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace, artifacts } = useWorkspaceStore();

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

  const { run, isRunning, status, error, result: latestTaskResult } = useFeatureTaskRunner({
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

  const latestSearchArtifact = useMemo(
    () => findLatestArtifact(artifacts, ["literature_search_results"]),
    [artifacts]
  );
  const latestSearchResult = useMemo(
    () => getArtifactContentRecord(latestSearchArtifact) ?? latestTaskResult,
    [latestSearchArtifact, latestTaskResult]
  );
  const latestSearchPapers = Array.isArray(latestSearchResult?.papers)
    ? latestSearchResult.papers
    : [];
  const latestTopHits = Array.isArray(latestSearchResult?.top_hits)
    ? latestSearchResult.top_hits
    : [];
  const latestSearchSummary = readString(latestSearchResult?.summary);
  const topTitles = readStringList(
    latestTopHits.map((item: unknown) =>
      item && typeof item === "object"
        ? (item as Record<string, unknown>).title
        : item
    ),
    3
  );
  const resultViewModel: WorkspaceResultViewModel = createWorkspaceResultViewModel({
    summary: latestSearchResult
      ? "最近一次文献检索结果已生成，可继续进入论文分析或写作。"
      : "本工作区用于生成结构化文献检索结果与推荐命中。",
    sections: [
      {
        title: "当前检索参数",
        content: describeFields([
          ["关键词", query],
          ["学科", discipline],
        ]),
      },
      {
        title: "任务状态",
        content: describeTaskStatus({
          error,
          status,
          idleMessage: "尚未开始检索。",
        }),
      },
      {
        title: "最近检索结果",
        content: latestSearchResult
          ? [
              `候选文献：${latestSearchPapers.length}`,
              `推荐命中：${latestTopHits.length}`,
              topTitles.length > 0 ? `Top Hits：${topTitles.join("、")}` : null,
              latestSearchSummary ? `摘要：${latestSearchSummary.slice(0, 100)}${latestSearchSummary.length > 100 ? "..." : ""}` : null,
            ]
              .filter((item): item is string => Boolean(item))
              .join("；")
          : "执行后会在这里展示最近一次检索摘要。",
      },
    ],
    nextActions: [
      "先检索主题文献，再进入论文分析模块做结构化解析。",
      "将高相关结果作为写作上下文输入。",
      "在知识区打开完整检索 artifact 查看全部结果。",
    ],
    outputLanguage: "en",
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
            className="h-full"
          >
            <WorkspaceResultPanel viewModel={resultViewModel} />
          </motion.div>
        </div>
      </main>
    </div>
  );
}
