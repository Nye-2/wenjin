"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, Search } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import {
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
import { findLatestArtifact, getArtifactContentRecord, readStringList } from "@/lib/artifact-utils";
import { cn } from "@/lib/utils";

const TIME_RANGE_OPTIONS = [
  { value: "近1年", label: "近1年" },
  { value: "近3年", label: "近3年" },
  { value: "近5年", label: "近5年" },
  { value: "近10年", label: "近10年" },
  { value: "不限", label: "不限" },
] as const;

export default function PriorArtSearchPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace, artifacts } = useWorkspaceStore();

  const [keywords, setKeywords] = useState("");
  const [ipcCodes, setIpcCodes] = useState("");

  useEffect(() => {
    if (workspace && !keywords) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync from async store
      setKeywords((workspace.name || workspace.description || "").toString());
    }
  }, [workspace, keywords]);
  const [timeRange, setTimeRange] = useState<string>("近5年");

  const { run, isRunning, status, error, result: latestTaskResult, runtime } = useFeatureTaskRunner({
    workspaceId,
    featureId: "prior_art_search",
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

  const latestPriorArtArtifact = useMemo(
    () => findLatestArtifact(artifacts, ["prior_art_report"]),
    [artifacts]
  );
  const latestPriorArtResult = useMemo(
    () => getArtifactContentRecord(latestPriorArtArtifact) ?? latestTaskResult,
    [latestPriorArtArtifact, latestTaskResult]
  );
  const comparisonTable = Array.isArray(latestPriorArtResult?.comparison_table)
    ? latestPriorArtResult.comparison_table
    : [];
  const noveltyRisks = readStringList(latestPriorArtResult?.novelty_risks, 3);
  const avoidanceSuggestions = readStringList(latestPriorArtResult?.avoidance_suggestions, 3);
  const resultViewModel: WorkspaceResultViewModel = createWorkspaceResultViewModel({
    summary: latestPriorArtResult
      ? "最近一次现有技术检索分析已生成，可用于修订专利方案与权利要求。"
      : "本工作区用于检索现有技术并输出新颖性风险分析。",
    sections: [
      {
        title: "当前检索参数",
        content: describeFields([
          ["关键词", keywords],
          ["IPC/CPC", ipcCodes],
          ["时间范围", timeRange],
        ]),
      },
      {
        title: "任务状态",
        content: describeTaskStatus({
          error,
          status,
          idleMessage: "尚未开始检索分析。",
        }),
      },
      {
        title: "最近分析结果",
        content: latestPriorArtResult
          ? [
              `对比项：${comparisonTable.length}`,
              noveltyRisks.length > 0 ? `风险：${noveltyRisks.join("、")}` : null,
              avoidanceSuggestions.length > 0 ? `规避建议：${avoidanceSuggestions.join("、")}` : null,
            ]
              .filter((item): item is string => Boolean(item))
              .join("；")
          : "执行后会在这里展示最近一次检索分析摘要。",
      },
    ],
    nextActions: [
      "先根据创新点设置关键词和 IPC/CPC。",
      "根据风险点调整 patent-outline 中的方案表述。",
      "在知识区查看完整对比表和建议。",
    ],
    outputLanguage: "zh",
  });

  const handleSearch = async () => {
    if (!keywords.trim()) return;
    const keywordList = keywords
      .split(/[,，\s]+/)
      .map((k) => k.trim())
      .filter((k) => k);
    const ipcList = ipcCodes
      .split(/[,，\s]+/)
      .map((c) => c.trim())
      .filter((c) => c);
    await run({
      keywords: keywordList,
      ipc_codes: ipcList,
      time_range: timeRange,
      model_id: selectedModel || undefined,
    });
  };

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
          <div className="p-2 rounded-lg bg-amber-500/10">
            <Search className="w-5 h-5 text-amber-600 dark:text-amber-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-[var(--text-primary)]">
              现有技术检索
            </h1>
            <p className="text-xs text-[var(--text-muted)]">
              检索相关专利与文献，辅助新颖性分析
            </p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left Sidebar - Input */}
        <aside className="w-96 border-r border-[var(--border-default)] bg-[var(--bg-surface)] p-4 overflow-y-auto">
          <h2 className="text-sm font-medium text-[var(--text-primary)] mb-4">
            检索配置
          </h2>

          <div className="space-y-4">
            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                检索关键词 <span className="text-red-500">*</span>
              </label>
              <textarea
                placeholder="输入关键词，多个关键词用逗号或空格分隔..."
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50 resize-none"
              />
              <p className="text-xs text-[var(--text-muted)] mt-1">
                建议使用技术术语，可包含同义词
              </p>
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                IPC/CPC分类号（可选）
              </label>
              <input
                type="text"
                placeholder="如：G06F, H04L..."
                value={ipcCodes}
                onChange={(e) => setIpcCodes(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
              />
              <p className="text-xs text-[var(--text-muted)] mt-1">
                多个分类号用逗号分隔
              </p>
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                时间范围
              </label>
              <div className="flex flex-wrap gap-2">
                {TIME_RANGE_OPTIONS.map((option) => (
                  <label
                    key={option.value}
                    className={cn(
                      "px-3 py-1.5 rounded-lg text-sm cursor-pointer transition-colors",
                      timeRange === option.value
                        ? "bg-amber-500 text-white"
                        : "bg-[var(--bg-elevated)] text-[var(--text-primary)] hover:bg-[var(--bg-muted)]"
                    )}
                  >
                    <input
                      type="radio"
                      name="time_range"
                      value={option.value}
                      checked={timeRange === option.value}
                      onChange={() => setTimeRange(option.value)}
                      className="sr-only"
                    />
                    {option.label}
                  </label>
                ))}
              </div>
            </div>

            <ModelSelector
              id="prior-art-model"
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
                "w-full py-2.5 bg-amber-600 text-white rounded-lg hover:bg-amber-700 transition-colors font-medium",
                isRunning && "opacity-60 cursor-not-allowed"
              )}
              onClick={handleSearch}
              disabled={isRunning}
            >
              {isRunning ? "正在检索..." : "开始检索分析"}
            </button>

            <TaskFeedbackBanner
              isRunning={isRunning}
              status={status}
              error={error}
              onRetry={handleSearch}
            />
          </div>
        </aside>

        {/* Main Area */}
        <div className="flex-1 p-6 overflow-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-6"
          >
            <TaskRuntimePanel
              runtime={runtime}
              isRunning={isRunning}
              status={status}
              error={error}
              title="现有技术检索运行面板"
              emptyDescription="执行后，这里会显示检索范围、对比分析和风险整理过程。"
            />
            <WorkspaceResultPanel viewModel={resultViewModel} />
          </motion.div>
        </div>
      </main>
    </div>
  );
}
