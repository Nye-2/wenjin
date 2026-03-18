"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, BookOpen, FileSearch } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import { TaskFeedbackBanner } from "@/components/workspace/TaskFeedbackBanner";
import { ModelSelector } from "@/components/workspace/ModelSelector";
import { useModelSelection } from "@/hooks/useModelSelection";
import { cn } from "@/lib/utils";

const TIME_RANGE_OPTIONS = [
  { value: "近3年", label: "近3年" },
  { value: "近5年", label: "近5年" },
  { value: "近10年", label: "近10年" },
  { value: "2020-2024", label: "2020-2024" },
  { value: "2015-2024", label: "2015-2024" },
] as const;

export default function BackgroundResearchPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace } = useWorkspaceStore();

  const [keywords, setKeywords] = useState("");
  const [industryScope, setIndustryScope] = useState("相关领域");
  const [timeRange, setTimeRange] = useState("近5年");

  const { run, isRunning, status, error } = useFeatureTaskRunner({
    workspaceId,
    featureId: "background_research",
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
    if (workspace && !keywords) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync from async store
      setKeywords((workspace.description || workspace.name || "").toString());
    }
  }, [workspace, keywords]);

  const handleGenerate = async () => {
    if (!keywords.trim()) return;
    await run({
      keywords: keywords.trim(),
      industry_scope: industryScope,
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
          <div className="p-2 rounded-lg bg-emerald-500/10">
            <BookOpen className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-[var(--text-primary)]">
              背景调研
            </h1>
            <p className="text-xs text-[var(--text-muted)]">
              调研项目背景和研究现状
            </p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left Sidebar - Input */}
        <aside className="w-80 border-r border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
          <h2 className="text-sm font-medium text-[var(--text-primary)] mb-4">
            调研配置
          </h2>

          <div className="space-y-4">
            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                主题关键词
              </label>
              <input
                type="text"
                placeholder="输入主题关键词..."
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                行业范围
              </label>
              <input
                type="text"
                placeholder="如：人工智能、生物医药..."
                value={industryScope}
                onChange={(e) => setIndustryScope(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                时间范围
              </label>
              <select
                value={timeRange}
                onChange={(e) => setTimeRange(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              >
                {TIME_RANGE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <ModelSelector
              id="background-research-model"
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
                "w-full py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors",
                isRunning && "opacity-60 cursor-not-allowed"
              )}
              onClick={handleGenerate}
              disabled={isRunning}
            >
              {isRunning ? "正在调研..." : "开始调研"}
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
            className="h-full flex items-center justify-center"
          >
            <div className="text-center">
              <FileSearch className="w-16 h-16 text-emerald-500 mx-auto mb-4 opacity-50" />
              <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
                背景调研工作区
              </h2>
              <p className="text-[var(--text-secondary)]">
                配置左侧参数后点击开始调研，生成的报告将作为产出物保存。
              </p>
              <p className="text-sm text-[var(--text-muted)] mt-2">
                包含：现状综述、问题清单、可行技术方向、参考文献
              </p>
            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
