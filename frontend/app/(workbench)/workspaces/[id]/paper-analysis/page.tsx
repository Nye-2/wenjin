"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { FlaskConical } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import {
  FeatureWorkbenchShell,
  TaskFeedbackBanner,
  TaskRuntimePanel,
} from "@/components/workspace";
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
  const searchParams = useSearchParams();
  const workspaceId = params.id as string;
  const { workspace, artifacts } = useWorkspaceStore();
  const paperIdSeed = searchParams.get("paper_id");
  const paperTitleSeed = searchParams.get("paper_title");
  const paperAbstractSeed = searchParams.get("paper_abstract");

  const [paperId, setPaperId] = useState(
    () => paperIdSeed || ""
  );
  const [paperTitle, setPaperTitle] = useState(
    () => paperTitleSeed || ""
  );
  const [paperAbstract, setPaperAbstract] = useState(
    () => paperAbstractSeed || ""
  );

  useEffect(() => {
    if (paperIdSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setPaperId(paperIdSeed);
    }
  }, [paperIdSeed]);

  useEffect(() => {
    if (paperTitleSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setPaperTitle(paperTitleSeed);
    }
  }, [paperTitleSeed]);

  useEffect(() => {
    if (paperAbstractSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setPaperAbstract(paperAbstractSeed);
    }
  }, [paperAbstractSeed]);

  useEffect(() => {
    if (workspace && !paperTitle) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync from async store
      setPaperTitle((workspace.description || workspace.name || "").toString());
    }
  }, [workspace, paperTitle]);

  const { run, isRunning, status, error, result: latestTaskResult, runtime } = useFeatureTaskRunner({
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

  useEffect(() => {
    const latestPaperId = readString(latestAnalysisResult?.paper_id);
    if (latestPaperId && !paperId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest analysis input when route seed is absent
      setPaperId(latestPaperId);
    }
  }, [latestAnalysisResult, paperId]);

  useEffect(() => {
    const latestPaperTitle = readString(latestAnalysisResult?.paper_title);
    if (latestPaperTitle && !paperTitle) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest analysis input when route seed is absent
      setPaperTitle(latestPaperTitle);
    }
  }, [latestAnalysisResult, paperTitle]);

  useEffect(() => {
    const latestPaperAbstract = readString(latestAnalysisResult?.paper_abstract);
    if (latestPaperAbstract && !paperAbstract) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest analysis input when route seed is absent
      setPaperAbstract(latestPaperAbstract);
    }
  }, [latestAnalysisResult, paperAbstract]);

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
    <FeatureWorkbenchShell
      workspaceId={workspaceId}
      title="论文分析"
      description="生成方法/实验/结论/创新点结构化分析"
      icon={FlaskConical}
      iconBgClass="bg-fuchsia-500/10"
      iconClass="text-fuchsia-600 dark:text-fuchsia-400"
      sidebarTitle="分析参数"
      sidebar={
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
      }
    >
      <TaskRuntimePanel
        runtime={runtime}
        isRunning={isRunning}
        status={status}
        error={error}
        title="论文分析运行面板"
        emptyDescription="执行后，这里会显示分析阶段、论文上下文和结构化分析分区。"
      />
      <WorkspaceResultPanel viewModel={resultViewModel} />
    </FeatureWorkbenchShell>
  );
}
