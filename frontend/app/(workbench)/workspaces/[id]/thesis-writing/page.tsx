"use client";

import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, PenTool, FileText, CheckCircle } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useThesisWritingStore } from "@/stores/thesis-writing";
import { cn } from "@/lib/utils";

export default function ThesisWritingPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace } = useWorkspaceStore();
  const { currentStep, outline, chapters, setStep } = useThesisWritingStore();

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
                    placeholder="输入论文主题..."
                    className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/50"
                  />
                </div>

                <div>
                  <label className="block text-xs text-[var(--text-muted)] mb-1">
                    目标字数
                  </label>
                  <select className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/50">
                    <option value="10000">10,000 字</option>
                    <option value="20000">20,000 字</option>
                    <option value="30000">30,000 字</option>
                    <option value="50000">50,000 字</option>
                  </select>
                </div>

                <button className="w-full py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors">
                  生成大纲
                </button>
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
                      className="w-full flex items-center gap-2 p-2 rounded-lg hover:bg-[var(--bg-muted)] text-left"
                    >
                      <CheckCircle
                        className={cn(
                          "w-4 h-4",
                          ch.status === "completed"
                            ? "text-green-500"
                            : "text-[var(--text-muted)]"
                        )}
                      />
                      <span className="text-sm text-[var(--text-primary)] truncate">
                        {ch.title}
                      </span>
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
                className="h-full flex items-center justify-center"
              >
                <div className="text-center">
                  <PenTool className="w-16 h-16 text-purple-500 mx-auto mb-4 opacity-50" />
                  <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
                    全文写作
                  </h2>
                  <p className="text-[var(--text-secondary)]">
                    选择章节开始写作
                  </p>
                </div>
              </motion.div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
