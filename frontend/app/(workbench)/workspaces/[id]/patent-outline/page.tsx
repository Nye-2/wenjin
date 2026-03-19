"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, FileText } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import { TaskFeedbackBanner } from "@/components/workspace/TaskFeedbackBanner";
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
} from "@/lib/artifact-utils";

export default function PatentOutlinePage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace, artifacts } = useWorkspaceStore();

  const [innovationDescription, setInnovationDescription] = useState("");
  const [technicalField, setTechnicalField] = useState("");
  const [applicationScenario, setApplicationScenario] = useState("");
  const [implementationMethod, setImplementationMethod] = useState("");

  const { run, isRunning, status, error, result: latestTaskResult } = useFeatureTaskRunner({
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
    <div className="h-screen flex flex-col bg-[var(--bg-base)]">
      {/* Header */}
      <header className="h-14 flex items-center gap-4 px-4 bg-[var(--glass-bg)] backdrop-blur-xl border-b border-[var(--glass-border)]">
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => router.push(`/workspaces/${workspaceId}`)}
          className={cn(
            "p-2 rounded-lg",
            "bg-[var(--bg-surface)]",
            "hover:bg-[var(--bg-muted)]",
            "text-[var(--text-secondary)]",
            "transition-colors"
          )}
        >
          <ArrowLeft className="w-5 h-5" />
        </motion.button>

        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-rose-500/10">
            <FileText className="w-5 h-5 text-rose-600 dark:text-rose-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-[var(--text-primary)]">
              专利框架
            </h1>
            <p className="text-xs text-[var(--text-muted)]">
              生成专利说明书与权利要求书框架
            </p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left Sidebar - Input */}
        <aside className="w-96 border-r border-[var(--border-default)] bg-[var(--bg-surface)] p-4 overflow-y-auto">
          <h2 className="text-sm font-medium text-[var(--text-primary)] mb-4">
            专利信息配置
          </h2>

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
        </aside>

        {/* Main Area */}
        <div className="flex-1 p-6 overflow-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="h-full"
          >
            <WorkspaceResultPanel viewModel={resultViewModel} />
          </motion.div>
        </div>
      </main>
    </div>
  );
}
