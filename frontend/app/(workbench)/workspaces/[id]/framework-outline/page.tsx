"use client";

import { useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { ListChecks } from "lucide-react";
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
  getArtifactPaperTitle,
  getArtifactTopic,
  resolveFeatureSourceArtifact,
  summarizeArtifactContext,
} from "@/lib/workspace-feature-actions";
import { cn } from "@/lib/utils";

export default function FrameworkOutlinePage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const workspaceId = params.id as string;
  const { workspace, artifacts } = useWorkspaceStore();

  const sourceArtifactId = searchParams.get("source_artifact_id");
  const sourceArtifact = useMemo(
    () =>
      resolveFeatureSourceArtifact(
        "framework_outline",
        artifacts,
        sourceArtifactId
      ),
    [artifacts, sourceArtifactId]
  );
  const sourceSummary = useMemo(
    () => summarizeArtifactContext(sourceArtifact),
    [sourceArtifact]
  );

  const [paperTitleInput, setPaperTitleInput] = useState<string | null>(() =>
    searchParams.get("paper_title")
  );
  const [topicInput, setTopicInput] = useState<string | null>(() =>
    searchParams.get("topic")
  );
  const defaultPaperTitle = useMemo(
    () =>
      getArtifactPaperTitle(sourceArtifact) ??
      (workspace?.name || workspace?.description || "").toString(),
    [sourceArtifact, workspace]
  );
  const defaultTopic = useMemo(
    () =>
      getArtifactTopic(sourceArtifact) ??
      (workspace?.description || workspace?.name || "").toString(),
    [sourceArtifact, workspace]
  );
  const paperTitle = paperTitleInput ?? defaultPaperTitle;
  const topic = topicInput ?? defaultTopic;

  const {
    run,
    isRunning,
    status,
    error,
    result: latestTaskResult,
    runtime,
  } = useFeatureTaskRunner({
    workspaceId,
    featureId: "framework_outline",
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

  const latestOutlineArtifact = useMemo(
    () => findLatestArtifact(artifacts, ["framework_outline"]),
    [artifacts]
  );
  const latestOutlineResult = useMemo(
    () => getArtifactContentRecord(latestOutlineArtifact) ?? latestTaskResult,
    [latestOutlineArtifact, latestTaskResult]
  );
  const latestKeywords = readStringList(latestOutlineResult?.keywords, 5);
  const latestSectionTitles = readNamedSections(latestOutlineResult?.sections, 6);
  const latestContributions = readStringList(
    latestOutlineResult?.contributions,
    3
  );
  const latestAbstract = readString(latestOutlineResult?.abstract);

  const resultViewModel: WorkspaceResultViewModel =
    createWorkspaceResultViewModel({
      summary: latestOutlineResult
        ? "最近一次已生成摘要与章节框架，可直接进入 writing 分章节写作。"
        : "本模块用于生成论文摘要、关键词和可直接展开正文的章节框架。",
      sections: [
        {
          title: "当前配置",
          content: describeFields([
            ["论文标题", paperTitle],
            ["研究主题", topic],
            ["上下文 artifact", sourceArtifact?.title || sourceArtifact?.type || null],
          ]),
        },
        {
          title: "任务状态",
          content: describeTaskStatus({
            error,
            status,
            idleMessage: "尚未开始生成框架。",
          }),
        },
        {
          title: "最近框架结果",
          content: latestOutlineResult
            ? [
                latestKeywords.length > 0
                  ? `关键词：${latestKeywords.join("、")}`
                  : null,
                latestSectionTitles.length > 0
                  ? `章节：${latestSectionTitles.join("、")}`
                  : null,
                latestContributions.length > 0
                  ? `贡献：${latestContributions.join("、")}`
                  : null,
                latestAbstract
                  ? `摘要：${latestAbstract.slice(0, 120)}${
                      latestAbstract.length > 120 ? "..." : ""
                    }`
                  : null,
              ]
                .filter((item): item is string => Boolean(item))
                .join("；")
            : "执行后会在这里展示最近一次框架摘要。",
        },
      ],
      nextActions: [
        "确认题目和研究主题后生成摘要与章节框架。",
        "把框架产出送入 writing 模块按章节展开写作。",
        "在知识区继续校正关键词、贡献点和 section focus。",
      ],
      outputLanguage: "en",
    });

  const handleGenerate = async () => {
    if (!paperTitle.trim() || !topic.trim()) {
      return;
    }
    await run({
      paper_title: paperTitle.trim(),
      topic: topic.trim(),
      context_artifact_ids: sourceArtifact ? [sourceArtifact.id] : undefined,
      model_id: selectedModel || undefined,
    });
  };

  return (
    <FeatureWorkbenchShell
      workspaceId={workspaceId}
      title="框架与摘要"
      description="生成摘要、关键词和整篇论文的章节框架"
      icon={ListChecks}
      iconBgClass="bg-blue-500/10"
      iconClass="text-blue-600 dark:text-blue-400"
      sidebarTitle="框架配置"
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
              论文标题
            </label>
            <input
              type="text"
              placeholder="输入论文标题"
              value={paperTitle}
              onChange={(event) => setPaperTitleInput(event.target.value)}
              className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            />
          </div>

          <div>
            <label className="block text-xs text-[var(--text-muted)] mb-1">
              研究主题
            </label>
            <textarea
              rows={4}
              placeholder="输入研究问题或主题定位"
              value={topic}
              onChange={(event) => setTopicInput(event.target.value)}
              className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            />
          </div>

          <ModelSelector
            id="framework-outline-model"
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
              "w-full py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors",
              isRunning && "opacity-60 cursor-not-allowed"
            )}
          >
            {isRunning ? "生成中..." : "生成框架"}
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
        title="框架生成运行面板"
        emptyDescription="执行后，这里会展示研究定位、章节规划和摘要生成阶段。"
      />
      <WorkspaceResultPanel viewModel={resultViewModel} />
    </FeatureWorkbenchShell>
  );
}
