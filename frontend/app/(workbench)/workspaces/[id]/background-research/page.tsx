"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { BookOpen } from "lucide-react";
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
import { findLatestArtifact, getArtifactContentRecord, readNamedSections, readStringList } from "@/lib/artifact-utils";
import { cn } from "@/lib/utils";

const TIME_RANGE_OPTIONS = [
  { value: "近3年", label: "近3年" },
  { value: "近5年", label: "近5年" },
  { value: "近10年", label: "近10年" },
  { value: "2020-2024", label: "2020-2024" },
  { value: "2015-2024", label: "2015-2024" },
] as const;

export default function BackgroundResearchPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const workspaceId = params.id as string;
  const { workspace, artifacts } = useWorkspaceStore();
  const keywordsSeed = searchParams.get("keywords");
  const industryScopeSeed = searchParams.get("industry_scope");
  const timeRangeSeed = searchParams.get("time_range");

  const [keywords, setKeywords] = useState(() => keywordsSeed || "");
  const [industryScope, setIndustryScope] = useState(
    () => industryScopeSeed || "相关领域"
  );
  const [timeRange, setTimeRange] = useState(() =>
    TIME_RANGE_OPTIONS.some((item) => item.value === timeRangeSeed)
      ? (timeRangeSeed as string)
      : "近5年"
  );

  useEffect(() => {
    if (keywordsSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setKeywords(keywordsSeed);
    }
  }, [keywordsSeed]);

  useEffect(() => {
    if (industryScopeSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setIndustryScope(industryScopeSeed);
    }
  }, [industryScopeSeed]);

  useEffect(() => {
    if (TIME_RANGE_OPTIONS.some((item) => item.value === timeRangeSeed)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setTimeRange(timeRangeSeed as string);
    }
  }, [timeRangeSeed]);

  const { run, isRunning, status, error, result: latestTaskResult, runtime } = useFeatureTaskRunner({
    workspaceId,
    featureId: "background_research",
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

  const latestResearchArtifact = useMemo(
    () => findLatestArtifact(artifacts, ["background_research"]),
    [artifacts]
  );
  const latestResearchResult = useMemo(
    () => getArtifactContentRecord(latestResearchArtifact) ?? latestTaskResult,
    [latestResearchArtifact, latestTaskResult]
  );
  const latestSections = Array.isArray(latestResearchResult?.sections)
    ? latestResearchResult.sections
    : [];
  const latestSectionNames = readNamedSections(latestSections, 4);
  const latestReferences = Array.isArray(latestResearchResult?.references)
    ? latestResearchResult.references
    : [];
  const latestReferenceTitles = readStringList(
    latestReferences.map((item: unknown) =>
      item && typeof item === "object"
        ? (item as Record<string, unknown>).title
        : item
    ),
    3
  );
  const resultViewModel: WorkspaceResultViewModel = createWorkspaceResultViewModel({
    summary: latestResearchResult
      ? "最近一次背景调研已生成，可继续为申报书大纲提供支撑。"
      : "本工作区用于调研项目背景、行业现状和可行技术方向。",
    sections: [
      {
        title: "当前配置",
        content: describeFields([
          ["关键词", keywords],
          ["行业范围", industryScope],
          ["时间范围", timeRange],
        ]),
      },
      {
        title: "任务状态",
        content: describeTaskStatus({
          error,
          status,
          idleMessage: "尚未开始调研。",
        }),
      },
      {
        title: "最近调研结果",
        content: latestResearchResult
          ? [
              `章节数：${latestSections.length}`,
              latestSectionNames.length > 0 ? `核心章节：${latestSectionNames.join("、")}` : null,
              latestReferenceTitles.length > 0 ? `参考文献：${latestReferenceTitles.join("、")}` : null,
            ]
              .filter((item): item is string => Boolean(item))
              .join("；")
          : "执行后会在这里展示最近一次调研摘要。",
      },
    ],
    nextActions: [
      "先完成背景调研，再进入 proposal-outline。",
      "在知识区审阅完整调研报告并补充数据。",
      "将关键结论写入申报书立项依据部分。",
    ],
    outputLanguage: "zh",
  });

  useEffect(() => {
    if (workspace && !keywords) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync from async store
      setKeywords((workspace.description || workspace.name || "").toString());
    }
  }, [workspace, keywords]);

  const handleGenerate = async () => {
    if (!keywords.trim()) return;
    await run({
      keywords: keywords.trim(),
      industry_scope: industryScope,
      time_range: timeRange,
      model_id: selectedModel || undefined,
    });
  };

  return (
    <FeatureWorkbenchShell
      workspaceId={workspaceId}
      title="背景调研"
      description="调研项目背景和研究现状"
      icon={BookOpen}
      iconBgClass="bg-emerald-500/10"
      iconClass="text-emerald-600 dark:text-emerald-400"
      sidebarTitle="调研配置"
      sidebar={
        <div className="space-y-4">
            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                主题关键词
              </label>
              <input
                type="text"
                placeholder="输入主题关键词..."
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                行业范围
              </label>
              <input
                type="text"
                placeholder="如：人工智能、生物医药..."
                value={industryScope}
                onChange={(e) => setIndustryScope(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                时间范围
              </label>
              <select
                value={timeRange}
                onChange={(e) => setTimeRange(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              >
                {TIME_RANGE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <ModelSelector
              id="background-research-model"
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
              onClick={handleGenerate}
              disabled={isRunning}
            >
              {isRunning ? "正在调研..." : "开始调研"}
            </button>

            <TaskFeedbackBanner
              isRunning={isRunning}
              status={status}
              error={error}
              onRetry={handleGenerate}
            />
        </div>
      }
    >
      <TaskRuntimePanel
        runtime={runtime}
        isRunning={isRunning}
        status={status}
        error={error}
        title="背景调研运行面板"
        emptyDescription="执行后，这里会显示调研范围、背景分析和报告整理阶段。"
      />
      <WorkspaceResultPanel viewModel={resultViewModel} />
    </FeatureWorkbenchShell>
  );
}
