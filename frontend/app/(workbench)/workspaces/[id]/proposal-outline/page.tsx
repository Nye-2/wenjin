"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, List, FileText } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { executeWorkspaceFeature } from "@/lib/api";
import { pollTaskUntilTerminal } from "@/lib/taskPolling";
import { cn } from "@/lib/utils";

const PROPOSAL_TYPES = [
  { value: "national_natural_science", label: "国家自然科学基金" },
  { value: "national_social_science", label: "国家社会科学基金" },
  { value: "provincial", label: "省部级项目" },
  { value: "enterprise", label: "企业联合项目" },
  { value: "university", label: "校级项目" },
  { value: "other", label: "其他类型" },
] as const;

const PERIOD_OPTIONS = [
  { value: 12, label: "1年（12个月）" },
  { value: 24, label: "2年（24个月）" },
  { value: 36, label: "3年（36个月）" },
  { value: 48, label: "4年（48个月）" },
  { value: 60, label: "5年（60个月）" },
] as const;

type ProposalTypeValue = (typeof PROPOSAL_TYPES)[number]["value"];

export default function ProposalOutlinePage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace, fetchArtifacts } = useWorkspaceStore();

  const [topic, setTopic] = useState("");
  const [proposalType, setProposalType] = useState<ProposalTypeValue>("other");
  const [periodMonths, setPeriodMonths] = useState<number>(24);
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

  const handleGenerate = async () => {
    if (isRunning) return;
    if (!topic.trim()) {
      setError("请输入项目主题");
      return;
    }

    setError(null);
    setStatus(null);
    setIsRunning(true);

    try {
      const resp = await executeWorkspaceFeature(
        workspaceId,
        "proposal_outline",
        {
          topic: topic.trim(),
          proposal_type: proposalType,
          period_months: periodMonths,
        }
      );

      if (resp.status === "warning" && !resp.task_id) {
        setError(resp.message || "暂时无法生成申报书大纲");
        return;
      }
      if (!resp.task_id) {
        setError("任务创建失败，请稍后重试");
        return;
      }

      setStatus("任务已提交，正在生成申报书大纲...");
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
        setStatus(task.message || "申报书大纲生成完成");
      } else {
        setError(task.error || task.message || "生成申报书大纲失败");
      }
    } catch (e: unknown) {
      setError(
        e instanceof Error ? e.message : "生成申报书大纲失败，请稍后重试"
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
          <div className="p-2 rounded-lg bg-purple-500/10">
            <List className="w-5 h-5 text-purple-600 dark:text-purple-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-[var(--text-primary)]">
              申报书大纲
            </h1>
            <p className="text-xs text-[var(--text-muted)]">
              生成项目申报书结构化大纲
            </p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left Sidebar - Input */}
        <aside className="w-80 border-r border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
          <h2 className="text-sm font-medium text-[var(--text-primary)] mb-4">
            大纲配置
          </h2>

          <div className="space-y-4">
            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                项目主题
              </label>
              <input
                type="text"
                placeholder="输入项目主题..."
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                申报类型
              </label>
              <select
                value={proposalType}
                onChange={(e) => setProposalType(e.target.value as ProposalTypeValue)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/50"
              >
                {PROPOSAL_TYPES.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                项目周期
              </label>
              <select
                value={periodMonths}
                onChange={(e) => setPeriodMonths(Number(e.target.value))}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/50"
              >
                {PERIOD_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <button
              className={cn(
                "w-full py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors",
                isRunning && "opacity-60 cursor-not-allowed"
              )}
              onClick={handleGenerate}
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
                申报书大纲工作区
              </h2>
              <p className="text-[var(--text-secondary)]">
                配置左侧参数后点击生成大纲，生成的大纲将作为产出物保存。
              </p>
              <p className="text-sm text-[var(--text-muted)] mt-2">
                包含：立项依据、研究目标、技术路线、计划进度、预算框架
              </p>
            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
