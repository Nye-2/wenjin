"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, PenTool, FileText, CheckCircle } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useThesisWritingStore, type OutlineData } from "@/stores/thesis-writing";
import { executeWorkspaceFeature } from "@/lib/api";
import { pollTaskUntilTerminal } from "@/lib/taskPolling";
import { cn } from "@/lib/utils";

export default function ThesisWritingPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace, fetchArtifacts } = useWorkspaceStore();
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
  const [isRunning, setIsRunning] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  useEffect(() => {
    if (workspace && !titleInput) {
      setTitleInput(workspace.name || "");
    }
  }, [workspace, titleInput]);

  useEffect(() => {
    if (chapters.length === 0) {
      return;
    }
    const hasCurrent = chapters.some((ch) => ch.index === currentChapterIndex);
    if (!hasCurrent) {
      setCurrentChapter(chapters[0].index);
    }
  }, [chapters, currentChapterIndex, setCurrentChapter]);

  const selectedChapter =
    chapters.find((ch) => ch.index === currentChapterIndex) ?? null;
  const selectedOutlineChapter =
    outline?.chapters[currentChapterIndex] ?? null;

  const handleGenerateOutline = async () => {
    if (isRunning) return;
    if (!titleInput.trim()) {
      setError("请输入论文主题");
      return;
    }
    setError(null);
    setStatus(null);
    setIsRunning(true);

    try {
      const resp = await executeWorkspaceFeature(
        workspaceId,
        "thesis_writing",
        {
          action: "generate_outline",
          paper_title: titleInput.trim(),
          target_words: Number(targetWords),
        }
      );

      if (resp.status === "warning") {
        setStatus(resp.message || "暂时无法生成大纲");
        return;
      }
      if (!resp.task_id) {
        setError("任务创建失败，请稍后重试");
        return;
      }

      setStatus("大纲生成任务已提交，正在处理中...");

      const task = await pollTaskUntilTerminal(resp.task_id, {
        onProgress: (task) => {
          if (task.message) {
            setStatus(task.message);
          }
        },
      });
      if (!task) {
        setError("任务轮询超时，请稍后在工作区查看结果");
        return;
      }

      if (task.status === "success") {
        const outlineData = parseOutline(task.result?.outline);
        if (outlineData) {
          setOutline(outlineData);
          setStep(2);
          setStatus("大纲已生成并同步到章节导航。");
        } else {
          setStatus(task.message || "大纲任务已完成，请在成果区查看输出。");
        }
        await fetchArtifacts(workspaceId);
      } else {
        setError(task.error || task.message || "生成大纲失败，请稍后重试");
      }
    } catch (e: unknown) {
      setError(
        e instanceof Error ? e.message : "生成大纲失败，请稍后重试"
      );
    } finally {
      setIsRunning(false);
    }
  };

  const handleWriteChapter = async () => {
    if (isRunning) return;
    if (!selectedChapter) {
      setError("请先生成大纲并选择章节");
      return;
    }

    setError(null);
    setStatus(null);
    setIsRunning(true);
    updateChapterStatus(selectedChapter.index, "generating");

    try {
      const resp = await executeWorkspaceFeature(
        workspaceId,
        "thesis_writing",
        {
          action: "write_chapter",
          paper_title: titleInput.trim() || workspace?.name || "未命名论文",
          chapter_index: selectedChapter.index,
          chapter_title: selectedChapter.title,
          target_words: selectedChapter.targetWords,
        }
      );

      if (resp.status === "warning") {
        setStatus(resp.message || "暂时无法生成章节");
        updateChapterStatus(selectedChapter.index, "pending");
        return;
      }
      if (!resp.task_id) {
        setError("任务创建失败，请稍后重试");
        updateChapterStatus(selectedChapter.index, "failed");
        return;
      }

      setStatus(`第 ${selectedChapter.index + 1} 章任务已提交，正在处理中...`);

      const task = await pollTaskUntilTerminal(resp.task_id, {
        onProgress: (task) => {
          if (task.message) {
            setStatus(task.message);
          }
        },
      });
      if (!task) {
        setError("任务轮询超时，请稍后在工作区查看结果");
        updateChapterStatus(selectedChapter.index, "failed");
        return;
      }

      if (task.status === "success") {
        const resultObj =
          task.result && typeof task.result === "object"
            ? (task.result as Record<string, unknown>)
            : null;
        const chapterObj =
          resultObj?.chapter && typeof resultObj.chapter === "object"
            ? (resultObj.chapter as Record<string, unknown>)
            : null;
        const writtenWords = Number(chapterObj?.target_words || 0);
        updateChapterStatus(
          selectedChapter.index,
          "completed",
          writtenWords > 0 ? writtenWords : selectedChapter.targetWords
        );
        setStatus(`第 ${selectedChapter.index + 1} 章写作完成，已生成章节草稿。`);
        await fetchArtifacts(workspaceId);
      } else {
        updateChapterStatus(selectedChapter.index, "failed");
        setError(task.error || task.message || "章节写作失败，请稍后重试");
      }
    } catch (e: unknown) {
      updateChapterStatus(selectedChapter.index, "failed");
      setError(
        e instanceof Error ? e.message : "章节写作失败，请稍后重试"
      );
    } finally {
      setIsRunning(false);
    }
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

                {error && (
                  <p className="text-xs text-red-500 mt-1">{error}</p>
                )}
                {status && !error && (
                  <p className="text-xs text-[var(--text-secondary)] mt-1">
                    {status}
                  </p>
                )}
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
                  <FileText className="w-16 h-16 text-purple-500 mx-auto mb-4 opacity-50" />
                  <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
                    大纲规划
                  </h2>
                  <p className="text-[var(--text-secondary)]">
                    配置左侧参数后生成论文大纲
                  </p>
                </div>
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

                      {error && (
                        <p className="text-xs text-red-500 mt-3">{error}</p>
                      )}
                      {status && !error && (
                        <p className="text-xs text-[var(--text-secondary)] mt-3">
                          {status}
                        </p>
                      )}
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
