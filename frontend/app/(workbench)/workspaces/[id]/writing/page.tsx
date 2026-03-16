"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, PenTool, FileEdit } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import { cn } from "@/lib/utils";

const SECTION_OPTIONS = [
  { value: "abstract", label: "摘要" },
  { value: "introduction", label: "引言" },
  { value: "related_work", label: "相关工作" },
  { value: "methodology", label: "方法" },
  { value: "experiments", label: "实验" },
  { value: "results", label: "结果分析" },
  { value: "discussion", label: "讨论" },
  { value: "conclusion", label: "结论" },
];

export default function SciWritingPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { workspace } = useWorkspaceStore();

  const [paperTitle, setPaperTitle] = useState("");
  const [sectionType, setSectionType] = useState("introduction");
  const [targetWords, setTargetWords] = useState(1200);
  const [contextArtifactIds, setContextArtifactIds] = useState("");

  const { run, isRunning, status, error } = useFeatureTaskRunner({
    workspaceId,
    featureId: "writing",
  });

  useEffect(() => {
    if (!workspace || paperTitle) return;
    const fallbackTitle =
      (workspace.description || workspace.name || "").toString().trim();
    if (fallbackTitle) {
      setPaperTitle(fallbackTitle);
    }
  }, [workspace, paperTitle]);

  const sectionHint = useMemo(() => {
    const current = SECTION_OPTIONS.find((option) => option.value === sectionType);
    return current?.label || "章节";
  }, [sectionType]);

  const parseArtifactIds = (): string[] => {
    return contextArtifactIds
      .split(/[\s,，]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  };

  const handleWrite = async () => {
    if (!paperTitle.trim()) return;
    const ids = parseArtifactIds();
    await run({
      paper_title: paperTitle.trim(),
      section_type: sectionType,
      target_words: targetWords,
      context_artifact_ids: ids.length > 0 ? ids : undefined,
    });
  };

  return (
    <div className="h-screen flex flex-col bg-[var(--bg-base)]">
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
            <PenTool className="w-5 h-5 text-amber-600 dark:text-amber-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-[var(--text-primary)]">论文写作</h1>
            <p className="text-xs text-[var(--text-muted)]">生成 SCI 章节草稿并沉淀为可编辑 artifact</p>
          </div>
        </div>
      </header>

      <main className="flex-1 flex overflow-hidden">
        <aside className="w-80 border-r border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
          <h2 className="text-sm font-medium text-[var(--text-primary)] mb-4">写作参数</h2>

          <div className="space-y-4">
            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">论文标题</label>
              <input
                type="text"
                placeholder="输入论文标题"
                value={paperTitle}
                onChange={(event) => setPaperTitle(event.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">章节类型</label>
              <select
                value={sectionType}
                onChange={(event) => setSectionType(event.target.value)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
              >
                {SECTION_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">目标字数</label>
              <input
                type="number"
                min={200}
                step={100}
                value={targetWords}
                onChange={(event) => setTargetWords(Number(event.target.value) || 1200)}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                上下文 Artifact ID（可选）
              </label>
              <textarea
                placeholder="可输入多个 ID，逗号或空格分隔"
                value={contextArtifactIds}
                onChange={(event) => setContextArtifactIds(event.target.value)}
                rows={3}
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
              />
            </div>

            <button
              className={cn(
                "w-full py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 transition-colors",
                isRunning && "opacity-60 cursor-not-allowed"
              )}
              onClick={handleWrite}
              disabled={isRunning}
            >
              {isRunning ? "生成中..." : "生成草稿"}
            </button>

            {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
            {status && !error && <p className="text-xs text-[var(--text-secondary)] mt-1">{status}</p>}
          </div>
        </aside>

        <div className="flex-1 p-6 overflow-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="h-full flex items-center justify-center"
          >
            <div className="text-center max-w-xl">
              <FileEdit className="w-16 h-16 text-amber-500 mx-auto mb-4 opacity-50" />
              <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
                SCI {sectionHint}写作工作区
              </h2>
              <p className="text-[var(--text-secondary)]">
                执行后将生成 <code>paper_draft</code> artifact，并在知识区可继续迭代编辑。
              </p>
              <p className="text-sm text-[var(--text-muted)] mt-2">
                建议先完成文献检索与论文分析，再将关键 artifact 作为上下文注入写作任务。
              </p>
            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
