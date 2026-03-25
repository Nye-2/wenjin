"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { FileText } from "lucide-react";
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

export default function PatentOutlinePage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const workspaceId = params.id as string;
  const { workspace, artifacts } = useWorkspaceStore();
  const innovationDescriptionSeed = searchParams.get("innovation_description");
  const technicalFieldSeed = searchParams.get("technical_field");
  const applicationScenarioSeed = searchParams.get("application_scenario");
  const implementationMethodSeed = searchParams.get("implementation_method");

  const [innovationDescription, setInnovationDescription] = useState(
    () => innovationDescriptionSeed || ""
  );
  const [technicalField, setTechnicalField] = useState(
    () => technicalFieldSeed || ""
  );
  const [applicationScenario, setApplicationScenario] = useState(
    () => applicationScenarioSeed || ""
  );
  const [implementationMethod, setImplementationMethod] = useState(
    () => implementationMethodSeed || ""
  );

  const { run, isRunning, status, error, result: latestTaskResult, runtime } = useFeatureTaskRunner({
    workspaceId,
    featureId: "patent_outline",
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

  useEffect(() => {
    if (innovationDescriptionSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setInnovationDescription(innovationDescriptionSeed);
    }
  }, [innovationDescriptionSeed]);

  useEffect(() => {
    if (technicalFieldSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setTechnicalField(technicalFieldSeed);
    }
  }, [technicalFieldSeed]);

  useEffect(() => {
    if (applicationScenarioSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setApplicationScenario(applicationScenarioSeed);
    }
  }, [applicationScenarioSeed]);

  useEffect(() => {
    if (implementationMethodSeed !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync local draft with route seed
      setImplementationMethod(implementationMethodSeed);
    }
  }, [implementationMethodSeed]);

  useEffect(() => {
    if (workspace && !innovationDescription) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync from async store
      setInnovationDescription((workspace.description || workspace.name || "").toString());
    }
  }, [workspace, innovationDescription]);

  const handleGenerate = async () => {
    if (!innovationDescription.trim()) return;
    await run({
      innovation_description: innovationDescription.trim(),
      technical_field: technicalField.trim(),
      application_scenario: applicationScenario.trim(),
      implementation_method: implementationMethod.trim(),
      model_id: selectedModel || undefined,
    });
  };

  const latestPatentArtifact = useMemo(
    () => findLatestArtifact(artifacts, ["patent_outline"]),
    [artifacts]
  );
  const latestPatentResult = useMemo(
    () => getArtifactContentRecord(latestPatentArtifact) ?? latestTaskResult,
    [latestPatentArtifact, latestTaskResult]
  );
  const latestPatentSections = useMemo(
    () =>
      Array.isArray(latestPatentResult?.sections)
        ? latestPatentResult.sections
        : [],
    [latestPatentResult]
  );
  const latestPatentSectionTitles = useMemo(
    () => readNamedSections(latestPatentSections, 4),
    [latestPatentSections]
  );
  const claimsDraft =
    latestPatentResult?.claims_draft &&
    typeof latestPatentResult.claims_draft === "object"
      ? (latestPatentResult.claims_draft as Record<string, unknown>)
      : null;
  const independentClaims = Array.isArray(claimsDraft?.independent_claims)
    ? claimsDraft.independent_claims
    : [];
  const dependentClaims = Array.isArray(claimsDraft?.dependent_claims)
    ? claimsDraft.dependent_claims
    : [];
  const evidencePoints = Array.isArray(latestPatentResult?.evidence_points_needed)
    ? latestPatentResult.evidence_points_needed
    : [];

  useEffect(() => {
    const latestInnovationDescription = readString(
      latestPatentResult?.innovation_description
    );
    if (latestInnovationDescription && !innovationDescription) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest innovation description when route seed is absent
      setInnovationDescription(latestInnovationDescription);
    }
  }, [latestPatentResult, innovationDescription]);

  useEffect(() => {
    const latestTechnicalField = readString(latestPatentResult?.technical_field);
    if (latestTechnicalField && !technicalField) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest technical field when route seed is absent
      setTechnicalField(latestTechnicalField);
    }
  }, [latestPatentResult, technicalField]);

  useEffect(() => {
    const latestApplicationScenario = readString(
      latestPatentResult?.application_scenario
    );
    if (latestApplicationScenario && !applicationScenario) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest application scenario when route seed is absent
      setApplicationScenario(latestApplicationScenario);
    }
  }, [latestPatentResult, applicationScenario]);

  useEffect(() => {
    const latestImplementationMethod = readString(
      latestPatentResult?.implementation_method
    );
    if (latestImplementationMethod && !implementationMethod) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore latest implementation method when route seed is absent
      setImplementationMethod(latestImplementationMethod);
    }
  }, [latestPatentResult, implementationMethod]);

  const resultViewModel: WorkspaceResultViewModel = createWorkspaceResultViewModel({
    summary: latestPatentResult
      ? "最近一次已生成专利框架与权利要求草案，可直接进入现有技术检索继续迭代。"
      : "本工作区用于生成专利说明书框架与权利要求草案，支持后续检索和新颖性风险评估。",
    sections: [
      {
        title: "当前创新点输入",
        content: describeFields([
          ["创新描述", innovationDescription],
          ["技术领域", technicalField],
        ]),
      },
      {
        title: "方案上下文",
        content: describeFields([
          ["应用场景", applicationScenario],
          ["实施方式", implementationMethod],
        ]),
      },
      {
        title: "任务状态",
        content: describeTaskStatus({
          error,
          status,
          idleMessage: "尚未开始生成专利框架。",
        }),
      },
      {
        title: "最近产出",
        content: latestPatentResult
          ? [
              `章节数：${latestPatentSections.length}`,
              `独立权利要求：${independentClaims.length}`,
              `从属权利要求：${dependentClaims.length}`,
              evidencePoints.length > 0 ? `待补证据点：${evidencePoints.length}` : null,
              latestPatentSectionTitles.length > 0
                ? `核心分区：${latestPatentSectionTitles.join("、")}`
                : null,
            ]
              .filter((item): item is string => Boolean(item))
              .join("；")
          : "执行后会在这里展示最近一次生成的专利框架摘要。",
      },
    ],
    nextActions: [
      "补齐创新点、场景与实施方式后执行生成。",
      "基于框架完善权利要求并准备附图说明。",
      "进入 prior-art-search 评估新颖性风险并迭代方案。",
    ],
    outputLanguage: "zh",
  });

  return (
    <FeatureWorkbenchShell
      workspaceId={workspaceId}
      title="专利框架"
      description="生成专利说明书与权利要求书框架"
      icon={FileText}
      iconBgClass="bg-rose-500/10"
      iconClass="text-rose-600 dark:text-rose-400"
      sidebarTitle="专利信息配置"
      sidebarWidthClassName="lg:w-96"
      sidebarClassName="overflow-y-auto"
      sidebar={
        <div className="space-y-4">
            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                创新点描述 <span className="text-red-500">*</span>
              </label>
              <textarea
                placeholder="描述发明的核心创新点..."
                value={innovationDescription}
                onChange={(e) => setInnovationDescription(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/50 resize-none"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                技术领域
              </label>
              <input
                type="text"
                placeholder="如：人工智能、物联网、生物医药..."
                value={technicalField}
                onChange={(e) => setTechnicalField(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                应用场景
              </label>
              <textarea
                placeholder="描述发明的具体应用场景..."
                value={applicationScenario}
                onChange={(e) => setApplicationScenario(e.target.value)}
                rows={2}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/50 resize-none"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                预期实施方式
              </label>
              <textarea
                placeholder="描述发明的具体实施方式..."
                value={implementationMethod}
                onChange={(e) => setImplementationMethod(e.target.value)}
                rows={2}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/50 resize-none"
              />
            </div>

            <ModelSelector
              id="patent-outline-model"
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
                "w-full py-2.5 bg-rose-600 text-white rounded-lg hover:bg-rose-700 transition-colors font-medium",
                isRunning && "opacity-60 cursor-not-allowed"
              )}
              onClick={handleGenerate}
              disabled={isRunning}
            >
              {isRunning ? "正在生成..." : "生成专利框架"}
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
        title="专利框架运行面板"
        emptyDescription="执行后，这里会显示创新输入、框架生成和权利要求整理过程。"
      />
      <WorkspaceResultPanel viewModel={resultViewModel} />
    </FeatureWorkbenchShell>
  );
}
