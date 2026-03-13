"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, FileText, Lightbulb } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { executeWorkspaceFeature } from "@/lib/api";
import { pollTaskUntilTerminal } from "@/lib/taskPolling";
import { cn } from "@/lib/utils";

export default function PatentOutlinePage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace, fetchArtifacts } = useWorkspaceStore();

  const [innovationDescription, setInnovationDescription] = useState("");
  const [technicalField, setTechnicalField] = useState("");
  const [applicationScenario, setApplicationScenario] = useState("");
  const [implementationMethod, setImplementationMethod] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (workspace && !innovationDescription) {
      setInnovationDescription(
        (workspace.description || workspace.name || "").toString()
      );
    }
  }, [workspace, innovationDescription]);

  const handleGenerate = async () => {
    if (isRunning) return;
    if (!innovationDescription.trim()) {
      setError("请输入创新点描述");
      return;
    }

    setError(null);
    setStatus(null);
    setIsRunning(true);

    try {
      const resp = await executeWorkspaceFeature(
        workspaceId,
        "patent_outline",
        {
          innovation_description: innovationDescription.trim(),
          technical_field: technicalField.trim(),
          application_scenario: applicationScenario.trim(),
          implementation_method: implementationMethod.trim(),
        }
      );

      if (resp.status === "warning" && !resp.task_id) {
        setError(resp.message || "暂时无法生成专利框架");
        return;
      }
      if (!resp.task_id) {
        setError("任务创建失败，请稍后重试");
        return;
      }

      setStatus("任务已提交，正在生成专利说明书框架...");
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
        await fetchArtifacts(workspaceId);
        setStatus(task.message || "专利框架生成完成");
      } else {
        setError(task.error || task.message || "生成专利框架失败");
      }
    } catch (e: unknown) {
      setError(
        e instanceof Error ? e.message : "生成专利框架失败，请稍后重试"
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
          <div className="p-2 rounded-lg bg-rose-500/10">
            <FileText className="w-5 h-5 text-rose-600 dark:text-rose-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-[var(--text-primary)]">
              专利框架
            </h1>
            <p className="text-xs text-[var(--text-muted)]">
              生成专利说明书与权利要求书框架
            </p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left Sidebar - Input */}
        <aside className="w-96 border-r border-[var(--border-default)] bg-[var(--bg-surface)] p-4 overflow-y-auto">
          <h2 className="text-sm font-medium text-[var(--text-primary)] mb-4">
            专利信息配置
          </h2>

          <div className="space-y-4">
            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                创新点描述 <span className="text-red-500">*</span>
              </label>
              <textarea
                placeholder="描述发明的核心创新点..."
                value={innovationDescription}
                onChange={(e) => setInnovationDescription(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/50 resize-none"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                技术领域
              </label>
              <input
                type="text"
                placeholder="如：人工智能、物联网、生物医药..."
                value={technicalField}
                onChange={(e) => setTechnicalField(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                应用场景
              </label>
              <textarea
                placeholder="描述发明的具体应用场景..."
                value={applicationScenario}
                onChange={(e) => setApplicationScenario(e.target.value)}
                rows={2}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/50 resize-none"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                预期实施方式
              </label>
              <textarea
                placeholder="描述发明的具体实施方式..."
                value={implementationMethod}
                onChange={(e) => setImplementationMethod(e.target.value)}
                rows={2}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/50 resize-none"
              />
            </div>

            <button
              className={cn(
                "w-full py-2.5 bg-rose-600 text-white rounded-lg hover:bg-rose-700 transition-colors font-medium",
                isRunning && "opacity-60 cursor-not-allowed"
              )}
              onClick={handleGenerate}
              disabled={isRunning}
            >
              {isRunning ? "正在生成..." : "生成专利框架"}
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
            <div className="text-center max-w-md">
              <Lightbulb className="w-16 h-16 text-rose-500 mx-auto mb-4 opacity-50" />
              <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
                专利框架生成
              </h2>
              <p className="text-[var(--text-secondary)] mb-4">
                填写左侧创新点信息后点击生成，系统将生成包含以下内容的专利框架：
              </p>
              <div className="text-left text-sm text-[var(--text-muted)] space-y-2">
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                  技术领域说明
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                  背景技术分析
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                  发明内容描述
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                  附图说明
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                  具体实施方式
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                  权利要求草案
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
