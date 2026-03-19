"use client";

import { useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, FileText, FileDown } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useFeatureTaskRunner } from "@/hooks/useFeatureTaskRunner";
import { TaskFeedbackBanner } from "@/components/workspace/TaskFeedbackBanner";
import { ModelSelector } from "@/components/workspace/ModelSelector";
import { useModelSelection } from "@/hooks/useModelSelection";
import {
  WorkspaceResultPanel,
  type WorkspaceResultViewModel,
} from "@/components/workspace/WorkspaceResultPanel";
import { createWorkspaceResultViewModel, describeFields, describeTaskStatus } from "@/lib/workspace-result";
import { extractArtifactFileUrl, isPdfUrl } from "@/lib/public-assets";
import { getArtifactContentRecord, readString } from "@/lib/artifact-utils";
import { cn } from "@/lib/utils";

export default function CompileExportPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const { artifacts } = useWorkspaceStore();

  const [template, setTemplate] = useState("default");
  const [compiler, setCompiler] = useState("xelatex");
  const [bibStyle, setBibStyle] = useState("gbt7714");

  const { run, isRunning, status, error, result: latestTaskResult } = useFeatureTaskRunner({
    workspaceId,
    featureId: "compile_export",
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

  const latestCompileArtifact = useMemo(
    () =>
      [...artifacts]
        .filter((artifact) => {
          const content = getArtifactContentRecord(artifact);
          return Boolean(content?.compile_status || content?.pdf_path || content?.pdf_url);
        })
        .sort(
          (left, right) =>
            new Date(right.created_at).getTime() - new Date(left.created_at).getTime()
        )[0] ?? null,
    [artifacts]
  );
  const latestCompileResult = useMemo(
    () => getArtifactContentRecord(latestCompileArtifact) ?? latestTaskResult,
    [latestCompileArtifact, latestTaskResult]
  );
  const latestCompileUrl = extractArtifactFileUrl(latestCompileResult);
  const latestCompileStatus = readString(latestCompileResult?.compile_status);
  const latestCompileError = readString(latestCompileResult?.compile_error);
  const latestCompileLogs = readString(latestCompileResult?.compile_logs);
  const latestCompilePageCount =
    typeof latestCompileResult?.page_count === "number"
      ? latestCompileResult.page_count
      : null;
  const latestLatexContent = readString(latestCompileResult?.latex_content);
  const latestBibContent = readString(latestCompileResult?.bib_content);
  const compileResultViewModel: WorkspaceResultViewModel = createWorkspaceResultViewModel({
    summary: latestCompileResult
      ? "最近一次编译结果已生成，可直接预览 PDF 或查看编译日志。"
      : "本工作区用于拼装章节、图表和文献，并编译导出论文 PDF。",
    sections: [
      {
        title: "当前配置",
        content: describeFields([
          ["模板", template],
          ["编译器", compiler],
          ["参考文献格式", bibStyle],
        ]),
      },
      {
        title: "任务状态",
        content: describeTaskStatus({
          error,
          status,
          idleMessage: "尚未开始编译。",
        }),
      },
      {
        title: "最近编译",
        content: latestCompileResult
          ? [
              describeFields([
                ["状态", latestCompileStatus],
                ["页数", latestCompilePageCount],
              ]),
              latestCompileUrl ? "已生成可访问 PDF。" : null,
              latestCompileError ? `错误：${latestCompileError}` : null,
            ]
              .filter((item): item is string => Boolean(item))
              .join("；")
          : "执行后会在这里展示最近一次编译结果。",
      },
    ],
    nextActions: [
      "确认章节、图表和文献已准备完成后开始编译。",
      "若编译失败，先查看日志定位 LaTeX 错误。",
      "编译成功后直接打开或下载 PDF。",
    ],
    outputLanguage: "zh",
  });

  const handleCompile = async () => {
    await run({
      template,
      compiler,
      bibliography_style: bibStyle,
      model_id: selectedModel || undefined,
    });
  };

  const downloadTextFile = (filename: string, content: string) => {
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    window.URL.revokeObjectURL(url);
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
              编译导出
            </h1>
            <p className="text-xs text-[var(--text-muted)]">
              LaTeX 编译 · 多格式导出
            </p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left Sidebar - Config */}
        <aside className="w-72 border-r border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
          <h2 className="text-sm font-medium text-[var(--text-primary)] mb-4">
            编译配置
          </h2>

          <div className="space-y-4">
            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                LaTeX 模板
              </label>
              <select
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/50"
                value={template}
                onChange={(e) => setTemplate(e.target.value)}
              >
                <option value="default">默认模板</option>
                <option value="ieee">IEEE 格式</option>
                <option value="acm">ACM 格式</option>
              </select>
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                编译器
              </label>
              <select
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/50"
                value={compiler}
                onChange={(e) => setCompiler(e.target.value)}
              >
                <option value="xelatex">XeLaTeX</option>
                <option value="pdflatex">PDFLaTeX</option>
                <option value="lualatex">LuaLaTeX</option>
              </select>
            </div>

            <div>
              <label className="block text-xs text-[var(--text-muted)] mb-1">
                参考文献格式
              </label>
              <select
                className="w-full px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/50"
                value={bibStyle}
                onChange={(e) => setBibStyle(e.target.value)}
              >
                <option value="gbt7714">GB/T 7714</option>
                <option value="apa">APA</option>
                <option value="mla">MLA</option>
              </select>
            </div>

            <ModelSelector
              id="compile-export-model"
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
                "w-full py-2 bg-rose-600 text-white rounded-lg hover:bg-rose-700 transition-colors flex items-center justify-center gap-2",
                isRunning && "opacity-60 cursor-not-allowed"
              )}
              onClick={handleCompile}
              disabled={isRunning}
            >
              {isRunning ? (
                <>
                  <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  正在编译...
                </>
              ) : (
                <>
                  <FileDown className="w-4 h-4" />
                  编译 PDF
                </>
              )}
            </button>

            <TaskFeedbackBanner
              isRunning={isRunning}
              status={status}
              error={error}
              onRetry={handleCompile}
            />
          </div>

          {/* Export Options */}
          <div className="mt-6 pt-6 border-t border-[var(--border-default)]">
            <h3 className="text-sm font-medium text-[var(--text-primary)] mb-3">
              导出格式
            </h3>
            <div className="space-y-2">
              <button
                onClick={() => {
                  if (latestCompileUrl) {
                    window.open(latestCompileUrl, "_blank", "noopener,noreferrer");
                  }
                }}
                disabled={!latestCompileUrl}
                className="w-full rounded-lg border border-[var(--border-default)] px-3 py-2 text-left text-sm text-[var(--text-secondary)] disabled:opacity-40"
              >
                导出 PDF
              </button>
              <button
                onClick={() => {
                  if (latestLatexContent) {
                    downloadTextFile("thesis.tex", latestLatexContent);
                  }
                }}
                disabled={!latestLatexContent}
                className="w-full rounded-lg border border-[var(--border-default)] px-3 py-2 text-left text-sm text-[var(--text-secondary)] disabled:opacity-40"
              >
                导出 LaTeX 源码
              </button>
              <button
                onClick={() => {
                  if (latestBibContent) {
                    downloadTextFile("references.bib", latestBibContent);
                  }
                }}
                disabled={!latestBibContent}
                className="w-full rounded-lg border border-[var(--border-default)] px-3 py-2 text-left text-sm text-[var(--text-secondary)] disabled:opacity-40"
              >
                导出 BibTeX
              </button>
            </div>
          </div>
        </aside>

        {/* Main Area - PDF Preview */}
        <div className="flex-1 p-6 overflow-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-6"
          >
            <WorkspaceResultPanel viewModel={compileResultViewModel} />

            <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-5">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold text-[var(--text-primary)]">
                    PDF 预览
                  </h2>
                  <p className="text-sm text-[var(--text-muted)]">
                    编译完成后，这里会展示最近一次 PDF 结果。
                  </p>
                </div>
                {latestCompileUrl && (
                  <div className="flex gap-2">
                    <a
                      href={latestCompileUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-lg bg-rose-600 px-3 py-2 text-sm text-white"
                    >
                      打开 PDF
                    </a>
                    <a
                      href={latestCompileUrl}
                      download
                      className="rounded-lg border border-[var(--border-default)] px-3 py-2 text-sm text-[var(--text-secondary)]"
                    >
                      下载
                    </a>
                  </div>
                )}
              </div>

              {latestCompileUrl && isPdfUrl(latestCompileUrl) ? (
                <div className="overflow-hidden rounded-lg border border-[var(--border-default)] bg-white">
                  <iframe
                    src={latestCompileUrl}
                    title="Compile Preview"
                    className="h-[640px] w-full"
                  />
                </div>
              ) : (
                <div className="text-center py-10">
                  <FileText className="mx-auto mb-4 h-12 w-12 text-rose-500/60" />
                  <p className="text-sm text-[var(--text-secondary)]">
                    暂无可预览 PDF，执行编译后会在这里显示。
                  </p>
                </div>
              )}
            </div>

            {latestCompileLogs && (
              <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-5">
                <h3 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">
                  最近编译日志
                </h3>
                <pre className="overflow-x-auto rounded-lg bg-[var(--bg-elevated)] p-4 text-xs leading-6 text-[var(--text-secondary)]">
                  {latestCompileLogs}
                </pre>
              </div>
            )}
            {latestCompileError && (
              <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300">
                {latestCompileError}
              </div>
            )}
          </motion.div>
        </div>
      </main>
    </div>
  );
}
