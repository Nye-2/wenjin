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
  WorkspaceResultPanel,
} from "@/components/workspace";
import { ModelSelector } from "@/components/workspace/ModelSelector";
import { useModelSelection } from "@/hooks/useModelSelection";
import type { WorkspaceResultViewModel } from "@/components/workspace/WorkspaceResultPanel";
import {
  createWorkspaceResultViewModel,
  describeFields,
  describeTaskStatus,
} from "@/lib/workspace-result";
import {
  findLatestArtifact,
  getArtifactContentRecord,
  readString,
} from "@/lib/artifact-utils";
import { cn } from "@/lib/utils";

export default function DeepResearchPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const workspaceId = params.id as string;
  const { workspace, artifacts, fetchArtifacts } = useWorkspaceStore();
  const topicSeed = searchParams.get("topic");

  const [topic, setTopic] = useState(() => topicSeed || "");
  const {
    run,
    isRunning,
    status,
    error,
    result: latestTaskResult,
    runtime,
  } = useFeatureTaskRunner({
    workspaceId,
    featureId: "deep_research",
  });
  const {
    models: availableModels,
    selectedModel,
    setSelectedModel,
    isLoading: isModelLoading,
    loadError: modelLoadError,
  } = useModelSelection({
    purpose: "chat",
    persistenceKey: `workspace:${workspaceId}:model:chat`,
  });

  useEffect(() => {
    if (topicSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setTopic(topicSeed);
    }
  }, [topicSeed]);

  useEffect(() => {
    if (workspace && !topic) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync from async store
      setTopic((workspace.description || workspace.name || "").toString());
    }
  }, [workspace, topic]);

  useEffect(() => {
    if (!workspaceId) {
      return;
    }
    void fetchArtifacts(workspaceId);
  }, [workspaceId, fetchArtifacts]);

  const latestReportArtifact = useMemo(
    () => findLatestArtifact(artifacts, ["deep_research_report"]),
    [artifacts]
  );
  const latestReport = useMemo(
    () => getArtifactContentRecord(latestReportArtifact),
    [latestReportArtifact]
  );
  const latestResult = useMemo(
    () =>
      latestTaskResult && typeof latestTaskResult === "object"
        ? (latestTaskResult as Record<string, unknown>)
        : null,
    [latestTaskResult]
  );
  const corpus = useMemo(
    () =>
      latestResult?.corpus && typeof latestResult.corpus === "object"
        ? (latestResult.corpus as Record<string, unknown>)
        : latestReport?.corpus && typeof latestReport.corpus === "object"
          ? (latestReport.corpus as Record<string, unknown>)
          : null,
    [latestResult, latestReport]
  );
  const discovery = useMemo(
    () =>
      latestResult?.discovery && typeof latestResult.discovery === "object"
        ? (latestResult.discovery as Record<string, unknown>)
        : latestReport?.discovery && typeof latestReport.discovery === "object"
          ? (latestReport.discovery as Record<string, unknown>)
        : null,
    [latestResult, latestReport]
  );
  const ideaItems = useMemo(
    () =>
      Array.isArray(latestResult?.ideas)
        ? latestResult.ideas
        : Array.isArray(latestReport?.ideas)
          ? latestReport.ideas
          : [],
    [latestResult, latestReport]
  );
  const gapItems = useMemo(
    () =>
      Array.isArray(latestResult?.gaps)
        ? latestResult.gaps
        : Array.isArray(latestReport?.gaps)
          ? latestReport.gaps
          : [],
    [latestResult, latestReport]
  );
  const reviewPapers = useMemo(
    () => (Array.isArray(corpus?.top_papers) ? corpus.top_papers : []),
    [corpus]
  );

  const ideaTitles = useMemo(
    () =>
      ideaItems
        .map((item) =>
          item && typeof item === "object"
            ? readString((item as Record<string, unknown>).title)
            : readString(item)
        )
        .filter((item): item is string => Boolean(item))
        .slice(0, 3),
    [ideaItems]
  );
  const gapHighlights = useMemo(
    () =>
      gapItems
        .map((item) =>
          item && typeof item === "object"
            ? readString((item as Record<string, unknown>).description)
            : readString(item)
        )
        .filter((item): item is string => Boolean(item))
        .slice(0, 3),
    [gapItems]
  );
  const reviewCount =
    typeof corpus?.paper_count === "number" ? corpus.paper_count : reviewPapers.length;
  const seminalCount = Array.isArray(discovery?.seminal_works)
    ? discovery.seminal_works.length
    : 0;
  const recentCount = Array.isArray(discovery?.recent_works)
    ? discovery.recent_works.length
    : 0;

  const resultViewModel: WorkspaceResultViewModel =
    createWorkspaceResultViewModel({
      summary:
        latestResult || latestReport
          ? "最近一次深度调研报告已生成，可继续沉淀到文献管理、论文大纲和正文写作。"
          : "本工作区用于执行深度调研，产出统一的调研报告、研究空白和研究创意。",
      sections: [
        {
          title: "当前配置",
          content: describeFields([
            ["研究主题", topic],
            ["工作区", workspace?.name || null],
          ]),
        },
        {
          title: "任务状态",
          content: describeTaskStatus({
            error,
            status,
            idleMessage: "尚未开始深度调研。",
          }),
        },
        {
          title: "最近调研结果",
          content:
            latestResult || latestReport
              ? [
                  reviewCount > 0 ? `调研文献：${reviewCount}` : null,
                  seminalCount > 0 ? `经典文献：${seminalCount}` : null,
                  recentCount > 0 ? `近期文献：${recentCount}` : null,
                  gapItems.length > 0 ? `研究空白：${gapItems.length}` : null,
                  ideaItems.length > 0 ? `研究创意：${ideaItems.length}` : null,
                  ideaTitles.length > 0 ? `创意示例：${ideaTitles.join("、")}` : null,
                  gapHighlights.length > 0 ? `空白示例：${gapHighlights.join("、")}` : null,
                ]
                  .filter((item): item is string => Boolean(item))
                  .join("；")
              : "执行后会在这里展示最近一次深度调研摘要。",
        },
      ],
      nextActions: [
        "先执行 Deep Research，再把结果导入文献管理或论文写作。",
        "重点关注研究空白与创意条目，用于后续大纲规划。",
        "调研完成后在 Chat 中继续追问某个方向的细化方案。",
      ],
      outputLanguage: "zh",
    });

  const handleRun = async () => {
    if (!topic.trim()) return;
    await run({
      topic: topic.trim(),
      query: topic.trim(),
      model_id: selectedModel || undefined,
    });
  };

  return (
    <FeatureWorkbenchShell
      workspaceId={workspaceId}
      title="Deep Research"
      description="深度文献调研与研究创意探索"
      icon={FlaskConical}
      iconBgClass="bg-blue-500/10"
      iconClass="text-blue-600 dark:text-blue-400"
      sidebarTitle="调研配置"
      sidebarWidthClassName="lg:w-96"
      sidebar={
        <div className="space-y-4">
          <div>
            <label className="block text-xs text-[var(--text-muted)] mb-1">
              研究主题
            </label>
            <textarea
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              placeholder="例如：面向边缘设备的轻量级图像分割网络"
              rows={4}
              className="w-full resize-none rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            />
          </div>

          <ModelSelector
            id="deep-research-model"
            label="推理模型"
            models={availableModels}
            selectedModel={selectedModel}
            onChange={setSelectedModel}
            isLoading={isModelLoading}
            loadError={modelLoadError}
            disabled={isRunning}
          />

          <button
            onClick={handleRun}
            disabled={isRunning}
            className={cn(
              "inline-flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium",
              "bg-blue-600 text-white transition-colors hover:bg-blue-700",
              isRunning && "cursor-not-allowed opacity-60"
            )}
          >
            {isRunning ? (
              <>
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                正在执行 Deep Research...
              </>
            ) : (
              <>
                <FlaskConical className="h-4 w-4" />
                开始 Deep Research
              </>
            )}
          </button>

          <p className="text-xs leading-5 text-[var(--text-muted)]">
            运行完成后，可在最近产出、Knowledge 和 Chat 中继续复用调研结果。
          </p>

          <TaskFeedbackBanner
            isRunning={isRunning}
            status={status}
            error={error}
            onRetry={handleRun}
          />
        </div>
      }
    >
      <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-6">
        <h2 className="mb-2 text-xl font-semibold text-[var(--text-primary)]">
          Deep Research 工作区
        </h2>
        <p className="max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
          输入论文研究主题后，系统会串联文献发现、研究空白挖掘、创意生成与交叉验证，
          产出文献综述、研究空白分析和研究创意，并把结果沉淀为 workspace 可复用知识。
        </p>
      </div>

      <TaskRuntimePanel
        runtime={runtime}
        isRunning={isRunning}
        status={status}
        error={error}
        title="Deep Research 运行面板"
        emptyDescription="执行后，这里会实时显示阶段推进、候选论文、研究空白和创意草案。"
      />
      <WorkspaceResultPanel viewModel={resultViewModel} />
    </FeatureWorkbenchShell>
  );
}
