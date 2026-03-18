"use client";

import { useState, useMemo, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, BarChart3, Image as ImageIcon } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import { TaskFeedbackBanner } from "@/components/workspace/TaskFeedbackBanner";
import { ModelSelector } from "@/components/workspace/ModelSelector";
import { useModelSelection } from "@/hooks/useModelSelection";
import { cn } from "@/lib/utils";

export default function FigureGenerationPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace, artifacts, fetchArtifacts } = useWorkspaceStore();
  const [figureType, setFigureType] = useState("flowchart");
  const [description, setDescription] = useState("");
  const [chapterIndex, setChapterIndex] = useState("");

  const { run, isRunning, status, error } = useFeatureTaskRunner({
    workspaceId,
    featureId: "figure_generation",
    onSuccess: () => setDescription(""),
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

  // 获取章节列表
  useEffect(() => {
    if (workspaceId) {
      fetchArtifacts(workspaceId);
    }
  }, [workspaceId, fetchArtifacts]);

  const chapters = useMemo(() => {
    const outlineArtifact = artifacts.find(
      (a) =>
        a.type === "framework_outline" ||
        a.type === "thesis_outline" ||
        a.type === "outline"
    );

    if (!outlineArtifact?.content) return [];

    const content = outlineArtifact.content as Record<string, unknown>;
    const outlineContent =
      content.outline && typeof content.outline === "object"
        ? (content.outline as Record<string, unknown>)
        : content;
    const chaptersList = outlineContent.chapters as
      | Array<Record<string, unknown>>
      | undefined;

    if (!chaptersList) return [];

    return chaptersList.map((chapter, index) => ({
      index: index + 1,
      title: String(chapter.title || `第${index + 1}章`),
    }));
  }, [artifacts]);

  const handleGenerateFigure = async () => {
    if (!description.trim()) return;
    const p: Record<string, unknown> = {
      type: figureType,
      description: description.trim(),
    };
    if (chapterIndex) {
      p.chapter_index = Number(chapterIndex);
    }
    p.model_id = selectedModel || undefined;
    await run(p);
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
          <div className="p-2 rounded-lg bg-cyan-500/10">
            <BarChart3 className="w-5 h-5 text-cyan-600 dark:text-cyan-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-[var(--text-primary)]">
              图表生成
            </h1>
            <p className="text-xs text-[var(--text-muted)]">
              流程图、数据可视化、概念图
            </p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left Sidebar - Config */}
        <aside className="w-80 border-r border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
          <h2 className="text-sm font-medium text-[var(--text-primary)] mb-4">
            图表配置
          </h2>

          <div className="space-y-4">
            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                图表类型
              </label>
              <select
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
                value={figureType}
                onChange={(e) => setFigureType(e.target.value)}
              >
                <option value="flowchart">流程图</option>
                <option value="data_visualization">数据可视化</option>
                <option value="concept_map">概念图</option>
              </select>
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                描述
              </label>
              <textarea
                placeholder="描述要生成的图表..."
                rows={4}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500/50 resize-none"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                关联章节
              </label>
              <select
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
                value={chapterIndex}
                onChange={(e) => setChapterIndex(e.target.value)}
              >
                <option value="">不关联</option>
                {chapters.length > 0 ? (
                  chapters.map((ch) => (
                    <option key={ch.index} value={ch.index}>
                      {ch.title}
                    </option>
                  ))
                ) : (
                  <>
                    <option value="1">第一章</option>
                    <option value="2">第二章</option>
                    <option value="3">第三章</option>
                    <option value="4">第四章</option>
                  </>
                )}
              </select>
              {chapters.length === 0 && (
                <p className="text-xs text-[var(--text-muted)] mt-1">
                  请先生成论文大纲以获取实际章节
                </p>
              )}
            </div>

            <ModelSelector
              id="figure-generation-model"
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
                "w-full py-2 bg-cyan-600 text-white rounded-lg transition-colors",
                isRunning ? "opacity-60 cursor-not-allowed" : "hover:bg-cyan-700"
              )}
              onClick={handleGenerateFigure}
              disabled={isRunning}
            >
              {isRunning ? "正在生成..." : "生成图表"}
            </button>

            <TaskFeedbackBanner
              isRunning={isRunning}
              status={status}
              error={error}
              onRetry={handleGenerateFigure}
            />
          </div>
        </aside>

        {/* Main Area - Preview */}
        <div className="flex-1 p-6 overflow-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="h-full flex items-center justify-center"
          >
            <div className="text-center">
              <ImageIcon className="w-16 h-16 text-cyan-500 mx-auto mb-4 opacity-50" />
              <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
                图表预览
              </h2>
              <p className="text-[var(--text-secondary)]">
                {workspace?.name
                  ? `当前工作区：${workspace.name}`
                  : "配置左侧参数后生成图表"}
              </p>
            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
