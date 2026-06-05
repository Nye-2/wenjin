import {
  Activity,
  CheckCircle2,
  Clock3,
  Loader2,
  Sparkles,
  X,
} from "lucide-react";

import type { ExecutionRecord } from "@/lib/api";
import type { PhaseGroup } from "@/lib/execution-phases";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

import {
  prismExecutionNodeLabel,
  prismJobStatusLabel,
  trimSnippet,
  type PrismOptimizationJob,
} from "./prismOptimizationJobs";

export function PrismOptimizationTraceDialog({
  open,
  activeJob,
  jobs,
  activeRecord,
  activePhases,
  fileChangesCount,
  onOpenChange,
  onSelectJob,
  onViewPendingChanges,
}: {
  open: boolean;
  activeJob: PrismOptimizationJob | null;
  jobs: PrismOptimizationJob[];
  activeRecord: ExecutionRecord | null;
  activePhases: PhaseGroup[];
  fileChangesCount: number;
  onOpenChange: (open: boolean) => void;
  onSelectJob: (jobId: string) => void;
  onViewPendingChanges: () => void;
}) {
  return (
    <>
      {activeJob ? (
        <button
          type="button"
          onClick={() => onOpenChange(true)}
          className="fixed bottom-5 right-5 z-40 flex max-w-[320px] items-center gap-3 rounded-2xl border border-white/60 bg-white/90 px-4 py-3 text-left shadow-2xl shadow-[rgba(86,74,118,0.16)] backdrop-blur-xl transition hover:-translate-y-0.5 hover:bg-white"
        >
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--wjn-accent-soft)] text-[var(--wjn-blue)]">
            {activeJob.status === "launching" ||
            activeJob.status === "running" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : activeJob.status === "completed" ? (
              <CheckCircle2 className="h-4 w-4" />
            ) : (
              <X className="h-4 w-4" />
            )}
          </span>
          <span className="min-w-0">
            <span className="block text-sm font-medium text-[var(--wjn-text)]">
              {prismJobStatusLabel(activeJob.status)}
            </span>
            <span className="mt-0.5 block truncate text-xs text-[var(--wjn-text-muted)]">
              {trimSnippet(activeJob.selectedText, 72)}
            </span>
          </span>
        </button>
      ) : null}

      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[84vh] max-w-2xl overflow-auto">
          <DialogHeader>
            <DialogTitle>Prism 优化过程</DialogTitle>
            <DialogDescription>
              右侧研究团队会处理改稿任务，结果会进入 Prism 待确认写入。
            </DialogDescription>
          </DialogHeader>
          {activeJob ? (
            <div className="space-y-4">
              <div className="rounded-xl border border-[var(--wjn-line)] bg-white/80 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-[var(--wjn-blue)]" />
                    <p className="text-sm font-medium">
                      {prismJobStatusLabel(activeJob.status)}
                    </p>
                  </div>
                  <span className="rounded-full border border-[var(--wjn-line)] bg-white px-2 py-0.5 text-[11px] text-[var(--wjn-text-muted)]">
                    {activeJob.scope === "document"
                      ? "全文"
                      : activeJob.scope === "section"
                        ? "所在 section"
                        : "仅选区"}
                  </span>
                </div>
                <p className="mt-2 text-xs leading-5 text-[var(--wjn-text-muted)]">
                  文件：{activeJob.filePath}
                </p>
                <p className="mt-2 rounded-lg bg-[rgba(19,34,53,0.04)] px-3 py-2 text-xs leading-5 text-[var(--wjn-text-secondary)]">
                  {trimSnippet(activeJob.selectedText, 240)}
                </p>
                <p className="mt-2 text-xs leading-5 text-[var(--wjn-text-muted)]">
                  指令：{activeJob.instruction}
                </p>
                {activeJob.error ? (
                  <p className="mt-2 rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs text-red-700">
                    {activeJob.error}
                  </p>
                ) : null}
              </div>

              {jobs.length > 1 ? (
                <div className="flex flex-wrap gap-2">
                  {jobs.map((job, index) => (
                    <button
                      key={job.id}
                      type="button"
                      onClick={() => onSelectJob(job.id)}
                      className={`rounded-full border px-3 py-1 text-xs ${
                        job.id === activeJob.id
                          ? "border-[var(--wjn-accent-line)] bg-[var(--wjn-accent-soft)] text-[var(--wjn-blue)]"
                          : "border-[var(--wjn-line)] bg-white text-[var(--wjn-text-muted)]"
                      }`}
                    >
                      任务 {index + 1} · {prismJobStatusLabel(job.status)}
                    </button>
                  ))}
                </div>
              ) : null}

              <div className="rounded-xl border border-[var(--wjn-line)] bg-white/80 p-3">
                <div className="flex items-center gap-2">
                  <Activity className="h-4 w-4 text-[var(--wjn-blue)]" />
                  <p className="text-sm font-medium">执行节点</p>
                </div>
                {activeRecord ? (
                  <div className="mt-3 space-y-3">
                    <div className="grid gap-2 text-xs text-[var(--wjn-text-muted)] md:grid-cols-3">
                      <span>执行：{activeRecord.id.slice(0, 8)}</span>
                      <span>状态：{activeRecord.status}</span>
                      <span>进度：{Math.round(activeRecord.progress || 0)}%</span>
                    </div>
                    {activePhases.length > 0 ? (
                      <div className="space-y-3">
                        {activePhases.map((phase) => (
                          <div key={`${phase.name}-${phase.index}`} className="rounded-lg border border-[var(--wjn-line)] bg-[rgba(19,34,53,0.025)] p-2">
                            <p className="text-xs font-medium text-[var(--wjn-text-secondary)]">
                              {phase.name}
                            </p>
                            <div className="mt-2 space-y-2">
                              {phase.nodes.map((node) => {
                                const nodeState = activeRecord.node_states[node.id] || {};
                                return (
                                  <div key={node.id} className="rounded-md bg-white/80 px-3 py-2">
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                      <p className="text-xs font-medium">
                                        {node.label || node.task || node.id}
                                      </p>
                                      <span className="inline-flex items-center gap-1 rounded-full border border-[var(--wjn-line)] bg-white px-2 py-0.5 text-[11px] text-[var(--wjn-text-muted)]">
                                        <Clock3 className="h-3 w-3" />
                                        {prismExecutionNodeLabel(nodeState.status)}
                                      </span>
                                    </div>
                                    {nodeState.output_preview ? (
                                      <p className="mt-1 text-xs leading-5 text-[var(--wjn-text-muted)]">
                                        {nodeState.output_preview}
                                      </p>
                                    ) : nodeState.thinking ? (
                                      <p className="mt-1 text-xs leading-5 text-[var(--wjn-text-muted)]">
                                        {trimSnippet(nodeState.thinking, 180)}
                                      </p>
                                    ) : null}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-[var(--wjn-text-muted)]">正在等待执行图回传。</p>
                    )}
                  </div>
                ) : (
                  <p className="mt-3 text-xs text-[var(--wjn-text-muted)]">
                    {activeJob.executionId
                      ? "已启动，正在拉取执行过程。"
                      : "正在等待 Agent 启动确认。"}
                  </p>
                )}
              </div>

              <div className="flex flex-wrap justify-end gap-2">
                <Button
                  variant="outline"
                  onClick={() => onOpenChange(false)}
                >
                  关闭
                </Button>
                <Button
                  onClick={onViewPendingChanges}
                  disabled={fileChangesCount === 0}
                >
                  查看待确认写入
                </Button>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}
