"use client";

import { useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { Lightbulb } from "lucide-react";
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
  readString,
  readStringList,
} from "@/lib/artifact-utils";
import {
  getArtifactAbstract,
  getArtifactDiscipline,
  getArtifactPaperTitle,
  resolveFeatureSourceArtifact,
  summarizeArtifactContext,
} from "@/lib/workspace-feature-actions";
import { cn } from "@/lib/utils";

export default function JournalRecommendPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const workspaceId = params.id as string;
  const { workspace, artifacts } = useWorkspaceStore();

  const sourceArtifactId = searchParams.get("source_artifact_id");
  const sourceArtifact = useMemo(
    () =>
      resolveFeatureSourceArtifact(
        "journal_recommend",
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
  const [disciplineInput, setDisciplineInput] = useState<string | null>(() =>
    searchParams.get("discipline")
  );
  const [abstractInput, setAbstractInput] = useState<string | null>(null);
  const defaultPaperTitle = useMemo(
    () =>
      getArtifactPaperTitle(sourceArtifact) ??
      (workspace?.name || workspace?.description || "").toString(),
    [sourceArtifact, workspace]
  );
  const defaultDiscipline = useMemo(
    () =>
      getArtifactDiscipline(sourceArtifact, workspace) ??
      (workspace?.discipline || "").toString(),
    [sourceArtifact, workspace]
  );
  const defaultAbstract = useMemo(
    () => getArtifactAbstract(sourceArtifact) ?? "",
    [sourceArtifact]
  );
  const paperTitle = paperTitleInput ?? defaultPaperTitle;
  const discipline = disciplineInput ?? defaultDiscipline;
  const abstract = abstractInput ?? defaultAbstract;

  const {
    run,
    isRunning,
    status,
    error,
    result: latestTaskResult,
    runtime,
  } = useFeatureTaskRunner({
    workspaceId,
    featureId: "journal_recommend",
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

  const latestSummaryArtifact = useMemo(
    () => findLatestArtifact(artifacts, ["summary"]),
    [artifacts]
  );
  const latestRecommendResult = useMemo(
    () => getArtifactContentRecord(latestSummaryArtifact) ?? latestTaskResult,
    [latestSummaryArtifact, latestTaskResult]
  );
  const latestProfile = readString(latestRecommendResult?.paper_profile);
  const latestJournalNames = readStringList(
    Array.isArray(latestRecommendResult?.journals)
      ? latestRecommendResult.journals.map((item: unknown) =>
          item && typeof item === "object"
            ? (item as Record<string, unknown>).name
            : item
        )
      : [],
    4
  );
  const latestSubmissionNotes = readStringList(
    latestRecommendResult?.submission_notes,
    3
  );

  const resultViewModel: WorkspaceResultViewModel =
    createWorkspaceResultViewModel({
      summary: latestRecommendResult
        ? "最近一次期刊推荐已生成，可据此制定投稿顺序和摘要改写策略。"
        : "本模块用于根据论文画像推荐潜在投稿期刊并附带投稿建议。",
      sections: [
        {
          title: "当前配置",
          content: describeFields([
            ["论文标题", paperTitle],
            ["学科", discipline],
            ["摘要长度", abstract.length > 0 ? `${abstract.length} 字符` : null],
          ]),
        },
        {
          title: "任务状态",
          content: describeTaskStatus({
            error,
            status,
            idleMessage: "尚未开始推荐期刊。",
          }),
        },
        {
          title: "最近推荐结果",
          content: latestRecommendResult
            ? [
                latestJournalNames.length > 0
                  ? `候选期刊：${latestJournalNames.join("、")}`
                  : null,
                latestSubmissionNotes.length > 0
                  ? `投稿建议：${latestSubmissionNotes.join("、")}`
                  : null,
                latestProfile
                  ? `论文画像：${latestProfile.slice(0, 120)}${
                      latestProfile.length > 120 ? "..." : ""
                    }`
                  : null,
              ]
                .filter((item): item is string => Boolean(item))
                .join("；")
            : "执行后会在这里展示最近一次期刊推荐摘要。",
        },
      ],
      nextActions: [
        "尽量挂载最新摘要或框架 artifact 后再推荐期刊。",
        "结合推荐结果回头优化摘要和贡献表述。",
        "优先比较 Top 3 期刊的 fit、风险和投稿周期。",
      ],
      outputLanguage: "en",
    });

  const handleGenerate = async () => {
    if (!paperTitle.trim() || !abstract.trim()) {
      return;
    }
    await run({
      paper_title: paperTitle.trim(),
      abstract: abstract.trim(),
      discipline: discipline.trim() || undefined,
      model_id: selectedModel || undefined,
    });
  };

  return (
    <FeatureWorkbenchShell
      workspaceId={workspaceId}
      title="期刊推荐"
      description="根据论文题目、摘要和画像推荐候选投稿期刊"
      icon={Lightbulb}
      iconBgClass="bg-amber-500/10"
      iconClass="text-amber-600 dark:text-amber-400"
      sidebarTitle="推荐配置"
      sidebar={
        <div className="space-y-4">
          {sourceArtifact && (
            <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-[var(--text-muted)]">
                当前论文画像来源
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
              className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
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
              className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
            />
          </div>

          <div>
            <label className="block text-xs text-[var(--text-muted)] mb-1">
              论文摘要
            </label>
            <textarea
              rows={8}
              placeholder="粘贴摘要或研究概述"
              value={abstract}
              onChange={(event) => setAbstractInput(event.target.value)}
              className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
            />
          </div>

          <ModelSelector
            id="journal-recommend-model"
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
              "w-full py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 transition-colors",
              isRunning && "opacity-60 cursor-not-allowed"
            )}
          >
            {isRunning ? "推荐中..." : "推荐期刊"}
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
        title="期刊推荐运行面板"
        emptyDescription="执行后，这里会展示论文画像提炼、期刊匹配和排序阶段。"
      />
      <WorkspaceResultPanel viewModel={resultViewModel} />
    </FeatureWorkbenchShell>
  );
}
