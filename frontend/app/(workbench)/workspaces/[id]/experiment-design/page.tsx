"use client";

import { useMemo, useState } from "react";
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
import {
  createWorkspaceResultViewModel,
  describeFields,
  describeTaskStatus,
} from "@/lib/workspace-result";
import {
  findLatestArtifact,
  getArtifactContentRecord,
  readStringList,
} from "@/lib/artifact-utils";
import {
  getArtifactObjective,
  getArtifactTopic,
  resolveFeatureSourceArtifact,
  summarizeArtifactContext,
} from "@/lib/workspace-feature-actions";
import { cn } from "@/lib/utils";

export default function ExperimentDesignPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const workspaceId = params.id as string;
  const { workspace, artifacts } = useWorkspaceStore();

  const sourceArtifactId = searchParams.get("source_artifact_id");
  const sourceArtifact = useMemo(
    () =>
      resolveFeatureSourceArtifact(
        "experiment_design",
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
  const [objectiveInput, setObjectiveInput] = useState<string | null>(() =>
    searchParams.get("objective")
  );
  const defaultTopic = useMemo(
    () =>
      getArtifactTopic(sourceArtifact) ??
      (workspace?.description || workspace?.name || "").toString(),
    [sourceArtifact, workspace]
  );
  const defaultObjective = useMemo(
    () => getArtifactObjective(sourceArtifact) ?? defaultTopic,
    [sourceArtifact, defaultTopic]
  );
  const topic = topicInput ?? defaultTopic;
  const objective = objectiveInput ?? defaultObjective;

  const {
    run,
    isRunning,
    status,
    error,
    result: latestTaskResult,
    runtime,
  } = useFeatureTaskRunner({
    workspaceId,
    featureId: "experiment_design",
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

  const latestDesignArtifact = useMemo(
    () => findLatestArtifact(artifacts, ["methodology"]),
    [artifacts]
  );
  const latestDesignResult = useMemo(
    () => getArtifactContentRecord(latestDesignArtifact) ?? latestTaskResult,
    [latestDesignArtifact, latestTaskResult]
  );
  const hypotheses = readStringList(latestDesignResult?.hypotheses, 3);
  const evaluation = readStringList(latestDesignResult?.evaluation, 3);
  const risks = readStringList(latestDesignResult?.risks, 3);
  const variableCount = Array.isArray(latestDesignResult?.variables)
    ? latestDesignResult.variables.length
    : 0;
  const procedureCount = Array.isArray(latestDesignResult?.procedure)
    ? latestDesignResult.procedure.length
    : 0;

  const resultViewModel: WorkspaceResultViewModel =
    createWorkspaceResultViewModel({
      summary: latestDesignResult
        ? "最近一次实验设计已生成，可继续回填申报书方法路线与评估方案。"
        : "本模块用于围绕课题生成研究假设、变量设计、流程和评估方案。",
      sections: [
        {
          title: "当前配置",
          content: describeFields([
            ["主题", topic],
            ["研究目标", objective],
            ["来源 artifact", sourceArtifact?.title || sourceArtifact?.type || null],
          ]),
        },
        {
          title: "任务状态",
          content: describeTaskStatus({
            error,
            status,
            idleMessage: "尚未开始生成实验设计。",
          }),
        },
        {
          title: "最近设计结果",
          content: latestDesignResult
            ? [
                hypotheses.length > 0 ? `研究假设：${hypotheses.join("、")}` : null,
                variableCount > 0 ? `变量数：${variableCount}` : null,
                procedureCount > 0 ? `流程步骤：${procedureCount}` : null,
                evaluation.length > 0 ? `评估：${evaluation.join("、")}` : null,
                risks.length > 0 ? `风险：${risks.join("、")}` : null,
              ]
                .filter((item): item is string => Boolean(item))
                .join("；")
            : "执行后会在这里展示最近一次实验设计摘要。",
        },
      ],
      nextActions: [
        "优先挂载最近 proposal 或 background-research 产物再执行设计。",
        "把 variables / procedure / evaluation 直接写入申报书方法部分。",
        "如需更细方案，可继续在 chat 中追问样本、指标和对照组设计。",
      ],
      outputLanguage: "zh",
    });

  const handleGenerate = async () => {
    if (!topic.trim() || !objective.trim()) {
      return;
    }
    await run({
      topic: topic.trim(),
      objective: objective.trim(),
      model_id: selectedModel || undefined,
    });
  };

  return (
    <FeatureWorkbenchShell
      workspaceId={workspaceId}
      title="实验设计"
      description="围绕课题生成假设、变量设计、实验流程和评估方案"
      icon={FlaskConical}
      iconBgClass="bg-indigo-500/10"
      iconClass="text-indigo-600 dark:text-indigo-400"
      sidebarTitle="设计配置"
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
              placeholder="输入实验设计主题"
              value={topic}
              onChange={(event) => setTopicInput(event.target.value)}
              className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
          </div>

          <div>
            <label className="block text-xs text-[var(--text-muted)] mb-1">
              研究目标
            </label>
            <textarea
              rows={6}
              placeholder="输入实验要验证的目标、问题或效果"
              value={objective}
              onChange={(event) => setObjectiveInput(event.target.value)}
              className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
          </div>

          <ModelSelector
            id="experiment-design-model"
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
              "w-full py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors",
              isRunning && "opacity-60 cursor-not-allowed"
            )}
          >
            {isRunning ? "生成中..." : "生成实验设计"}
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
        title="实验设计运行面板"
        emptyDescription="执行后，这里会展示假设澄清、变量设计和评估规划阶段。"
      />
      <WorkspaceResultPanel viewModel={resultViewModel} />
    </FeatureWorkbenchShell>
  );
}
