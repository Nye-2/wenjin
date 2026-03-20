"use client";

import { useState, useMemo, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, BarChart3, Image as ImageIcon } from "lucide-react";
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
import { extractArtifactFileUrl, isImageUrl, isPdfUrl } from "@/lib/public-assets";
import { findLatestArtifact, getArtifactContentRecord, readString } from "@/lib/artifact-utils";
import { cn } from "@/lib/utils";

export default function FigureGenerationPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace, artifacts, fetchArtifacts } = useWorkspaceStore();
  const [figureType, setFigureType] = useState("flowchart");
  const [description, setDescription] = useState("");
  const [chapterIndex, setChapterIndex] = useState("");

  const { run, isRunning, status, error, result: latestTaskResult, runtime } = useFeatureTaskRunner({
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

  const latestFigureArtifact = useMemo(
    () => findLatestArtifact(artifacts, ["figure"]),
    [artifacts]
  );
  const latestFigureResult = useMemo(
    () => getArtifactContentRecord(latestFigureArtifact) ?? latestTaskResult,
    [latestFigureArtifact, latestTaskResult]
  );
  const latestFigureUrl = extractArtifactFileUrl(latestFigureResult);
  const latestFigureSource = readString(latestFigureResult?.source_code);
  const latestFigurePrompt = readString(latestFigureResult?.prompt);
  const latestFigureFormat =
    latestFigureResult?.render_data &&
    typeof latestFigureResult.render_data === "object"
      ? readString((latestFigureResult.render_data as Record<string, unknown>).format)
      : null;
  const figureResultViewModel: WorkspaceResultViewModel = createWorkspaceResultViewModel({
    summary: latestFigureResult
      ? "最近一次图表产物已生成，可直接预览或下载。"
      : "本工作区用于规划和生成论文图表，支持流程图、数据可视化与概念图。",
    sections: [
      {
        title: "当前配置",
        content: describeFields([
          ["图表类型", figureType],
          ["关联章节", chapterIndex || "未关联"],
        ]),
      },
      {
        title: "任务状态",
        content: describeTaskStatus({
          error,
          status,
          idleMessage: "尚未开始生成图表。",
        }),
      },
      {
        title: "最近产出",
        content: latestFigureResult
          ? [
              describeFields([
                ["策略", readString(latestFigureResult.strategy)],
                ["格式", latestFigureFormat],
              ]),
              latestFigureUrl ? "已生成可访问文件。" : "当前仅生成了源代码/提示词。",
            ].join("；")
          : "执行后会在这里展示最近一次图表生成结果。",
      },
    ],
    nextActions: [
      "补充图表描述并选择关联章节后执行生成。",
      "如果已有文件，先预览再决定是否重新生成。",
      "如仅生成源代码，可在详情中复制并手动调整。",
    ],
    outputLanguage: "zh",
  });

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
            className="space-y-6"
          >
            <TaskRuntimePanel
              runtime={runtime}
              isRunning={isRunning}
              status={status}
              error={error}
              title="图表生成运行面板"
              emptyDescription="执行后，这里会显示图表规划、生成和结果整理过程。"
            />
            <WorkspaceResultPanel viewModel={figureResultViewModel} />

            <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-5">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold text-[var(--text-primary)]">
                    图表预览
                  </h2>
                  <p className="text-sm text-[var(--text-muted)]">
                    {workspace?.name
                      ? `当前工作区：${workspace.name}`
                      : "配置左侧参数后生成图表"}
                  </p>
                </div>
                {latestFigureUrl && (
                  <div className="flex gap-2">
                    <a
                      href={latestFigureUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-lg bg-cyan-600 px-3 py-2 text-sm text-white"
                    >
                      打开文件
                    </a>
                    <a
                      href={latestFigureUrl}
                      download
                      className="rounded-lg border border-[var(--border-default)] px-3 py-2 text-sm text-[var(--text-secondary)]"
                    >
                      下载
                    </a>
                  </div>
                )}
              </div>

              {latestFigureUrl && isImageUrl(latestFigureUrl) && (
                <div className="overflow-hidden rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={latestFigureUrl}
                    alt={readString(latestFigureResult?.description) || "图表预览"}
                    className="max-h-[520px] w-full object-contain"
                  />
                </div>
              )}

              {latestFigureUrl && isPdfUrl(latestFigureUrl) && (
                <div className="overflow-hidden rounded-lg border border-[var(--border-default)] bg-white">
                  <iframe
                    src={latestFigureUrl}
                    title="Figure Preview"
                    className="h-[520px] w-full"
                  />
                </div>
              )}

              {!latestFigureUrl && latestFigureSource && (
                <pre className="overflow-x-auto rounded-lg bg-[var(--bg-elevated)] p-4 text-xs leading-6 text-[var(--text-secondary)]">
                  {latestFigureSource}
                </pre>
              )}

              {!latestFigureUrl && !latestFigureSource && latestFigurePrompt && (
                <div className="rounded-lg bg-[var(--bg-elevated)] p-4 text-sm leading-6 text-[var(--text-secondary)]">
                  {latestFigurePrompt}
                </div>
              )}

              {!latestFigureUrl && !latestFigureSource && !latestFigurePrompt && (
                <div className="text-center py-12">
                  <ImageIcon className="mx-auto mb-4 h-12 w-12 text-cyan-500/60" />
                  <p className="text-sm text-[var(--text-secondary)]">
                    暂无图表产出，执行生成后会在这里显示。
                  </p>
                </div>
              )}
            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
