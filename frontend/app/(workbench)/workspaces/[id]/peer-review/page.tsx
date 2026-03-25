"use client";

import { useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { MessagesSquare } from "lucide-react";
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
  getArtifactExcerpt,
  getArtifactPaperTitle,
  resolveFeatureSourceArtifact,
  summarizeArtifactContext,
} from "@/lib/workspace-feature-actions";
import { cn } from "@/lib/utils";

export default function PeerReviewPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const workspaceId = params.id as string;
  const { workspace, artifacts } = useWorkspaceStore();

  const sourceArtifactId = searchParams.get("source_artifact_id");
  const sourceArtifact = useMemo(
    () => resolveFeatureSourceArtifact("peer_review", artifacts, sourceArtifactId),
    [artifacts, sourceArtifactId]
  );
  const sourceSummary = useMemo(
    () => summarizeArtifactContext(sourceArtifact),
    [sourceArtifact]
  );

  const [paperTitleInput, setPaperTitleInput] = useState<string | null>(() =>
    searchParams.get("paper_title")
  );
  const [manuscriptExcerptInput, setManuscriptExcerptInput] = useState<string | null>(null);
  const defaultPaperTitle = useMemo(
    () =>
      getArtifactPaperTitle(sourceArtifact) ??
      (workspace?.name || workspace?.description || "").toString(),
    [sourceArtifact, workspace]
  );
  const defaultManuscriptExcerpt = useMemo(
    () => getArtifactExcerpt(sourceArtifact) ?? "",
    [sourceArtifact]
  );
  const paperTitle = paperTitleInput ?? defaultPaperTitle;
  const manuscriptExcerpt = manuscriptExcerptInput ?? defaultManuscriptExcerpt;

  const {
    run,
    isRunning,
    status,
    error,
    result: latestTaskResult,
    runtime,
  } = useFeatureTaskRunner({
    workspaceId,
    featureId: "peer_review",
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
    () => findLatestArtifact(artifacts, ["review"]),
    [artifacts]
  );
  const latestReviewResult = useMemo(
    () => getArtifactContentRecord(latestReviewArtifact) ?? latestTaskResult,
    [latestReviewArtifact, latestTaskResult]
  );
  const latestAssessment = readString(latestReviewResult?.overall_assessment);
  const latestScore =
    typeof latestReviewResult?.score === "number"
      ? latestReviewResult.score
      : null;
  const latestStrengths = readStringList(latestReviewResult?.strengths, 3);
  const latestWeaknesses = readStringList(latestReviewResult?.weaknesses, 3);
  const latestRevisionActions = readStringList(
    latestReviewResult?.revision_actions,
    3
  );

  const resultViewModel: WorkspaceResultViewModel =
    createWorkspaceResultViewModel({
      summary: latestReviewResult
        ? "最近一次同行评审已生成，可据此回到写作模块逐项修改。"
        : "本模块用于对当前稿件进行审稿式评阅，输出优劣势和修改建议。",
      sections: [
        {
          title: "当前配置",
          content: describeFields([
            ["论文标题", paperTitle],
            ["稿件长度", manuscriptExcerpt.length > 0 ? `${manuscriptExcerpt.length} 字符` : null],
            ["来源 artifact", sourceArtifact?.title || sourceArtifact?.type || null],
          ]),
        },
        {
          title: "任务状态",
          content: describeTaskStatus({
            error,
            status,
            idleMessage: "尚未开始同行评审。",
          }),
        },
        {
          title: "最近评审结果",
          content: latestReviewResult
            ? [
                latestScore !== null ? `评分：${latestScore.toFixed(1)}` : null,
                latestStrengths.length > 0
                  ? `优点：${latestStrengths.join("、")}`
                  : null,
                latestWeaknesses.length > 0
                  ? `问题：${latestWeaknesses.join("、")}`
                  : null,
                latestRevisionActions.length > 0
                  ? `修改动作：${latestRevisionActions.join("、")}`
                  : null,
                latestAssessment
                  ? `总体评价：${latestAssessment.slice(0, 120)}${
                      latestAssessment.length > 120 ? "..." : ""
                    }`
                  : null,
              ]
                .filter((item): item is string => Boolean(item))
                .join("；")
            : "执行后会在这里展示最近一次评审摘要。",
        },
      ],
      nextActions: [
        "挂载最近草稿后执行评审，避免空稿件审阅。",
        "优先消化 weakness 和 revision actions。",
        "回到 writing 模块对章节逐项修改并再次评审。",
      ],
      outputLanguage: "en",
    });

  const handleGenerate = async () => {
    if (!paperTitle.trim() || !manuscriptExcerpt.trim()) {
      return;
    }
    await run({
      paper_title: paperTitle.trim(),
      manuscript_excerpt: manuscriptExcerpt.trim(),
      model_id: selectedModel || undefined,
    });
  };

  return (
    <FeatureWorkbenchShell
      workspaceId={workspaceId}
      title="同行评审"
      description="从审稿人视角审阅稿件并输出可执行修改建议"
      icon={MessagesSquare}
      iconBgClass="bg-rose-500/10"
      iconClass="text-rose-600 dark:text-rose-400"
      sidebarTitle="评审配置"
      sidebar={
        <div className="space-y-4">
          {sourceArtifact && (
            <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-[var(--text-muted)]">
                当前稿件来源
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
              className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/50"
            />
          </div>

          <div>
            <label className="block text-xs text-[var(--text-muted)] mb-1">
              稿件内容 / 摘录
            </label>
            <textarea
              rows={10}
              placeholder="粘贴待评审的正文、摘要或章节摘录"
              value={manuscriptExcerpt}
              onChange={(event) => setManuscriptExcerptInput(event.target.value)}
              className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/50"
            />
          </div>

          <ModelSelector
            id="peer-review-model"
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
              "w-full py-2 bg-rose-600 text-white rounded-lg hover:bg-rose-700 transition-colors",
              isRunning && "opacity-60 cursor-not-allowed"
            )}
          >
            {isRunning ? "评审中..." : "开始评审"}
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
        title="同行评审运行面板"
        emptyDescription="执行后，这里会展示稿件检查、打分与修改建议输出阶段。"
      />
      <WorkspaceResultPanel viewModel={resultViewModel} />
    </FeatureWorkbenchShell>
  );
}
