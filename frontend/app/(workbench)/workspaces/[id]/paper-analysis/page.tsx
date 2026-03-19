"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, FlaskConical } from "lucide-react";
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
import { findLatestArtifact, getArtifactContentRecord, readString, readStringList } from "@/lib/artifact-utils";
import { cn } from "@/lib/utils";

export default function PaperAnalysisPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceId = params.id as string;
  const { workspace, artifacts } = useWorkspaceStore();

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

  const { run, isRunning, status, error, result: latestTaskResult } = useFeatureTaskRunner({
    workspaceId,
    featureId: "paper_analysis",
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

  const latestAnalysisArtifact = useMemo(
    () => findLatestArtifact(artifacts, ["paper_analysis"]),
    [artifacts]
  );
  const latestAnalysisResult = useMemo(
    () => getArtifactContentRecord(latestAnalysisArtifact) ?? latestTaskResult,
    [latestAnalysisArtifact, latestTaskResult]
  );
  const latestSections =
    latestAnalysisResult?.sections && typeof latestAnalysisResult.sections === "object"
      ? (latestAnalysisResult.sections as Record<string, unknown>)
      : null;
  const latestRecommendations = readStringList(latestAnalysisResult?.recommendations, 3);
  const latestSummary = readString(latestAnalysisResult?.summary);
  const latestSectionNames = latestSections
    ? Object.keys(latestSections).slice(0, 4)
    : [];
  const resultViewModel: WorkspaceResultViewModel = createWorkspaceResultViewModel({
    summary: latestAnalysisResult
      ? "最近一次论文结构化分析已生成，可继续作为写作上下文使用。"
      : "本工作区用于生成方法、实验、结论和创新点的结构化分析。",
    sections: [
      {
        title: "当前分析参数",
        content: describeFields([
          ["Paper ID", paperId],
          ["标题", paperTitle],
        ]),
      },
      {
        title: "任务状态",
        content: describeTaskStatus({
          error,
          status,
          idleMessage: "尚未开始分析。",
        }),
      },
      {
        title: "最近分析结果",
        content: latestAnalysisResult
          ? [
              latestSectionNames.length > 0 ? `分析分区：${latestSectionNames.join("、")}` : null,
              latestRecommendations.length > 0 ? `建议：${latestRecommendations.join("、")}` : null,
              latestSummary ? `摘要：${latestSummary.slice(0, 120)}${latestSummary.length > 120 ? "..." : ""}` : null,
            ]
              .filter((item): item is string => Boolean(item))
              .join("；")
          : "执行后会在这里展示最近一次分析摘要。",
      },
    ],
    nextActions: [
      "输入论文标题或 Paper ID 后开始分析。",
      "将分析结果作为后续 SCI 写作上下文。",
      "在知识区查看完整分析 artifact。",
    ],
    outputLanguage: "en",
  });

  const handleAnalyze = async () => {
    if (!paperId.trim() && !paperTitle.trim()) return;
    await run({
      paper_id: paperId.trim() || undefined,
      paper_title: paperTitle.trim() || undefined,
      paper_abstract: paperAbstract.trim() || undefined,
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

            <ModelSelector
              id="paper-analysis-model"
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
            className="h-full"
          >
            <WorkspaceResultPanel viewModel={resultViewModel} />
          </motion.div>
        </div>
      </main>
    </div>
  );
}
