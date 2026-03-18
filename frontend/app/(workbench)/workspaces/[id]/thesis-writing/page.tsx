"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, PenTool, CheckCircle } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useThesisWritingStore, type OutlineData } from "@/stores/thesis-writing";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import { TaskFeedbackBanner } from "@/components/workspace/TaskFeedbackBanner";
import { ModelSelector } from "@/components/workspace/ModelSelector";
import {
  WorkspaceResultPanel,
  type WorkspaceResultViewModel,
} from "@/components/workspace/WorkspaceResultPanel";
import { useModelSelection } from "@/hooks/useModelSelection";
import { cn } from "@/lib/utils";
import type { TaskStatus } from "@/lib/api";

function resolveFeatureResult(
  task: TaskStatus | null
): Record<string, unknown> | null {
  if (!task?.result || typeof task.result !== "object") {
    return null;
  }
  const resultObj = task.result as Record<string, unknown>;
  const nested = resultObj.data;
  if (nested && typeof nested === "object") {
    return nested as Record<string, unknown>;
  }
  return resultObj;
}

export default function ThesisWritingPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace } = useWorkspaceStore();
  const {
    currentStep,
    outline,
    chapters,
    currentChapterIndex,
    setStep,
    setOutline,
    setCurrentChapter,
    updateChapterStatus,
  } = useThesisWritingStore();

  const [titleInput, setTitleInput] = useState("");
  const [targetWords, setTargetWords] = useState("20000");
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
    if (workspace && !titleInput) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync from async store
      setTitleInput(workspace.name || "");
    }
  }, [workspace, titleInput]);

  const parseOutline = (raw: unknown): OutlineData | null => {
    if (!raw || typeof raw !== "object") {
      return null;
    }
    const obj = raw as Record<string, unknown>;
    if (!Array.isArray(obj.chapters)) {
      return null;
    }

    const chapters = obj.chapters
      .filter((chapter): chapter is Record<string, unknown> => {
        return Boolean(chapter && typeof chapter === "object");
      })
      .map((chapter) => ({
        title: String(chapter.title || "未命名章节"),
        position: String(chapter.position || ""),
        targetWords: Number(chapter.targetWords || 0),
        keyPoints: Array.isArray(chapter.keyPoints)
          ? chapter.keyPoints.map((item) => String(item))
          : [],
        sections: Array.isArray(chapter.sections)
          ? chapter.sections.map((item) => String(item))
          : [],
      }));

    if (chapters.length === 0) {
      return null;
    }

    return {
      abstract: String(obj.abstract || ""),
      keywords: Array.isArray(obj.keywords)
        ? obj.keywords.map((item) => String(item))
        : [],
      chapters,
    };
  };

  const handleOutlineSuccess = useCallback(
    (task: TaskStatus | null) => {
      if (!task) return;
      const featureResult = resolveFeatureResult(task);
      const outlineData = parseOutline(featureResult?.outline);
      if (outlineData) {
        setOutline(outlineData);
        setStep(2);
      }
    },
    [setOutline, setStep]
  );

  const {
    run: runOutline,
    isRunning: isOutlineRunning,
    status: outlineStatus,
    error: outlineError,
    clearStatus: clearOutlineStatus,
    clearError: clearOutlineError,
  } = useFeatureTaskRunner({
    workspaceId,
    featureId: "thesis_writing",
    onSuccess: handleOutlineSuccess,
  });

  const handleChapterSuccess = useCallback(
    (task: TaskStatus | null) => {
      if (!task) return;
      const chapter = chapters.find((ch) => ch.index === currentChapterIndex);
      if (!chapter) return;

      const resultObj = resolveFeatureResult(task);
      const chapterObj =
        resultObj?.chapter && typeof resultObj.chapter === "object"
          ? (resultObj.chapter as Record<string, unknown>)
          : null;
      const writtenWords = Number(
        chapterObj?.target_words ?? chapterObj?.estimated_words ?? 0
      );

      let chapterContent: string | undefined;
      const storeArtifacts = useWorkspaceStore.getState().artifacts;
      if (Array.isArray(storeArtifacts)) {
        const chapterArtifact = storeArtifacts.find(
          (a) =>
            a.type === "thesis_chapter" &&
            (a.content as Record<string, unknown>)?.chapter_index ===
              chapter.index
        );
        if (chapterArtifact) {
          chapterContent = String(
            (chapterArtifact.content as Record<string, unknown>)?.markdown ||
              ""
          );
        }
      }

      updateChapterStatus(
        chapter.index,
        "completed",
        writtenWords > 0 ? writtenWords : chapter.targetWords,
        chapterContent
      );
    },
    [chapters, currentChapterIndex, updateChapterStatus]
  );

  const handleChapterError = useCallback(() => {
    const chapter = chapters.find((ch) => ch.index === currentChapterIndex);
    if (chapter) {
      updateChapterStatus(chapter.index, "failed");
    }
  }, [chapters, currentChapterIndex, updateChapterStatus]);

  const {
    run: runChapter,
    isRunning: isChapterRunning,
    status: chapterStatus,
    error: chapterError,
    clearStatus: clearChapterStatus,
    clearError: clearChapterError,
  } = useFeatureTaskRunner({
    workspaceId,
    featureId: "thesis_writing",
    onSuccess: handleChapterSuccess,
    onError: handleChapterError,
  });

  const isRunning = isOutlineRunning || isChapterRunning;
  const status = currentStep === 1 ? outlineStatus : chapterStatus;
  const error = currentStep === 1 ? outlineError : chapterError;

  // Sync chapter selection when chapters change
  useEffect(() => {
    if (chapters.length === 0) return;
    const hasCurrent = chapters.some((ch) => ch.index === currentChapterIndex);
    if (!hasCurrent) {
      setCurrentChapter(chapters[0].index);
    }
  }, [chapters, currentChapterIndex, setCurrentChapter]);

  const selectedChapter =
    chapters.find((ch) => ch.index === currentChapterIndex) ?? null;
  const selectedOutlineChapter =
    outline?.chapters[currentChapterIndex] ?? null;

  const step1ResultViewModel: WorkspaceResultViewModel = {
    summary:
      "本工作区用于生成中文论文大纲并逐章写作，最终可进入图表生成与编译导出流程。",
    sections: [
      {
        title: "当前配置",
        content: `论文主题：${titleInput || "未填写"}；目标字数：${targetWords}`,
      },
      {
        title: "流程阶段",
        content:
          currentStep === 1
            ? "当前阶段：大纲规划"
            : `当前阶段：正文写作（${selectedChapter?.title || "未选择章节"}）`,
      },
      {
        title: "任务状态",
        content: error
          ? `执行失败：${error}`
          : status
            ? `执行反馈：${status}`
            : "尚未开始执行。",
      },
    ],
    nextActions: [
      "在 Step 1 先生成完整大纲。",
      "切换到 Step 2 按章节逐步写作并检查字数进度。",
      "完成正文后进入图表生成与编译导出。",
    ],
    outputLanguage: "zh",
  };

  const handleGenerateOutline = async () => {
    if (!titleInput.trim()) return;
    clearChapterStatus();
    clearChapterError();
    await runOutline({
      action: "generate_outline",
      paper_title: titleInput.trim(),
      target_words: Number(targetWords),
      model_id: selectedModel || undefined,
    });
  };

  const handleWriteChapter = async () => {
    if (!selectedChapter) return;
    clearOutlineStatus();
    clearOutlineError();
    updateChapterStatus(selectedChapter.index, "generating");
    await runChapter({
      action: "write_chapter",
      paper_title: titleInput.trim() || workspace?.name || "未命名论文",
      chapter_index: selectedChapter.index,
      chapter_title: selectedChapter.title,
      target_words: selectedChapter.targetWords,
      model_id: selectedModel || undefined,
    });
  };

  return (
    <div className="h-screen flex flex-col bg-[var(--bg-base)]">
      {/* Header */}
      <header className="h-14 flex items-center justify-between px-4 bg-[var(--glass-bg)] backdrop-blur-xl border-b border-[var(--glass-border)]">
        <div className="flex items-center gap-4">
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
            <div className="p-2 rounded-lg bg-purple-500/10">
              <PenTool className="w-5 h-5 text-purple-600 dark:text-purple-400" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-[var(--text-primary)]">
                论文写作
              </h1>
              <p className="text-xs text-[var(--text-muted)]">
                大纲规划 · 全文写作
              </p>
            </div>
          </div>
        </div>

        {/* Step Indicator */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setStep(1)}
            className={cn(
              "px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
              currentStep === 1
                ? "bg-purple-600 text-white"
                : "bg-[var(--bg-surface)] text-[var(--text-secondary)]"
            )}
          >
            Step 1: 大纲规划
          </button>
          <button
            onClick={() => setStep(2)}
            disabled={!outline}
            title={!outline ? "请先生成大纲" : undefined}
            className={cn(
              "px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
              currentStep === 2
                ? "bg-purple-600 text-white"
                : "bg-[var(--bg-surface)] text-[var(--text-secondary)]",
              !outline && "opacity-50 cursor-not-allowed"
            )}
          >
            Step 2: 全文写作
          </button>
          {!outline && (
            <span className="text-xs text-[var(--text-muted)]">
              需要先完成 Step 1
            </span>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex overflow-hidden">
        {currentStep === 1 ? (
          /* Step 1: Outline Planning */
          <>
            {/* Left Sidebar */}
            <aside className="w-80 border-r border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
              <h2 className="text-sm font-medium text-[var(--text-primary)] mb-4">
                大纲配置
              </h2>

              <div className="space-y-4">
                <div>
                  <label className="block text-xs text-[var(--text-muted)] mb-1">
                    论文主题
                  </label>
                  <input
                    type="text"
                    value={titleInput}
                    onChange={(e) => setTitleInput(e.target.value)}
                    placeholder="输入论文主题..."
                    className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/50"
                  />
                </div>

                <div>
                  <label className="block text-xs text-[var(--text-muted)] mb-1">
                    目标字数
                  </label>
                  <select
                    className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/50"
                    value={targetWords}
                    onChange={(e) => setTargetWords(e.target.value)}
                  >
                    <option value="10000">10,000 字</option>
                    <option value="20000">20,000 字</option>
                    <option value="30000">30,000 字</option>
                    <option value="50000">50,000 字</option>
                  </select>
                </div>

                <ModelSelector
                  id="thesis-writing-model"
                  label="写作模型"
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
                  onClick={handleGenerateOutline}
                  disabled={isRunning}
                >
                  {isRunning ? "正在生成..." : "生成大纲"}
                </button>

                <TaskFeedbackBanner
                  isRunning={isRunning}
                  status={status}
                  error={error}
                  onRetry={handleGenerateOutline}
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
                <WorkspaceResultPanel viewModel={step1ResultViewModel} />
              </motion.div>
            </div>
          </>
        ) : (
          /* Step 2: Full Writing */
          <>
            {/* Left Sidebar - Chapter Nav */}
            <aside className="w-64 border-r border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
              <h2 className="text-sm font-medium text-[var(--text-primary)] mb-4">
                章节导航
              </h2>

              <div className="space-y-2">
                {chapters.length === 0 ? (
                  <p className="text-sm text-[var(--text-muted)]">暂无章节</p>
                ) : (
                  chapters.map((ch) => (
                    <button
                      key={ch.index}
                      className={cn(
                        "w-full flex items-center gap-2 p-2 rounded-lg text-left transition-colors",
                        ch.index === currentChapterIndex
                          ? "bg-purple-500/15 border border-purple-500/30"
                          : "hover:bg-[var(--bg-muted)] border border-transparent"
                      )}
                      onClick={() => setCurrentChapter(ch.index)}
                    >
                      <CheckCircle
                        className={cn(
                          "w-4 h-4",
                          ch.status === "completed" && "text-green-500",
                          ch.status === "generating" && "text-amber-500",
                          ch.status === "failed" && "text-red-500",
                          ch.status === "pending" && "text-[var(--text-muted)]"
                        )}
                      />
                      <div className="min-w-0">
                        <span className="block text-sm text-[var(--text-primary)] truncate">
                          {ch.title}
                        </span>
                        <span className="block text-[11px] text-[var(--text-muted)]">
                          目标 {ch.targetWords.toLocaleString()} 字
                        </span>
                      </div>
                    </button>
                  ))
                )}
              </div>
            </aside>

            {/* Main Area - Editor */}
            <div className="flex-1 p-6 overflow-auto">
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="h-full"
              >
                {selectedChapter && selectedOutlineChapter ? (
                  <div className="max-w-3xl mx-auto space-y-6">
                    <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-5">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <h2 className="text-xl font-semibold text-[var(--text-primary)]">
                            {selectedChapter.title}
                          </h2>
                          <p className="text-sm text-[var(--text-secondary)] mt-1">
                            {selectedOutlineChapter.position || "正文章节"}
                          </p>
                        </div>
                        <span
                          className={cn(
                            "px-2.5 py-1 rounded-md text-xs font-medium",
                            selectedChapter.status === "completed" &&
                              "bg-green-500/10 text-green-600",
                            selectedChapter.status === "generating" &&
                              "bg-amber-500/10 text-amber-600",
                            selectedChapter.status === "failed" &&
                              "bg-red-500/10 text-red-600",
                            selectedChapter.status === "pending" &&
                              "bg-[var(--bg-muted)] text-[var(--text-secondary)]"
                          )}
                        >
                          {selectedChapter.status === "completed"
                            ? "已完成"
                            : selectedChapter.status === "generating"
                            ? "生成中"
                            : selectedChapter.status === "failed"
                            ? "失败"
                            : "待写作"}
                        </span>
                      </div>

                      <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                        <div className="rounded-lg bg-[var(--bg-elevated)] px-3 py-2">
                          <p className="text-[var(--text-muted)]">目标字数</p>
                          <p className="text-[var(--text-primary)] font-medium">
                            {selectedChapter.targetWords.toLocaleString()} 字
                          </p>
                        </div>
                        <div className="rounded-lg bg-[var(--bg-elevated)] px-3 py-2">
                          <p className="text-[var(--text-muted)]">当前进度</p>
                          <p className="text-[var(--text-primary)] font-medium">
                            {selectedChapter.currentWords.toLocaleString()} 字
                          </p>
                        </div>
                      </div>

                      <ModelSelector
                        id="thesis-writing-model-step2"
                        label="写作模型"
                        models={availableModels}
                        selectedModel={selectedModel}
                        onChange={setSelectedModel}
                        isLoading={isModelLoading}
                        loadError={modelLoadError}
                        disabled={isRunning}
                        className="mt-4 max-w-sm"
                      />

                      <button
                        className={cn(
                          "mt-4 w-full sm:w-auto px-4 py-2 rounded-lg text-white transition-colors",
                          isRunning
                            ? "bg-purple-400 cursor-not-allowed"
                            : "bg-purple-600 hover:bg-purple-700"
                        )}
                        onClick={handleWriteChapter}
                        disabled={isRunning}
                      >
                        {isRunning ? "正在写作..." : "写作本章"}
                      </button>

                      <TaskFeedbackBanner
                        isRunning={isRunning}
                        status={status}
                        error={error}
                        onRetry={handleWriteChapter}
                        className="mt-3"
                      />
                    </div>

                    <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-5">
                      <h3 className="text-sm font-medium text-[var(--text-primary)] mb-3">
                        本章写作要点
                      </h3>
                      <div className="space-y-2">
                        {selectedOutlineChapter.keyPoints.length > 0 ? (
                          selectedOutlineChapter.keyPoints.map((point, idx) => (
                            <p
                              key={`${selectedChapter.index}-kp-${idx}`}
                              className="text-sm text-[var(--text-secondary)]"
                            >
                              {idx + 1}. {point}
                            </p>
                          ))
                        ) : (
                          <p className="text-sm text-[var(--text-muted)]">
                            暂无关键要点
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Chapter Content Display */}
                    {selectedChapter.content && (
                      <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-5">
                        <h3 className="text-sm font-medium text-[var(--text-primary)] mb-3">
                          章节正文
                        </h3>
                        <div className="prose prose-sm max-w-none text-[var(--text-secondary)] whitespace-pre-wrap">
                          {selectedChapter.content}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="h-full flex items-center justify-center text-center">
                    <div>
                      <PenTool className="w-16 h-16 text-purple-500 mx-auto mb-4 opacity-50" />
                      <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
                        全文写作
                      </h2>
                      <p className="text-[var(--text-secondary)]">
                        请先生成大纲，再选择章节开始写作
                      </p>
                    </div>
                  </div>
                )}
              </motion.div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
