"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, FlaskConical } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { executeWorkspaceFeature } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function DeepResearchPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace } = useWorkspaceStore();

  const [topic, setTopic] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (workspace && !topic) {
      setTopic(
        (workspace.description || workspace.name || "").toString()
      );
    }
  }, [workspace, topic]);

  const handleRun = async () => {
    if (isRunning) return;
    if (!topic.trim()) {
      setError("请输入研究主题");
      return;
    }

    setError(null);
    setStatus(null);
    setIsRunning(true);

    try {
      // 通过统一 features API 触发 deep_research 任务
      const resp = await executeWorkspaceFeature(workspaceId, "deep_research", {
        query: topic.trim(),
      });

      if (resp.status === "warning") {
        setStatus(resp.message || "暂时无法执行 Deep Research");
      } else {
        setStatus("任务已提交，稍后可在工作台知识区查看文献综述与研究创意。");
      }
    } catch (e: unknown) {
      setError(
        e instanceof Error ? e.message : "Deep Research 执行失败，请稍后重试"
      );
    } finally {
      setIsRunning(false);
    }
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
          <div className="p-2 rounded-lg bg-blue-500/10">
            <FlaskConical className="w-5 h-5 text-blue-600 dark:text-blue-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-[var(--text-primary)]">
              Deep Research
            </h1>
            <p className="text-xs text-[var(--text-muted)]">
              深度文献调研与研究创意探索
            </p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="py-8 space-y-6"
          >
            <div>
              <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
                Deep Research 工作区
              </h2>
              <p className="text-sm text-[var(--text-secondary)] max-w-2xl">
                输入论文研究主题，系统将调用 Deep Research 能力，对相关文献进行检索与分析，
                产出文献综述、研究空白分析与研究创意，并作为知识产出物保存到 workspace。
              </p>
            </div>

            <div className="bg-[var(--bg-surface)] border border-[var(--border-default)] rounded-xl p-6 space-y-4">
              <div>
                <label className="block text-xs text-[var(--text-muted)] mb-1">
                  研究主题
                </label>
                <textarea
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder="例如：面向边缘设备的轻量级图像分割网络"
                  rows={3}
                  className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 resize-none"
                />
              </div>

              <div className="flex items-center justify-between">
                <button
                  onClick={handleRun}
                  disabled={isRunning}
                  className={cn(
                    "inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium",
                    "bg-blue-600 text-white hover:bg-blue-700 transition-colors",
                    isRunning && "opacity-60 cursor-not-allowed"
                  )}
                >
                  {isRunning ? (
                    <>
                      <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      正在执行 Deep Research...
                    </>
                  ) : (
                    <>
                      <FlaskConical className="w-4 h-4" />
                      开始 Deep Research
                    </>
                  )}
                </button>

                <p className="text-xs text-[var(--text-muted)]">
                  运行完成后，可在工作台“最近产出”与“Knowledge” 中查看结果。
                </p>
              </div>

              {error && (
                <p className="text-xs text-red-500 mt-1">
                  {error}
                </p>
              )}
              {status && !error && (
                <p className="text-xs text-[var(--text-secondary)] mt-1">
                  {status}
                </p>
              )}
            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
