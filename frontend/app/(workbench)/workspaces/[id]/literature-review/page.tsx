"use client";

import { useMemo, useState } from "react";
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
import {
  createWorkspaceResultViewModel,
  describeFields,
  describeTaskStatus,
} from "@/lib/workspace-result";
import {
  findLatestArtifact,
  getArtifactContentRecord,
  readNamedSections,
  readString,
  readStringList,
} from "@/lib/artifact-utils";
import {
  getArtifactDiscipline,
  getArtifactTopic,
  resolveFeatureSourceArtifact,
  summarizeArtifactContext,
} from "@/lib/workspace-feature-actions";
import { cn } from "@/lib/utils";

export default function LiteratureReviewPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const workspaceId = params.id as string;
  const { workspace, artifacts } = useWorkspaceStore();

  const sourceArtifactId = searchParams.get("source_artifact_id");
  const sourceArtifact = useMemo(
    () =>
      resolveFeatureSourceArtifact(
        "literature_review",
        artifacts,
        sourceArtifactId
      ),
    [artifacts, sourceArtifactId]
  );
  const sourceSummary = useMemo(
    () => summarizeArtifactContext(sourceArtifact),
    [sourceArtifact]
  );

  const [topicInput, setTopicInput] = useState<string | null>(() =>
    searchParams.get("topic")
  );
  const [disciplineInput, setDisciplineInput] = useState<string | null>(() =>
    searchParams.get("discipline")
  );
  const defaultTopic = useMemo(
    () =>
      getArtifactTopic(sourceArtifact) ??
      (workspace?.description || workspace?.name || "").toString(),
    [sourceArtifact, workspace]
  );
  const defaultDiscipline = useMemo(
    () =>
      getArtifactDiscipline(sourceArtifact, workspace) ??
      (workspace?.discipline || "").toString(),
    [sourceArtifact, workspace]
  );
  const topic = topicInput ?? defaultTopic;
  const discipline = disciplineInput ?? defaultDiscipline;

  const {
    run,
    isRunning,
    status,
    error,
    result: latestTaskResult,
    runtime,
  } = useFeatureTaskRunner({
    workspaceId,
    featureId: "literature_review",
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

  const latestReviewArtifact = useMemo(
    () => findLatestArtifact(artifacts, ["literature_review"]),
    [artifacts]
  );
  const latestReviewResult = useMemo(
    () => getArtifactContentRecord(latestReviewArtifact) ?? latestTaskResult,
    [latestReviewArtifact, latestTaskResult]
  );
  const latestSections = Array.isArray(latestReviewResult?.sections)
    ? latestReviewResult.sections
    : [];
  const latestSectionNames = readNamedSections(latestSections, 4);
  const latestGapList = readStringList(latestReviewResult?.research_gaps, 3);
  const latestKeyPaperTitles = readStringList(
    Array.isArray(latestReviewResult?.key_papers)
      ? latestReviewResult.key_papers.map((item: unknown) =>
          item && typeof item === "object"
            ? (item as Record<string, unknown>).title
            : item
        )
      : [],
    3
  );
  const latestSummary = readString(latestReviewResult?.summary);

  const resultViewModel: WorkspaceResultViewModel =
    createWorkspaceResultViewModel({
      summary: latestReviewResult
        ? "最近一次文献综述已生成，可直接为 framework-outline 和写作模块提供上下文。"
        : "本模块用于把检索与分析结果整合为结构化 SCI 文献综述。",
      sections: [
        {
          title: "当前配置",
          content: describeFields([
            ["主题", topic],
            ["学科", discipline],
            ["上下文 artifact", sourceArtifact?.title || sourceArtifact?.type || null],
          ]),
        },
        {
          title: "任务状态",
          content: describeTaskStatus({
            error,
            status,
            idleMessage: "尚未开始生成综述。",
          }),
        },
        {
          title: "最近综述结果",
          content: latestReviewResult
            ? [
                `章节数：${latestSections.length}`,
                latestSectionNames.length > 0
                  ? `核心章节：${latestSectionNames.join("、")}`
                  : null,
                latestKeyPaperTitles.length > 0
                  ? `关键论文：${latestKeyPaperTitles.join("、")}`
                  : null,
                latestGapList.length > 0
                  ? `研究空白：${latestGapList.join("、")}`
                  : null,
                latestSummary
                  ? `摘要：${latestSummary.slice(0, 120)}${
                      latestSummary.length > 120 ? "..." : ""
                    }`
                  : null,
              ]
                .filter((item): item is string => Boolean(item))
                .join("；")
            : "执行后会在这里展示最近一次文献综述摘要。",
        },
      ],
      nextActions: [
        "先确认主题和上下文来源，再生成综述。",
        "将综述直接送入 framework-outline 生成摘要与章节框架。",
        "在知识区审阅 key papers、gaps 和 next actions。",
      ],
      outputLanguage: "en",
    });

  const handleGenerate = async () => {
    if (!topic.trim()) {
      return;
    }
    await run({
      topic: topic.trim(),
      discipline: discipline.trim() || undefined,
      context_artifact_ids: sourceArtifact ? [sourceArtifact.id] : undefined,
      model_id: selectedModel || undefined,
    });
  };

  return (
    <FeatureWorkbenchShell
      workspaceId={workspaceId}
      title="文献综述"
      description="整合检索结果与上下文，生成结构化 SCI 文献综述"
      icon={BookOpen}
      iconBgClass="bg-cyan-500/10"
      iconClass="text-cyan-600 dark:text-cyan-400"
      sidebarTitle="综述配置"
      sidebar={
        <div className="space-y-4">
          {sourceArtifact && (
            <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-[var(--text-muted)]">
                已挂载上下文
              </p>
              <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">
                {sourceArtifact.title || sourceArtifact.type}
              </p>
              {sourceSummary && (
                <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                  {sourceSummary}
                </p>
              )}
            </div>
          )}

          <div>
            <label className="block text-xs text-[var(--text-muted)] mb-1">
              研究主题
            </label>
            <input
              type="text"
              placeholder="输入综述主题"
              value={topic}
              onChange={(event) => setTopicInput(event.target.value)}
              className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
            />
          </div>

          <div>
            <label className="block text-xs text-[var(--text-muted)] mb-1">
              学科领域（可选）
            </label>
            <input
              type="text"
              placeholder="如：computer_science"
              value={discipline}
              onChange={(event) => setDisciplineInput(event.target.value)}
              className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
            />
          </div>

          <ModelSelector
            id="literature-review-model"
            label="生成模型"
            models={availableModels}
            selectedModel={selectedModel}
            onChange={setSelectedModel}
            isLoading={isModelLoading}
            loadError={modelLoadError}
            disabled={isRunning}
          />

          <button
            type="button"
            onClick={handleGenerate}
            disabled={isRunning}
            className={cn(
              "w-full py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-700 transition-colors",
              isRunning && "opacity-60 cursor-not-allowed"
            )}
          >
            {isRunning ? "生成中..." : "生成综述"}
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
        title="文献综述运行面板"
        emptyDescription="执行后，这里会展示文献整理、观点综合和综述成稿阶段。"
      />
      <WorkspaceResultPanel viewModel={resultViewModel} />
    </FeatureWorkbenchShell>
  );
}
