"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, FlaskConical } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import {
  TaskFeedbackBanner,
  TaskRuntimePanel,
} from "@/components/workspace";
import { ModelSelector } from "@/components/workspace/ModelSelector";
import { useModelSelection } from "@/hooks/useModelSelection";
import { cn } from "@/lib/utils";

export default function DeepResearchPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace } = useWorkspaceStore();

  const [topic, setTopic] = useState("");
  const { run, isRunning, status, error, runtime } = useFeatureTaskRunner({
    workspaceId,
    featureId: "deep_research",
  });
  const {
    models: availableModels,
    selectedModel,
    setSelectedModel,
    isLoading: isModelLoading,
    loadError: modelLoadError,
  } = useModelSelection({
    purpose: "chat",
    persistenceKey: `workspace:${workspaceId}:model:chat`,
  });

  useEffect(() => {
    if (workspace && !topic) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync from async store
      setTopic((workspace.description || workspace.name || "").toString());
    }
  }, [workspace, topic]);

  const handleRun = async () => {
    if (!topic.trim()) return;
    await run({
      topic: topic.trim(),
      query: topic.trim(),
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
        <div className="max-w-6xl mx-auto">
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

            <div className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
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

                <ModelSelector
                  id="deep-research-model"
                  label="推理模型"
                  models={availableModels}
                  selectedModel={selectedModel}
                  onChange={setSelectedModel}
                  isLoading={isModelLoading}
                  loadError={modelLoadError}
                  disabled={isRunning}
                />

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

                <TaskFeedbackBanner
                  isRunning={isRunning}
                  status={status}
                  error={error}
                  onRetry={handleRun}
                />
              </div>

              <TaskRuntimePanel
                runtime={runtime}
                isRunning={isRunning}
                status={status}
                error={error}
                title="Deep Research 运行面板"
                emptyDescription="执行后，这里会实时显示阶段推进、候选论文、研究空白和创意草案。"
              />
            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
