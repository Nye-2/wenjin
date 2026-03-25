"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { List } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import {
  FeatureWorkbenchShell,
  TaskFeedbackBanner,
  TaskRuntimePanel,
} from "@/components/workspace";
import { ModelSelector } from "@/components/workspace/ModelSelector";
import {
  WorkspaceResultPanel,
  type WorkspaceResultViewModel,
} from "@/components/workspace/WorkspaceResultPanel";
import { useModelSelection } from "@/hooks/useModelSelection";
import { cn } from "@/lib/utils";
import { createWorkspaceResultViewModel, describeFields, describeTaskStatus } from "@/lib/workspace-result";
import {
  findLatestArtifact,
  getArtifactContentRecord,
  readNamedSections,
  readString,
} from "@/lib/artifact-utils";

const PROPOSAL_TYPES = [
  { value: "national_natural_science", label: "国家自然科学基金" },
  { value: "national_social_science", label: "国家社会科学基金" },
  { value: "provincial", label: "省部级项目" },
  { value: "enterprise", label: "企业联合项目" },
  { value: "university", label: "校级项目" },
  { value: "other", label: "其他类型" },
] as const;

const PERIOD_OPTIONS = [
  { value: 12, label: "1年（12个月）" },
  { value: 24, label: "2年（24个月）" },
  { value: 36, label: "3年（36个月）" },
  { value: 48, label: "4年（48个月）" },
  { value: 60, label: "5年（60个月）" },
] as const;

type ProposalTypeValue = (typeof PROPOSAL_TYPES)[number]["value"];

export default function ProposalOutlinePage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const workspaceId = params.id as string;
  const { workspace, artifacts } = useWorkspaceStore();
  const topicSeed = searchParams.get("topic");
  const proposalTypeSeed = searchParams.get("proposal_type");
  const periodMonthsSeed = searchParams.get("period_months");

  const [topic, setTopic] = useState(() => topicSeed || "");
  const [proposalType, setProposalType] = useState<ProposalTypeValue>(() =>
    PROPOSAL_TYPES.some((item) => item.value === proposalTypeSeed)
      ? (proposalTypeSeed as ProposalTypeValue)
      : "other"
  );

  useEffect(() => {
    if (workspace && !topic) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync from async store
      setTopic((workspace.description || workspace.name || "").toString());
    }
  }, [workspace, topic]);
  const [periodMonths, setPeriodMonths] = useState<number>(() => {
    const parsed = Number(periodMonthsSeed);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 24;
  });

  useEffect(() => {
    if (topicSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setTopic(topicSeed);
    }
  }, [topicSeed]);

  useEffect(() => {
    if (PROPOSAL_TYPES.some((item) => item.value === proposalTypeSeed)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setProposalType(proposalTypeSeed as ProposalTypeValue);
    }
  }, [proposalTypeSeed]);

  useEffect(() => {
    const parsed = Number(periodMonthsSeed);
    if (Number.isFinite(parsed) && parsed > 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setPeriodMonths(parsed);
    }
  }, [periodMonthsSeed]);

  const { run, isRunning, status, error, result: latestTaskResult, runtime } = useFeatureTaskRunner({
    workspaceId,
    featureId: "proposal_outline",
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

  const handleGenerate = async () => {
    if (!topic.trim()) return;
    await run({
      topic: topic.trim(),
      proposal_type: proposalType,
      period_months: periodMonths,
      model_id: selectedModel || undefined,
    });
  };

  const latestProposalArtifact = useMemo(
    () => findLatestArtifact(artifacts, ["proposal"]),
    [artifacts]
  );
  const latestProposalResult = useMemo(
    () => getArtifactContentRecord(latestProposalArtifact) ?? latestTaskResult,
    [latestProposalArtifact, latestTaskResult]
  );
  const latestProposalSections = useMemo(
    () =>
      Array.isArray(latestProposalResult?.sections)
        ? latestProposalResult.sections
        : [],
    [latestProposalResult]
  );
  const latestProposalMilestones = useMemo(
    () =>
      Array.isArray(latestProposalResult?.milestones)
        ? latestProposalResult.milestones
        : [],
    [latestProposalResult]
  );
  const latestProposalRisks = useMemo(
    () =>
      Array.isArray(latestProposalResult?.risks)
        ? latestProposalResult.risks
        : [],
    [latestProposalResult]
  );
  const latestProposalSectionTitles = useMemo(
    () => readNamedSections(latestProposalSections, 4),
    [latestProposalSections]
  );
  const latestProposalTypeLabel = readString(
    latestProposalResult?.proposal_type_label
  );
  const latestProposalSummary = latestProposalResult
    ? [
        `章节数：${latestProposalSections.length}`,
        latestProposalMilestones.length > 0
          ? `里程碑：${latestProposalMilestones.length}`
          : null,
        latestProposalRisks.length > 0
          ? `风险项：${latestProposalRisks.length}`
          : null,
        latestProposalSectionTitles.length > 0
          ? `核心章节：${latestProposalSectionTitles.join("、")}`
          : null,
      ]
        .filter((item): item is string => Boolean(item))
        .join("；")
    : "执行后会在这里展示最近一次生成的大纲结构。";

  const resultViewModel: WorkspaceResultViewModel = createWorkspaceResultViewModel({
    summary: latestProposalResult
      ? `最近一次已生成${latestProposalTypeLabel || "申报书"}大纲，可继续补充背景调研、预算与里程碑细节。`
      : "本工作区用于生成研究项目申报书的大纲骨架，并沉淀为可复用产出。",
    sections: [
      {
        title: "当前配置",
        content: describeFields([
          ["主题", topic],
          ["类型", proposalType],
          ["周期", `${periodMonths} 个月`],
        ]),
      },
      {
        title: "任务状态",
        content: describeTaskStatus({
          error,
          status,
          idleMessage: "尚未开始执行生成。",
        }),
      },
      {
        title: "产出内容",
        content: latestProposalSummary,
      },
    ],
    nextActions: [
      "确认主题、申报类型与周期后执行生成。",
      "结合背景调研补充关键问题与技术路线细节。",
      "根据预算与里程碑形成可提交版本。",
    ],
    outputLanguage: "zh",
  });

  return (
    <FeatureWorkbenchShell
      workspaceId={workspaceId}
      title="申报书大纲"
      description="生成项目申报书结构化大纲"
      icon={List}
      iconBgClass="bg-purple-500/10"
      iconClass="text-purple-600 dark:text-purple-400"
      sidebarTitle="大纲配置"
      sidebar={
        <div className="space-y-4">
            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                项目主题
              </label>
              <input
                type="text"
                placeholder="输入项目主题..."
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                申报类型
              </label>
              <select
                value={proposalType}
                onChange={(e) => setProposalType(e.target.value as ProposalTypeValue)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/50"
              >
                {PROPOSAL_TYPES.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                项目周期
              </label>
              <select
                value={periodMonths}
                onChange={(e) => setPeriodMonths(Number(e.target.value))}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/50"
              >
                {PERIOD_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <ModelSelector
              id="proposal-outline-model"
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
                "w-full py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors",
                isRunning && "opacity-60 cursor-not-allowed"
              )}
              onClick={handleGenerate}
              disabled={isRunning}
            >
              {isRunning ? "正在生成..." : "生成大纲"}
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
        title="申报书大纲运行面板"
        emptyDescription="执行后，这里会显示项目范围、大纲生成和里程碑整理过程。"
      />
      <WorkspaceResultPanel viewModel={resultViewModel} />
    </FeatureWorkbenchShell>
  );
}
