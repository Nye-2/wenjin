"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { Search } from "lucide-react";
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
import { findLatestArtifact, getArtifactContentRecord, readNamedSections } from "@/lib/artifact-utils";
import { cn } from "@/lib/utils";

const REPORT_TYPES = [
  { value: "opening_report", label: "开题报告" },
  { value: "literature_review", label: "文献综述" },
  { value: "feasibility_analysis", label: "可行性分析" },
] as const;

type ReportTypeValue = (typeof REPORT_TYPES)[number]["value"];

export default function OpeningResearchPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const workspaceId = params.id as string;
  const { workspace, artifacts } = useWorkspaceStore();
  const topicSeed = searchParams.get("topic");
  const reportTypeSeed = searchParams.get("report_type");

  const [topic, setTopic] = useState(() => topicSeed || "");
  const [reportType, setReportType] = useState<ReportTypeValue>(() =>
    REPORT_TYPES.some((item) => item.value === reportTypeSeed)
      ? (reportTypeSeed as ReportTypeValue)
      : "opening_report"
  );

  const { run, isRunning, status, error, result: latestTaskResult, runtime } = useFeatureTaskRunner({
    workspaceId,
    featureId: "opening_research",
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

  const latestOpeningArtifact = useMemo(
    () => findLatestArtifact(artifacts, ["opening_report", "literature_review", "feasibility_analysis"]),
    [artifacts]
  );
  const latestOpeningResult = useMemo(
    () => getArtifactContentRecord(latestOpeningArtifact) ?? latestTaskResult,
    [latestOpeningArtifact, latestTaskResult]
  );
  const latestSections = Array.isArray(latestOpeningResult?.sections)
    ? latestOpeningResult.sections
    : [];
  const latestSectionNames = readNamedSections(latestSections, 4);
  const resultViewModel: WorkspaceResultViewModel = createWorkspaceResultViewModel({
    summary: latestOpeningResult
      ? "最近一次开题调研结果已生成，可作为论文写作前的研究准备。"
      : "本工作区用于生成开题报告、文献综述和可行性分析。",
    sections: [
      {
        title: "当前配置",
        content: describeFields([
          ["主题", topic],
          ["报告类型", reportType],
        ]),
      },
      {
        title: "任务状态",
        content: describeTaskStatus({
          error,
          status,
          idleMessage: "尚未开始生成报告。",
        }),
      },
      {
        title: "最近报告结果",
        content: latestOpeningResult
          ? [
              `章节数：${latestSections.length}`,
              latestSectionNames.length > 0 ? `核心章节：${latestSectionNames.join("、")}` : null,
              latestOpeningResult.research_analysis ? "已包含研究现状分析。" : null,
              latestOpeningResult.methodology_plan ? "已包含方法规划。" : null,
            ]
              .filter((item): item is string => Boolean(item))
              .join("；")
          : "执行后会在这里展示最近一次报告摘要。",
      },
    ],
    nextActions: [
      "根据课题阶段选择报告类型后执行生成。",
      "将调研结论带入 thesis-writing 或 figure-generation。",
      "在知识区查看完整报告章节。",
    ],
    outputLanguage: "zh",
  });

  useEffect(() => {
    if (topicSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setTopic(topicSeed);
    }
  }, [topicSeed]);

  useEffect(() => {
    if (REPORT_TYPES.some((item) => item.value === reportTypeSeed)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setReportType(reportTypeSeed as ReportTypeValue);
    }
  }, [reportTypeSeed]);

  useEffect(() => {
    if (workspace && !topic) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync from async store
      setTopic((workspace.description || workspace.name || "").toString());
    }
  }, [workspace, topic]);

  const handleGenerate = async () => {
    if (!topic.trim()) return;
    await run({
      topic: topic.trim(),
      report_type: reportType,
      model_id: selectedModel || undefined,
    });
  };

  return (
    <FeatureWorkbenchShell
      workspaceId={workspaceId}
      title="开题调研"
      description="生成开题报告、文献综述、可行性分析"
      icon={Search}
      iconBgClass="bg-amber-500/10"
      iconClass="text-amber-600 dark:text-amber-400"
      sidebarTitle="报告配置"
      sidebar={
        <div className="space-y-4">
            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                研究主题
              </label>
              <input
                type="text"
                placeholder="输入研究主题..."
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                报告类型
              </label>
              <div className="space-y-2">
                {REPORT_TYPES.map((type) => (
                  <label
                    key={type.value}
                    className="flex items-center gap-2 p-2 bg-[var(--bg-elevated)] rounded-lg cursor-pointer hover:bg-[var(--bg-muted)]"
                  >
                    <input
                      type="radio"
                      name="report_type"
                      value={type.value}
                      checked={reportType === type.value}
                      onChange={() => setReportType(type.value)}
                      className="text-amber-500"
                    />
                    <span className="text-sm text-[var(--text-primary)]">
                      {type.label}
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <ModelSelector
              id="opening-research-model"
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
                "w-full py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 transition-colors",
                isRunning && "opacity-60 cursor-not-allowed"
              )}
              onClick={handleGenerate}
              disabled={isRunning}
            >
              {isRunning ? "正在生成..." : "生成报告"}
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
        title="开题调研运行面板"
        emptyDescription="执行后，这里会显示研究现状、方法规划和报告章节生成的过程。"
      />
      <WorkspaceResultPanel viewModel={resultViewModel} />
    </FeatureWorkbenchShell>
  );
}
