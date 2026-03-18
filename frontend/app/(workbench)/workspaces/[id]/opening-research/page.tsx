"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, Search, FileText } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import { TaskFeedbackBanner } from "@/components/workspace/TaskFeedbackBanner";
import { ModelSelector } from "@/components/workspace/ModelSelector";
import { useModelSelection } from "@/hooks/useModelSelection";
import { cn } from "@/lib/utils";

const REPORT_TYPES = [
  { value: "opening_report", label: "开题报告" },
  { value: "literature_review", label: "文献综述" },
  { value: "feasibility_analysis", label: "可行性分析" },
] as const;

type ReportTypeValue = (typeof REPORT_TYPES)[number]["value"];

export default function OpeningResearchPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace } = useWorkspaceStore();

  const [topic, setTopic] = useState("");
  const [reportType, setReportType] = useState<ReportTypeValue>("opening_report");

  const { run, isRunning, status, error } = useFeatureTaskRunner({
    workspaceId,
    featureId: "opening_research",
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
    if (workspace && !topic) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync from async store
      setTopic((workspace.description || workspace.name || "").toString());
    }
  }, [workspace, topic]);

  const handleGenerate = async () => {
    if (!topic.trim()) return;
    await run({
      topic: topic.trim(),
      report_type: reportType,
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
              开题调研
            </h1>
            <p className="text-xs text-[var(--text-muted)]">
              生成开题报告、文献综述、可行性分析
            </p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left Sidebar - Input */}
        <aside className="w-80 border-r border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
          <h2 className="text-sm font-medium text-[var(--text-primary)] mb-4">
            报告配置
          </h2>

          <div className="space-y-4">
            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                研究主题
              </label>
              <input
                type="text"
                placeholder="输入研究主题..."
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                报告类型
              </label>
              <div className="space-y-2">
                {REPORT_TYPES.map((type) => (
                  <label
                    key={type.value}
                    className="flex items-center gap-2 p-2 bg-[var(--bg-elevated)] rounded-lg cursor-pointer hover:bg-[var(--bg-muted)]"
                  >
                    <input
                      type="radio"
                      name="report_type"
                      value={type.value}
                      checked={reportType === type.value}
                      onChange={() => setReportType(type.value)}
                      className="text-amber-500"
                    />
                    <span className="text-sm text-[var(--text-primary)]">
                      {type.label}
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <ModelSelector
              id="opening-research-model"
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
                "w-full py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 transition-colors",
                isRunning && "opacity-60 cursor-not-allowed"
              )}
              onClick={handleGenerate}
              disabled={isRunning}
            >
              {isRunning ? "正在生成..." : "生成报告"}
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
              <FileText className="w-16 h-16 text-amber-500 mx-auto mb-4 opacity-50" />
              <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
                开题调研工作区
              </h2>
              <p className="text-[var(--text-secondary)]">
                配置左侧参数后点击生成报告，生成的报告将作为产出物保存。
              </p>
            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
